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

    def _poll_interval(self, context: dict) -> float:
        polling = self.config.get("polling", {})
        fast = float(polling.get("fast_seconds", 20))
        med = float(polling.get("medium_seconds", 60))
        slow = float(polling.get("slow_seconds", 300))

        if not is_daytime(self.config):
            return slow
        if context.get("vehicle_plugged_in"):
            if context.get("high_production"):
                return fast
            return med
        return med

    def run(self, stop_event):
        dry_run = self.config.get("dry_run", True)
        self.logger.info("Scheduler started (dry_run=%s)", dry_run)
        
        # Print header for monitor display
        print("\n🌞⚡ Solar Charger System - Live Control")
        print("=" * 95)
        print("Time        Solar (kW)  Tesla (%)  Vehicle     Status      Action                    Control")
        print("-" * 95)
        
        while not stop_event.is_set():
            try:
                daytime = is_daytime(self.config)
                if not daytime and self.config.get("polling", {}).get("night_sleep", True):
                    self.logger.debug("Nighttime sleep; skipping poll")
                    time.sleep(self._poll_interval({}))
                    continue

                # Get current time
                now = datetime.now().strftime("%H:%M:%S")

                # Get data
                solar = self.solar_client.get_power()
                vehicle = self.tesla_client.get_state()

                # Parse data for display
                solar_kw = solar.get("pv_production_w", 0) / 1000.0
                export_kw = solar.get("site_export_w")
                if export_kw:
                    export_kw = export_kw / 1000.0
                
                tesla_soc = vehicle.get("soc", 0)
                plugged_in = vehicle.get("plugged_in", False)
                charging_state = vehicle.get("charging_state", "Unknown")
                shift_state = vehicle.get("shift_state")
                speed = vehicle.get("speed")

                # Build context for controller
                context = {
                    "pv_production_w": solar.get("pv_production_w") or 0,
                    "site_export_w": solar.get("site_export_w"),
                    "vehicle_plugged_in": plugged_in,
                    "vehicle_soc": tesla_soc,
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
                if not plugged_in:
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

                # Apply the control action
                control_result = self.controller.apply_action(action, self.tesla_client)
                
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
                
                # Print status line
                print(f"{now}     {solar_kw:>7.3f}kW {export_str:<12} {tesla_soc:>3d}%{vehicle_display}     {status:<10} {display_action:<25} {control_status}")

                sleep_s = self._poll_interval(context)
                time.sleep(sleep_s)

            except Exception:
                self.logger.exception("Error in scheduler loop; backing off")
                time.sleep(10)
