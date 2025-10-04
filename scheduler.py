import logging
import time
from datetime import datetime
from controller import Controller
from clients.solaredge_cloud import SolarEdgeCloudClient
from clients.solaredge_modbus import SolarEdgeModbusClient
from clients.tesla import TeslaClient
from utils.time_windows import is_daytime


class Scheduler:
    def __init__(self, config: dict):
        self.config = config
        self.logger = logging.getLogger("scheduler")
        self.controller = Controller(config)
        self.solar_client = self._init_solar_client(config)
        self.tesla_client = TeslaClient(config)

    def _init_solar_client(self, config: dict):
        source = config.get("solaredge", {}).get("source", "cloud")
        if source == "modbus":
            return SolarEdgeModbusClient(config)
        return SolarEdgeCloudClient(config)

    def _poll_interval(self, context: dict) -> int:
        # Check if test mode is enabled
        test_mode = self.config.get("test_mode", False)
        
        if test_mode:
            test_polling = self.config.get("test_polling", {})
            return test_polling.get("poll_seconds", 5)  # Default 5-second polling in test mode
        
        # Normal polling logic
        polling = self.config.get("polling", {})
        fast = polling.get("fast_seconds", 30)
        med = polling.get("medium_seconds", 60)
        slow = polling.get("slow_seconds", 120)
        
        if context.get("high_production"):
            if self.controller._charging:
                return fast
            return med
        return med

    def run(self, stop_event):
        dry_run = self.config.get("dry_run", True)
        test_mode = self.config.get("test_mode", False)
        
        if test_mode:
            self.logger.info("Scheduler started (dry_run=%s, TEST_MODE=ON)", dry_run)
        else:
            self.logger.info("Scheduler started (dry_run=%s)", dry_run)
        
        # Print header for monitor display
        if test_mode:
            print("\n🧪⚡ Solar Charger System - TEST MODE")
            print("=" * 95)
            print("Time        Solar (kW)  Tesla (%)  Vehicle     Status      Action                    Control")
            print("-" * 95)
        else:
            print("\n🌞⚡ Solar Charger System - Live Control")
            print("=" * 95)
            print("Time        Solar (kW)  Tesla (%)  Vehicle     Status      Action                    Control")
            print("-" * 95)
        
        while not stop_event.is_set():
            try:
                # Check daytime restrictions (skip in test mode)
                if not test_mode:
                    daytime = is_daytime(self.config)
                    if not daytime and self.config.get("polling", {}).get("night_sleep", True):
                        self.logger.info("Outside daytime window - sleeping (night_sleep=true)")
                        time.sleep(self._poll_interval({}))
                        continue
                else:
                    # Test mode - ignore daytime restrictions
                    self.logger.debug("Test mode: ignoring daytime restrictions")
                # Get current time
                now = datetime.now().strftime("%H:%M:%S")

                # Get data
                solar = self.solar_client.get_power()
                
                # Get Tesla data - poll if solar is high enough OR if we think Tesla is charging
                solar_kw = solar.get("pv_production_w", 0) / 1000.0
                wake_threshold_percent = self.config.get("tesla", {}).get("wake_threshold_percent", 95)  # Default 90%
                wake_threshold_kw = self.controller.start_threshold_w / 1000.0 * wake_threshold_percent
                
                # Check if we should poll Tesla
                should_poll_tesla = (
                    solar_kw >= wake_threshold_kw or  # Solar is high enough
                    self.controller._charging  # Or we think Tesla is currently charging
                )
                
                if should_poll_tesla:
                    # Poll Tesla (solar high enough or charging active)
                    reason = "charging active" if self.controller._charging else "solar sufficient"
                    self.logger.debug(f"Polling Tesla ({reason})")
                    vehicle = self.tesla_client.get_state(wake_if_needed=True)
                    plugged_in = vehicle.get("plugged_in", False)
                    tesla_soc = vehicle.get("soc", 0)
                    charging_state = vehicle.get("charging_state", "Unknown")
                else:
                    # Solar too low and not charging - don't poll Tesla at all (let it sleep)
                    self.logger.debug(f"Solar too low ({solar_kw:.2f}kW < {wake_threshold_kw:.2f}kW) and not charging - not polling Tesla")
                    vehicle = {"charging_state": "Sleeping", "plugged_in": False, "soc": 0}
                    plugged_in = False
                    tesla_soc = 0
                    charging_state = "Sleeping"
                
                # Parse data for display
                export_kw = solar.get("site_export_w")
                if export_kw:
                    export_kw = export_kw / 1000.0
                shift_state = vehicle.get("shift_state")
                speed = vehicle.get("speed")

                # Build context for controller
                context = {
                    "pv_production_w": solar.get("pv_production_w") or 0,
                    "site_export_w": solar.get("site_export_w"),
                    "vehicle_plugged_in": plugged_in,
                    "vehicle_soc": tesla_soc,
                    "tesla_power_w": vehicle.get("charger_power", 0) * 1000,  # Convert kW to W
                }
                context["high_production"] = (context.get("site_export_w") or 0) > self.controller.start_threshold_w

                # Make control decision
                action = self.controller.decide_action(context)
                
                # Determine vehicle state display (only if we have data)
                vehicle_state_str = ""
                if speed and speed > 0:
                    vehicle_state_str = f"Driving {speed}mph"
                elif shift_state == "P":
                    vehicle_state_str = "Parked"
                elif shift_state == "D":
                    vehicle_state_str = "Drive"
                elif shift_state == "R":
                    vehicle_state_str = "Reverse"
                elif shift_state == "N":
                    vehicle_state_str = "Neutral"
                # If shift_state and speed are None/null, vehicle_state_str stays empty
                
                # Determine display status and action
                if charging_state == "Sleeping":
                    status = "Sleeping"
                    display_action = f"Low Solar ({solar_kw:.3f}kW < {(self.controller.start_threshold_w / 1000.0 * self.config.get('tesla', {}).get('wake_threshold_percent', 0.95)):.2f}kW)"
                elif not plugged_in:
                    status = "Unplugged"
                    display_action = "Waiting"
                elif charging_state == "Charging":
                    status = "Charging"
                    display_action = "Active"
                elif charging_state in ["Stopped", "Complete"]:
                    if solar_kw * 1000 >= self.config.get("control", {}).get("start_export_watts", 100):
                        status = "Ready"
                        display_action = "Should Start"
                    else:
                        status = "Plugged"
                        threshold_kw = self.config.get("control", {}).get("start_export_watts", 100) / 1000.0
                        display_action = f"Low Solar ({solar_kw:.3f}kW < {threshold_kw:.1f}kW)"
                else:
                    status = charging_state
                    display_action = "Monitoring"

                # Apply the control action (pass context for logging)
                control_result = self.controller.apply_action(action, self.tesla_client, context)
                
                # Determine control status
                action_type = action.get("type") if isinstance(action, dict) else action
                action_reason = action.get("reason", "") if isinstance(action, dict) else ""
                
                if action_type == "start":
                    control_status = "🟢 START" if not dry_run else "🟢 [DRY] START"
                    if action_reason:
                        control_status += f" ({action_reason})"
                elif action_type == "stop":
                    control_status = "🔴 STOP" if not dry_run else "🔴 [DRY] STOP"
                    if action_reason:
                        control_status += f" ({action_reason})"
                elif action_type == "none":
                    control_status = "⚪ No Action"
                elif action_type == "set_amps":
                    amps = action.get("amps", "?")
                    control_status = f"⚙️ Set {amps}A" if not dry_run else f"⚙️ [DRY] Set {amps}A"
                else:
                    control_status = f"⚙️ {action_type or 'Unknown'}"

                # Format export info
                export_str = f"(+{export_kw:.3f}kW)" if export_kw else ""
                
                # Format vehicle state (always reserve space for alignment)
                if vehicle_state_str:
                    vehicle_display = f" {vehicle_state_str:<11}"
                else:
                    vehicle_display = f" {'':11}"  # Empty space to maintain alignment
                
                # Format Tesla SOC display (show dash when sleeping)
                if charging_state == "Sleeping":
                    soc_display = "  --%"
                else:
                    soc_display = f"{tesla_soc:>3d}%"
                
                # Print status line
                print(f"{now}     {solar_kw:>7.3f}kW {export_str:<12} {soc_display}{vehicle_display}     {status:<10} {display_action:<25} {control_status}")

                sleep_s = self._poll_interval(context)
                time.sleep(sleep_s)

            except Exception:
                self.logger.exception("Error in scheduler loop; backing off")
                time.sleep(10)
