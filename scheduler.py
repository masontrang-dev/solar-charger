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
        self.controller = Controller(self.config)
        self.solar_client = SolarEdgeCloudClient(self.config)
        self.tesla_client = TeslaClient(self.config)
        
        # Smart Tesla polling to reduce API costs (5000 calls/month budget)
        self._last_tesla_poll = 0
        self._last_tesla_data = {}
        self._min_tesla_poll_interval = 300  # Minimum 5 minutes between Tesla polls
        self._last_charging_power = 0
        self._battery_capacity_kwh = 75  # Approximate Tesla battery capacity
        self._max_daily_calls = 50   # Very conservative daily limit (1500/month + buffer)
        self._daily_call_count = 0
        self._last_call_reset = time.time()
        self._startup_poll_done = False  # Track if we've done initial startup poll
    
    def _should_poll_tesla(self, force_poll=False) -> bool:
        """Smart Tesla polling to reduce API costs (5000/month budget)"""
        now = time.time()
        time_since_last_poll = now - self._last_tesla_poll
        
        # Always poll on startup to initialize system
        if not self._startup_poll_done:
            self.logger.info("Startup Tesla poll - initializing system data")
            return True
        
        # Reset daily call counter at midnight
        if now - self._last_call_reset > 86400:  # 24 hours
            self._daily_call_count = 0
            self._last_call_reset = now
            self.logger.info(f"Daily Tesla API call counter reset")
        
        # Check daily call limit
        if self._daily_call_count >= self._max_daily_calls:
            self.logger.warning(f"Daily Tesla API limit reached ({self._daily_call_count}/{self._max_daily_calls})")
            return False
        
        # Check if it's nighttime (no solar, no need to poll frequently)
        daytime_config = self.config.get("control", {}).get("daytime", {})
        if not is_daytime(daytime_config):
            # At night, only poll every 6 hours unless charging
            min_night_interval = 21600  # 6 hours at night
            if self._last_charging_power == 0 and time_since_last_poll < min_night_interval:
                self.logger.debug(f"Tesla poll skipped - nighttime and not charging ({time_since_last_poll:.0f}s < {min_night_interval}s)")
                return False
        
        # Always poll if forced or if it's been too long (1 hour max)
        if force_poll or time_since_last_poll > 3600:  # 1 hour max
            return True
            
        # Don't poll too frequently (minimum 5 minutes)
        if time_since_last_poll < self._min_tesla_poll_interval:
            self.logger.debug(f"Tesla poll skipped - too soon ({time_since_last_poll:.0f}s < {self._min_tesla_poll_interval}s)")
            return False
            
        # If not charging, poll very rarely (every 3 hours)
        if self._last_charging_power == 0:
            should_poll = time_since_last_poll > 10800  # 3 hours when not charging
            if not should_poll:
                self.logger.debug(f"Tesla poll skipped - not charging ({time_since_last_poll:.0f}s < 10800s)")
            return should_poll
            
        # If charging, calculate expected SOC change
        # SOC change = (power_kw * time_hours) / battery_capacity_kwh * 100
        power_kw = self._last_charging_power / 1000.0
        time_hours = time_since_last_poll / 3600.0
        expected_soc_change = (power_kw * time_hours) / self._battery_capacity_kwh * 100
        
        # Poll if we expect SOC to have changed by 2% or more (more conservative)
        should_poll = expected_soc_change >= 2.0
        if not should_poll:
            self.logger.debug(f"Tesla poll skipped - SOC change too small ({expected_soc_change:.2f}% < 2%)")
        return should_poll

    def _init_solar_client(self, config: dict):
        source = config.get("solaredge", {}).get("source", "cloud")
        if source == "modbus":
            return SolarEdgeModbusClient(config)

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
                
                # Check if we should poll Tesla (solar-based + smart caching)
                should_poll_tesla_solar = (
                    solar_kw >= wake_threshold_kw or  # Solar is high enough
                    self.controller._charging  # Or we think Tesla is currently charging
                )
                
                # Apply smart polling logic to reduce API costs
                # Always poll on startup regardless of solar conditions
                should_poll_tesla = (should_poll_tesla_solar and self._should_poll_tesla()) or not self._startup_poll_done
                
                if should_poll_tesla:
                    # Poll Tesla (solar high enough or charging active or startup)
                    if not self._startup_poll_done:
                        reason = "startup initialization"
                    else:
                        reason = "charging active" if self.controller._charging else "solar sufficient"
                    
                    self.logger.debug(f"Polling Tesla ({reason}) - Call #{self._daily_call_count + 1}/{self._max_daily_calls}")
                    
                    try:
                        vehicle = self.tesla_client.get_state(wake_if_needed=True)
                        plugged_in = vehicle.get("plugged_in", False)
                        tesla_soc = vehicle.get("soc", 0)
                        charging_state = vehicle.get("charging_state", "Unknown")
                        
                        # Update cache and call counter
                        self._last_tesla_poll = time.time()
                        self._last_tesla_data = vehicle
                        self._last_charging_power = vehicle.get("charger_power", 0) * 1000  # Convert kW to W
                        self._daily_call_count += 1
                        self._startup_poll_done = True  # Mark startup poll as complete
                        
                    except Exception as e:
                        self.logger.error(f"Failed to get Tesla vehicle state: {e}")
                        # Use default values if Tesla polling fails
                        vehicle = {"charging_state": "Unknown", "plugged_in": False, "soc": 0}
                        plugged_in = False
                        tesla_soc = 0
                        charging_state = "Unknown"
                        # Still mark startup as done to avoid infinite retries
                        self._startup_poll_done = True
                    
                elif should_poll_tesla_solar and self._last_tesla_data:
                    # Use cached data to avoid API call
                    self.logger.debug("Using cached Tesla data to reduce API costs")
                    vehicle = self._last_tesla_data
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
                    "charge_current_request": vehicle.get("charge_current_request", 0),  # Current Tesla amperage
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
