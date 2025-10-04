import logging
import time
from utils.solar_logger import SolarChargingLogger


class Controller:
    def __init__(self, config: dict):
        self.config = config
        self.logger = logging.getLogger("controller")
        ctrl = config.get("control", {})
        
        # Check if test mode is enabled
        test_mode = config.get("test_mode", False)
        
        if test_mode:
            self.logger.info("TEST MODE ENABLED - Using test configuration values")
            # Test mode values from config
            test_ctrl = config.get("test_control", {})
            self.start_threshold_w = int(test_ctrl.get("start_export_watts", 200))
            self.stop_threshold_w = int(test_ctrl.get("stop_export_watts", 150))
            self.min_on = int(test_ctrl.get("min_on_seconds", 30))
            self.min_off = int(test_ctrl.get("min_off_seconds", 30))
        else:
            # Normal configuration values
            self.start_threshold_w = int(ctrl.get("start_export_watts", 3500))
            self.stop_threshold_w = int(ctrl.get("stop_export_watts", 1500))
            self.min_on = int(ctrl.get("min_on_seconds", 300))
            self.min_off = int(ctrl.get("min_off_seconds", 300))
        
        self.max_soc = int(ctrl.get("max_soc", 80))
        
        # Dynamic charging configuration (works in both normal and test mode)
        self.dynamic_charging = ctrl.get("dynamic_charging", {}).get("enabled", False)
        self.min_dynamic_watts = int(ctrl.get("dynamic_charging", {}).get("min_watts", 1200))
        self.min_charge_amps = int(ctrl.get("dynamic_charging", {}).get("min_amps", 5))
        self.max_charge_amps = int(ctrl.get("dynamic_charging", {}).get("max_amps", 24))
        
        # Stepped amperage control to reduce API calls
        self.min_start_amps = int(ctrl.get("dynamic_charging", {}).get("min_start_amps", 8))  # Don't start below 8A
        self.amp_steps = ctrl.get("dynamic_charging", {}).get("amp_steps", [8, 10, 12])  # Only use these amperage levels
        self.mode = ctrl.get("mode", "threshold")
        
        if test_mode:
            self.logger.info(f"TEST MODE: Dynamic charging enabled: {self.dynamic_charging}, Mode: {self.mode}")

        self._charging = False
        self._last_change_ts = 0.0
        
        # Initialize solar logger
        self.solar_logger = SolarChargingLogger()
        self._last_log_time = 0.0
    
    def calculate_optimal_amps(self, solar_power_w: int, house_load_w: int = None) -> int:
        """Calculate optimal charging amperage based on available solar power"""
        if not self.dynamic_charging:
            return None
        
        # Calculate house load from threshold if not provided
        if house_load_w is None:
            # Derive from threshold: threshold = house_load + (120V * 12A)
            # Your 1.8kW threshold with 12A@120V charging = 360W house load
            baseline_tesla_w = 120 * 12  # 1440W
            house_load_w = self.start_threshold_w - baseline_tesla_w
            self.logger.debug(f"Calculated house load: {house_load_w}W (from {self.start_threshold_w}W threshold)")
            
        # Available power for Tesla (solar - house load)
        available_power_w = solar_power_w - house_load_w
        
        # Don't charge if below minimum threshold
        if available_power_w < self.min_dynamic_watts:
            return None
            
        # Tesla charges at different voltages depending on setup
        # Use actual voltage from config or default to 120V for Level 1 (mobile connector)
        charging_voltage = self.config.get("tesla", {}).get("charging_voltage", 120)
        
        # Calculate optimal amperage: watts = volts * amps
        calculated_amps = available_power_w / charging_voltage
        
        # Find the best step from our allowed amperage levels
        best_amps = None
        for step_amps in self.amp_steps:
            if step_amps <= calculated_amps:
                best_amps = step_amps
            else:
                break  # Steps should be in ascending order
        
        # Don't start charging if we can't reach minimum start amperage
        if best_amps is None or best_amps < self.min_start_amps:
            self.logger.debug(f"Available power ({available_power_w}W) insufficient for minimum start amperage ({self.min_start_amps}A)")
            return None
            
        return best_amps

    def _enforce_hysteresis(self, want_on: bool) -> bool:
        now = time.time()
        elapsed = now - self._last_change_ts
        if want_on and not self._charging:
            return elapsed >= self.min_off
        if not want_on and self._charging:
            return elapsed >= self.min_on
        return False

    def decide_action(self, ctx: dict) -> dict:
        soc = ctx.get("vehicle_soc")
        plugged = ctx.get("vehicle_plugged_in", False)
        export = ctx.get("site_export_w")
        pv = ctx.get("pv_production_w", 0)
        
        self.logger.debug(f"Controller mode: {self.mode}, dynamic_charging: {self.dynamic_charging}")

        if not plugged:
            self.logger.debug("Vehicle not plugged in; ensure stopped")
            if self._charging:
                return {"type": "stop", "reason": "unplugged"}
            return {"type": "none"}

        if soc is not None and soc >= self.max_soc:
            self.logger.info("SOC %s >= max %s; ensure stopped", soc, self.max_soc)
            if self._charging:
                return {"type": "stop", "reason": "soc_cap"}
            return {"type": "none"}

        signal_value = export if export is not None else pv

        # Dynamic charging mode
        if self.mode == "dynamic" and self.dynamic_charging:
            self.logger.debug(f"Dynamic mode active: signal_value={signal_value}W, charging={self._charging}")
            optimal_amps = self.calculate_optimal_amps(signal_value)
            self.logger.debug(f"Calculated optimal_amps: {optimal_amps}A")
            
            if optimal_amps is None:
                # Not enough solar for charging
                if self._charging:
                    if self._enforce_hysteresis(False):
                        return {"type": "stop", "reason": "insufficient_solar"}
                return {"type": "none"}
            else:
                # Enough solar for charging
                if not self._charging:
                    if self._enforce_hysteresis(True):
                        return {"type": "start", "reason": "dynamic_solar_available", "amps": optimal_amps}
                else:
                    # Already charging, adjust amperage if needed
                    current_amps = ctx.get("charge_current_request", self.min_charge_amps)
                    self.logger.debug(f"Dynamic charging check: current={current_amps}A, optimal={optimal_amps}A, solar={signal_value}W")
                    
                    # Only change amperage if moving to a different step
                    if optimal_amps != current_amps:
                        # Check if both are valid steps (avoid changing to/from non-step values)
                        if optimal_amps in self.amp_steps and current_amps in self.amp_steps:
                            self.logger.info(f"Amperage step change: {current_amps}A → {optimal_amps}A (solar: {signal_value}W)")
                            return {"type": "set_amps", "reason": "dynamic_step_adjustment", "amps": optimal_amps}
                        elif optimal_amps in self.amp_steps:
                            # Current is not a step, move to proper step
                            self.logger.info(f"Amperage correction to step: {current_amps}A → {optimal_amps}A (solar: {signal_value}W)")
                            return {"type": "set_amps", "reason": "dynamic_step_correction", "amps": optimal_amps}
                        else:
                            self.logger.debug(f"Amperage change skipped - not a valid step: {current_amps}A → {optimal_amps}A")
                    else:
                        self.logger.debug(f"Amperage already at optimal step: {current_amps}A (solar: {signal_value}W)")
                return {"type": "none"}
        
        # Threshold control (original mode)
        elif self.mode == "threshold":
            if not self._charging and signal_value >= self.start_threshold_w:
                if self._enforce_hysteresis(True):
                    return {"type": "start", "reason": "export_above_start"}
                else:
                    return {"type": "none"}
            if self._charging and signal_value <= self.stop_threshold_w:
                if self._enforce_hysteresis(False):
                    return {"type": "stop", "reason": "export_below_stop"}
                else:
                    return {"type": "none"}
            return {"type": "none"}

        return {"type": "none"}

    def apply_action(self, action: dict, tesla_client, ctx: dict = None):
        t = action.get("type")
        
        # Get context data for logging
        solar_power_w = ctx.get("pv_production_w", 0) if ctx else 0
        tesla_soc = ctx.get("vehicle_soc", 0) if ctx else 0
        tesla_power_w = ctx.get("tesla_power_w", 0) if ctx else 0  # From Tesla charging power
        
        if t == "start":
            self.logger.info("Starting charge (%s)", action.get("reason"))
            if tesla_client.start_charging():
                self._charging = True
                self._last_change_ts = time.time()
                # Start logging session
                self.solar_logger.start_charging_session(solar_power_w, tesla_soc, tesla_power_w)
                
                # Set initial amperage for dynamic mode
                if action.get("amps"):
                    initial_amps = action.get("amps")
                    self.logger.info("Setting initial charge amps to %s", initial_amps)
                    tesla_client.set_charging_amps(initial_amps)
        elif t == "stop":
            self.logger.info("Stopping charge (%s)", action.get("reason"))
            if tesla_client.stop_charging():
                self._charging = False
                self._last_change_ts = time.time()
                # End logging session
                self.solar_logger.end_charging_session(solar_power_w, tesla_soc, tesla_power_w)
        elif t == "set_amps":
            amps = action.get("amps")
            self.logger.info("Setting charge amps to %s", amps)
            tesla_client.set_charging_amps(amps)
        else:
            self.logger.debug("No action")
        
        # Log ongoing charging data (every ~10 seconds)
        if self._charging and ctx:
            now = time.time()
            if now - self._last_log_time >= 10:  # Log every 10 seconds
                interval = int(now - self._last_log_time) if self._last_log_time > 0 else 10
                self.solar_logger.log_charging_sample(solar_power_w, tesla_soc, tesla_power_w, interval)
                self._last_log_time = now
