import logging
import time
from datetime import datetime
from controller import Controller
from clients.solaredge_cloud import SolarEdgeCloudClient
from clients.tesla import TeslaClient
from clients.tesla_hpwc import TeslaHPWCClient
from utils.time_windows import is_daytime

class Scheduler:
    def __init__(self, config: dict):
        self.config = config
        self.logger = logging.getLogger("scheduler")
        self.controller = Controller(self.config)
        self.solar_client = SolarEdgeCloudClient(self.config)
        self.tesla_client = TeslaClient(self.config)
        self.hpwc_client = TeslaHPWCClient(self.config)
        
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
        if now - self._last_call_reset > 86400:
            self._daily_call_count = 0
            self._last_call_reset = now
            self.logger.info("Daily Tesla API call counter reset")
        
        # Check daily call limit
        if self._daily_call_count >= self._max_daily_calls:
            self.logger.warning(f"Daily Tesla API limit reached ({self._daily_call_count}/{self._max_daily_calls})")
            return False
        
        # Check if it's nighttime (no solar, no need to poll frequently)
        daytime_config = self.config.get("control", {}).get("daytime", {})
        if not is_daytime(daytime_config):
            min_night_interval = 21600
            if self._last_charging_power == 0 and time_since_last_poll < min_night_interval:
                self.logger.debug(f"Tesla poll skipped - nighttime and not charging ({time_since_last_poll:.0f}s < {min_night_interval}s)")
                return False
        
        # Always poll if forced or if it's been too long (1 hour max)
        if force_poll or time_since_last_poll > 3600:
            return True
            
        # Don't poll too frequently (minimum 5 minutes)
        if time_since_last_poll < self._min_tesla_poll_interval:
            self.logger.debug(f"Tesla poll skipped - too soon ({time_since_last_poll:.0f}s < {self._min_tesla_poll_interval}s)")
            return False
            
        # If not charging, poll very rarely (every 3 hours)
        if self._last_charging_power == 0:
            should_poll = time_since_last_poll > 10800
            if not should_poll:
                self.logger.debug(f"Tesla poll skipped - not charging ({time_since_last_poll:.0f}s < 10800s)")
            return should_poll
            
        # If charging, calculate expected SOC change
        power_kw = self._last_charging_power / 1000.0
        time_hours = time_since_last_poll / 3600.0
        expected_soc_change = (power_kw * time_hours) / self._battery_capacity_kwh * 100
        
        # Poll if we expect SOC to have changed by 2% or more
        should_poll = expected_soc_change >= 2.0
        if not should_poll:
            self.logger.debug(f"Tesla poll skipped - SOC change too small ({expected_soc_change:.2f}% < 2%)")
        return should_poll

    def _poll_interval(self, context: dict) -> int:
        test_mode = self.config.get("test_mode", False)
        
        if test_mode:
            test_polling = self.config.get("test_polling", {})
            return test_polling.get("poll_seconds", 5)
        
        polling = self.config.get("polling", {})
        fast = polling.get("fast_seconds", 30)
        med = polling.get("medium_seconds", 60)
        
        if context.get("high_production") and self.controller._charging:
            return fast
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

                solar = self.solar_client.get_power()
                
                dev_mode = self.config.get('dev_mode', False)
                solar_kw = solar.get("pv_production_w", 0) / 1000.0
                wake_threshold_percent = self.config.get("tesla", {}).get("wake_threshold_percent", 0.95)
                wake_threshold_kw = self.controller.start_threshold_w / 1000.0 * wake_threshold_percent
                
                should_poll_tesla_solar = (
                    dev_mode or
                    solar_kw >= wake_threshold_kw or
                    self.controller._charging
                )
                
                should_poll_tesla = (should_poll_tesla_solar and self._should_poll_tesla()) or not self._startup_poll_done
                
                # HPWC pre-check: Skip Tesla poll if HPWC reports vehicle not connected
                if should_poll_tesla and self.hpwc_client.enabled:
                    hpwc_connected = self.hpwc_client.is_vehicle_connected()
                    if hpwc_connected is False:  # Explicitly False (not None)
                        self.logger.info("HPWC reports vehicle not connected - skipping Tesla poll (saved API call)")
                        should_poll_tesla = False
                    elif hpwc_connected is True:
                        self.logger.debug("HPWC confirms vehicle connected")
                    # If None (HPWC unavailable), proceed with Tesla poll as normal
                
                if should_poll_tesla:
                    if not self._startup_poll_done:
                        reason = "startup initialization"
                    elif dev_mode:
                        reason = "dev mode enabled"
                    else:
                        reason = "charging active" if self.controller._charging else "solar sufficient"
                    
                    self.logger.debug(f"Polling Tesla ({reason}) - Call #{self._daily_call_count + 1}/{self._max_daily_calls}")
                    
                    try:
                        vehicle = self.tesla_client.get_state(wake_if_needed=True)
                        plugged_in = vehicle.get("plugged_in", False)
                        tesla_soc = vehicle.get("soc", 0)
                        charging_state = vehicle.get("charging_state", "Unknown")
                        
                        self._last_tesla_poll = time.time()
                        self._last_tesla_data = vehicle
                        self._last_charging_power = vehicle.get("charger_power", 0) * 1000
                        self._daily_call_count += 1
                        self._startup_poll_done = True
                        
                    except Exception as e:
                        self.logger.error(f"Failed to get Tesla vehicle state: {e}")
                        vehicle = {"charging_state": "Unknown", "plugged_in": False, "soc": 0}
                        plugged_in = False
                        tesla_soc = 0
                        charging_state = "Unknown"
                        self._startup_poll_done = True
                    
                elif should_poll_tesla_solar and self._last_tesla_data:
                    self.logger.debug("Using cached Tesla data to reduce API costs")
                    vehicle = self._last_tesla_data
                    plugged_in = vehicle.get("plugged_in", False)
                    tesla_soc = vehicle.get("soc", 0)
                    charging_state = vehicle.get("charging_state", "Unknown")
                else:
                    self.logger.debug(f"Solar too low ({solar_kw:.2f}kW < {wake_threshold_kw:.2f}kW) and not charging - not polling Tesla")
                    vehicle = {"charging_state": "Sleeping", "plugged_in": False, "soc": 0}
                    plugged_in = False
                    tesla_soc = 0
                    charging_state = "Sleeping"
                
                export_kw = solar.get("site_export_w")
                if export_kw:
                    export_kw = export_kw / 1000.0
                shift_state = vehicle.get("shift_state")
                speed = vehicle.get("speed")

                context = {
                    "pv_production_w": solar.get("pv_production_w") or 0,
                    "site_export_w": solar.get("site_export_w"),
                    "vehicle_plugged_in": plugged_in,
                    "vehicle_soc": tesla_soc,
                    "tesla_power_w": vehicle.get("charger_power", 0) * 1000,
                    "charge_current_request": vehicle.get("charge_current_request", 0),
                    "charger_voltage": vehicle.get("charger_voltage"),
                }
                context["high_production"] = (context.get("site_export_w") or 0) > self.controller.start_threshold_w

                action = self.controller.decide_action(context)
                
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
                
                if charging_state == "Sleeping":
                    status = "Sleeping"
                    wake_thresh = self.controller.start_threshold_w / 1000.0 * self.config.get('tesla', {}).get('wake_threshold_percent', 0.95)
                    if solar_kw >= wake_thresh:
                        display_action = f"Solar OK ({solar_kw:.3f}kW >= {wake_thresh:.2f}kW) - Vehicle sleeping"
                    else:
                        display_action = f"Low Solar ({solar_kw:.3f}kW < {wake_thresh:.2f}kW)"
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

                self.controller.apply_action(action, self.tesla_client, context)
                
                action_type = action.get("type")
                action_reason = action.get("reason", "")
                
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

                export_str = f"(+{export_kw:.3f}kW)" if export_kw else ""
                vehicle_display = f" {vehicle_state_str:<11}" if vehicle_state_str else f" {'':11}"
                soc_display = "  --% " if charging_state == "Sleeping" else f"{tesla_soc:>3d}%"
                
                print(f"{now}     {solar_kw:>7.3f}kW {export_str:<12} {soc_display}{vehicle_display}     {status:<10} {display_action:<25} {control_status}")

                sleep_s = self._poll_interval(context)
                time.sleep(sleep_s)

            except Exception:
                self.logger.exception("Error in scheduler loop; backing off")
                time.sleep(10)
