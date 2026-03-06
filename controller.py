import logging
import time
from utils.solar_logger import SolarChargingLogger


class Controller:
    def __init__(self, config: dict):
        self.config = config
        self.logger = logging.getLogger("controller")
        ctrl = config.get("control", {})
        
        test_mode = config.get("test_mode", False)
        
        if test_mode:
            self.logger.info("TEST MODE ENABLED - Using test configuration values")
            test_ctrl = config.get("test_control", {})
            self.start_threshold_w = int(test_ctrl.get("start_export_watts", 200))
            self.stop_threshold_w = int(test_ctrl.get("stop_export_watts", 150))
            self.min_on = int(test_ctrl.get("min_on_seconds", 30))
            self.min_off = int(test_ctrl.get("min_off_seconds", 30))
        else:
            self.start_threshold_w = int(ctrl.get("start_export_watts", 3500))
            self.stop_threshold_w = int(ctrl.get("stop_export_watts", 1500))
            self.min_on = int(ctrl.get("min_on_seconds", 300))
            self.min_off = int(ctrl.get("min_off_seconds", 300))
        
        self.max_soc = int(ctrl.get("max_soc", 80))
        
        self.dynamic_charging = ctrl.get("dynamic_charging", {}).get("enabled", False)
        self.min_dynamic_watts = int(ctrl.get("dynamic_charging", {}).get("min_watts", 1200))
        self.min_charge_amps = int(ctrl.get("dynamic_charging", {}).get("min_amps", 5))
        self.max_charge_amps = int(ctrl.get("dynamic_charging", {}).get("max_amps", 48))
        self.mode = ctrl.get("mode", "threshold")
        
        if test_mode:
            self.logger.info(f"TEST MODE: Dynamic charging enabled: {self.dynamic_charging}, Mode: {self.mode}")

        self._charging = False
        self._last_change_ts = 0.0
        self._last_set_amps = None
        
        self.solar_logger = SolarChargingLogger()
        self._last_log_time = 0.0
    
    def calculate_optimal_amps(self, solar_power_w: int, house_load_w: int = None, actual_voltage: int = None) -> int:
        """Calculate optimal charging amperage based on available solar power.
        
        Args:
            solar_power_w: Solar power in watts
            house_load_w: House baseline load in watts (optional)
            actual_voltage: Actual charging voltage from vehicle (optional, uses config if not provided)
        """
        if not self.dynamic_charging:
            return None
        
        if house_load_w is None:
            house_load_w = self.config.get("control", {}).get("house_baseline_w", 400)
            self.logger.debug(f"Using house baseline: {house_load_w}W")
            
        available_power_w = solar_power_w - house_load_w
        
        # Use actual voltage from vehicle if available, otherwise fall back to config
        config_voltage = self.config.get("tesla", {}).get("charging_voltage", 240)
        charging_voltage = actual_voltage if actual_voltage is not None else config_voltage
        
        if actual_voltage is not None:
            self.logger.debug(f"Using actual voltage from vehicle: {actual_voltage}V (config: {config_voltage}V)")
        else:
            self.logger.debug(f"Using config voltage: {config_voltage}V (no vehicle data available)")
        
        min_power_needed = self.min_charge_amps * charging_voltage
        
        if available_power_w < min_power_needed:
            self.logger.debug(f"Available power ({available_power_w}W) insufficient for minimum {self.min_charge_amps}A at {charging_voltage}V (need {min_power_needed}W)")
            return None
            
        calculated_amps = available_power_w / charging_voltage
        optimal_amps = int(calculated_amps)
        optimal_amps = max(self.min_charge_amps, min(optimal_amps, self.max_charge_amps))
        
        self.logger.debug(f"Solar: {solar_power_w}W, House: {house_load_w}W, Available: {available_power_w}W, Voltage: {charging_voltage}V → {optimal_amps}A")
        
        return optimal_amps

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

        if self.mode == "dynamic" and self.dynamic_charging:
            house_baseline = self.config.get("control", {}).get("house_baseline_w", 400)
            # Get actual voltage from vehicle data if available
            actual_voltage = ctx.get("charger_voltage")
            config_voltage = self.config.get("tesla", {}).get("charging_voltage", 240)
            display_voltage = actual_voltage if actual_voltage is not None else config_voltage
            
            self.logger.info(f"Dynamic mode: Solar={signal_value}W, House={house_baseline}W, Available={signal_value-house_baseline}W, Voltage={display_voltage}V")
            optimal_amps = self.calculate_optimal_amps(signal_value, actual_voltage=actual_voltage)
            if optimal_amps:
                self.logger.info(f"Calculated optimal amperage: {optimal_amps}A (would draw {optimal_amps * display_voltage}W)")
            else:
                self.logger.info(f"Insufficient solar for minimum {self.min_charge_amps}A charging")
            
            if optimal_amps is None:
                if self._charging:
                    if self._enforce_hysteresis(False):
                        return {"type": "stop", "reason": "insufficient_solar"}
                return {"type": "none"}
            else:
                if not self._charging:
                    if self._enforce_hysteresis(True):
                        return {"type": "start", "reason": "dynamic_solar_available", "amps": optimal_amps}
                else:
                    current_amps = self._last_set_amps if self._last_set_amps is not None else ctx.get("charge_current_request", self.min_charge_amps)
                    self.logger.debug(f"Dynamic charging check: current={current_amps}A, optimal={optimal_amps}A, solar={signal_value}W")
                    
                    if optimal_amps != current_amps:
                        amp_diff = abs(optimal_amps - current_amps)
                        if amp_diff >= 1:
                            self.logger.info(f"Amperage adjustment: {current_amps}A → {optimal_amps}A (solar: {signal_value}W)")
                            return {"type": "set_amps", "reason": "dynamic_adjustment", "amps": optimal_amps}
                        else:
                            self.logger.debug(f"Amperage change too small ({amp_diff}A), keeping at {current_amps}A")
                    else:
                        self.logger.debug(f"Amperage already optimal: {current_amps}A (solar: {signal_value}W)")
                return {"type": "none"}
        
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
        
        solar_power_w = ctx.get("pv_production_w", 0) if ctx else 0
        tesla_soc = ctx.get("vehicle_soc", 0) if ctx else 0
        tesla_power_w = ctx.get("tesla_power_w", 0) if ctx else 0
        
        if t == "start":
            self.logger.info("Starting charge (%s)", action.get("reason"))
            if tesla_client.start_charging():
                self._charging = True
                self._last_change_ts = time.time()
                self.solar_logger.start_charging_session(solar_power_w, tesla_soc, tesla_power_w)
                
                if action.get("amps"):
                    initial_amps = action.get("amps")
                    current_amps = ctx.get("charge_current_request") if ctx else None
                    if current_amps != initial_amps:
                        self.logger.info("Setting initial charge amps to %s", initial_amps)
                        tesla_client.set_charging_amps(initial_amps)
                    else:
                        self.logger.info("Amperage already at %s, skipping set command", initial_amps)
                    self._last_set_amps = initial_amps
        elif t == "stop":
            self.logger.info("Stopping charge (%s)", action.get("reason"))
            if tesla_client.stop_charging():
                self._charging = False
                self._last_change_ts = time.time()
                self._last_set_amps = None
                self.solar_logger.end_charging_session(solar_power_w, tesla_soc, tesla_power_w)
        elif t == "set_amps":
            amps = action.get("amps")
            tesla_client.set_charging_amps(amps)
            self._last_set_amps = amps
        else:
            self.logger.debug("No action")
        
        if self._charging and ctx:
            now = time.time()
            if now - self._last_log_time >= 10:
                interval = int(now - self._last_log_time) if self._last_log_time > 0 else 10
                self.solar_logger.log_charging_sample(solar_power_w, tesla_soc, tesla_power_w, interval)
                self._last_log_time = now
