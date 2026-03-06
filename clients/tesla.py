import json
import logging
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

class TeslaClient:
    BASE_URL = "https://fleet-api.prd.na.vn.cloud.tesla.com"
    PROXY_URL = "https://localhost:8080"  # Tesla HTTP proxy
    
    def __init__(self, config: dict):
        self.config = config
        self.logger = logging.getLogger("tesla")
        
        tesla_config = config.get("tesla", {})
        api_config = tesla_config.get("api", {})
        
        self.vin = tesla_config.get("vehicle_vin")
        if not self.vin:
            raise ValueError("Tesla VIN not configured")
        
        self.dry = config.get("dry_run", False)
        
        self.api_type = api_config.get("type", "fleet")
        if self.api_type == "fleet":
            self.BASE_URL = "https://fleet-api.prd.na.vn.cloud.tesla.com"
        else:
            self.BASE_URL = "https://owner-api.teslamotors.com"
        
        self.access_token = api_config.get("access_token")
        
        if not self.access_token:
            raise ValueError("Tesla access token not configured")
    
    def _headers(self):
        """Get HTTP headers for Tesla API requests"""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((requests.exceptions.RequestException, json.JSONDecodeError))
    )
    def _get(self, path: str):
        """Make a GET request to the Tesla API with retry"""
        url = f"{self.BASE_URL}{path}"
        self.logger.debug(f"Making GET request to {url}")
        response = requests.get(url, headers=self._headers(), timeout=10)
        
        try:
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError:
            self.logger.error(f"Tesla API error ({response.status_code}): {response.text}")
            raise
        except json.JSONDecodeError:
            self.logger.error(f"Failed to parse Tesla API response: {response.text}")
            raise
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((requests.exceptions.RequestException, json.JSONDecodeError))
    )
    def _post(self, path: str, data: dict = None):
        """Make a POST request to the Tesla API with retry"""
        if "/command/" in path:
            url = f"{self.PROXY_URL}{path}"
            verify_ssl = False
        else:
            url = f"{self.BASE_URL}{path}"
            verify_ssl = True
        
        self.logger.debug(f"Making POST request to {url}")
        response = requests.post(
            url, 
            headers=self._headers(), 
            json=data or {}, 
            timeout=10,
            verify=verify_ssl
        )
        
        try:
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError:
            self.logger.error(f"Tesla API error ({response.status_code}): {response.text}")
            raise
        except json.JSONDecodeError:
            self.logger.error(f"Failed to parse Tesla API response: {response.text}")
            raise

    def get_state(self, wake_if_needed: bool = True) -> dict:
        if not self.access_token or not self.vin:
            self.logger.debug("No Tesla access token or VIN; returning placeholder data")
            return {
                "plugged_in": True,  # assume plugged for dry-run demo
                "soc": 60,
            }
        
        try:
            self.logger.debug("Getting vehicle list from Tesla API...")
            vehicles_data = self._get("/api/1/vehicles")
            vehicles = vehicles_data.get("response", [])
            
            vehicle_info = None
            for v in vehicles:
                if v.get("vin") == self.vin:
                    vehicle_info = v
                    break
            
            if not vehicle_info:
                raise Exception(f"Vehicle with VIN {self.vin} not found")
            
            vehicle_state = vehicle_info.get("state", "unknown")
            self.logger.debug(f"Vehicle state: {vehicle_state}")
            
            # If vehicle is asleep/offline and we don't want to wake it
            if vehicle_state in ["asleep", "offline"] and not wake_if_needed:
                self.logger.debug(f"Vehicle is {vehicle_state}, not waking")
                return {
                    "vehicle_state": vehicle_state,
                    "plugged_in": False,  # Unknown, assume not plugged
                    "soc": 0,
                    "charging_state": "Sleeping",
                }
            
            # If vehicle is asleep/offline but we need to wake it
            if vehicle_state in ["asleep", "offline"] and wake_if_needed:
                self.logger.info(f"Vehicle is {vehicle_state}, attempting to wake...")
                if not self.wake_vehicle():
                    return {
                        "vehicle_state": vehicle_state,
                        "plugged_in": False,
                        "soc": 0,
                        "charging_state": "Sleeping",
                    }
            
            data = self._get(f"/api/1/vehicles/{self.vin}/vehicle_data")
            vehicle_data = data.get("response", {})
            
            charge_state = vehicle_data.get("charge_state", {})
            vehicle_state_data = vehicle_data.get("vehicle_state", {})
            drive_state = vehicle_data.get("drive_state", {})
            
            return {
                "plugged_in": charge_state.get("charging_state") != "Disconnected",
                "soc": charge_state.get("battery_level", 0),
                "charging_state": charge_state.get("charging_state", "Unknown"),
                "charge_current_request": charge_state.get("charge_current_request", 0),
                "charge_current_request_max": charge_state.get("charge_current_request_max", 0),
                "charger_actual_current": charge_state.get("charger_actual_current", 0),
                "charger_voltage": charge_state.get("charger_voltage", 0),
                "charger_power": (charge_state.get("charger_actual_current", 0) * charge_state.get("charger_voltage", 0) / 1000.0),
                "charger_power_raw": charge_state.get("charger_power", 0),
                "charge_rate": charge_state.get("charge_rate", 0),
                "time_to_full_charge": charge_state.get("time_to_full_charge", 0),
                "charge_limit_soc": charge_state.get("charge_limit_soc", 80),
                "charge_port_door_open": charge_state.get("charge_port_door_open", False),
                "charge_port_latch": charge_state.get("charge_port_latch", "Unknown"),
                "vehicle_state": vehicle_state_data.get("car_version"),
                "shift_state": drive_state.get("shift_state"),
                "speed": drive_state.get("speed"),
                "location": {
                    "latitude": drive_state.get("latitude"),
                    "longitude": drive_state.get("longitude"),
                }
            }
        except Exception as e:
            self.logger.error(f"Failed to get Tesla vehicle state: {e}")
            return {"plugged_in": False, "soc": 0, "charge_state": "Error", "vehicle_state": "error"}
    
    def wake_vehicle(self) -> bool:
        """Wake up the vehicle"""
        if not self.access_token or not self.vin:
            self.logger.error("No Tesla access token or VIN for wake command")
            return False
        
        try:
            self.logger.info("Sending wake command to vehicle...")
            data = self._post(f"/api/1/vehicles/{self.vin}/wake_up")
            
            response = data.get("response", {})
            state = response.get("state", "")
            
            if state == "online":
                self.logger.info("Vehicle woke up successfully")
                return True
            elif state in ["asleep", "offline"]:
                self.logger.warning(f"Wake command sent but vehicle still {state}")
                return False
            else:
                # If we got a successful response but state is unclear/empty,
                # the vehicle is likely already awake
                self.logger.info("Wake command successful (vehicle may already be awake)")
                return True
                
        except Exception as e:
            self.logger.error(f"Failed to wake vehicle: {e}")
            return False
    
    def start_charging(self) -> bool:
        if self.dry:
            self.logger.info("[DRY-RUN] Would start charging for VIN %s", self.vin)
            return True
        
        if not self.access_token or not self.vin:
            self.logger.error("Cannot start charging: missing access token or VIN")
            return False
        
        try:
            self._post(f"/api/1/vehicles/{self.vin}/command/charge_start")
            self.logger.info("Started charging for VIN %s", self.vin)
            return True
        except Exception as e:
            error_str = str(e).lower()
            if "vehicle_command" in error_str or "signed_command" in error_str or "unauthorized" in error_str:
                self.logger.error("Tesla deprecated simple REST commands in Oct 2023. Vehicle commands now require Tesla Vehicle Command Protocol with cryptographic keys.")
                self.logger.error("Your system can read vehicle data but cannot send commands without implementing the new protocol.")
                return False
            elif "offline or asleep" in error_str or "unavailable" in error_str:
                self.logger.info("Vehicle asleep/unavailable, attempting wake sequence...")
                return self._wake_and_retry_command("charge_start")
            else:
                self.logger.error("Failed to start charging: %s", e)
            return False

    def _wake_and_retry_command(self, command: str, max_attempts: int = 3) -> bool:
        """Wake vehicle and retry command with multiple attempts"""
        import time
        
        for attempt in range(max_attempts):
            try:
                self.logger.info(f"Wake attempt {attempt + 1}/{max_attempts}...")
                
                try:
                    self._post(f"/api/1/vehicles/{self.vin}/command/wake_up")
                    self.logger.info("Wake command sent via proxy, waiting...")
                except Exception as wake_e:
                    self.logger.warning(f"Proxy wake command failed: {wake_e}")
                    try:
                        wake_url = f"{self.BASE_URL}/api/1/vehicles/{self.vin}/wake_up"
                        response = requests.post(wake_url, headers=self._headers(), timeout=10)
                        response.raise_for_status()
                        self.logger.info("Direct Fleet API wake command sent, waiting...")
                    except Exception as direct_wake_e:
                        self.logger.warning(f"Direct wake also failed: {direct_wake_e}, trying command anyway...")
                
                wait_time = 10 + (attempt * 5)
                self.logger.info(f"Waiting {wait_time} seconds for vehicle to wake...")
                time.sleep(wait_time)
                
                try:
                    state_response = self._get(f"/api/1/vehicles/{self.vin}/vehicle_data")
                    if state_response.get("response"):
                        self.logger.info("Vehicle is now awake and responding")
                except Exception as state_e:
                    self.logger.warning(f"Cannot verify wake state: {state_e}")
                
                if command == "charge_start":
                    self._post(f"/api/1/vehicles/{self.vin}/command/charge_start")
                    self.logger.info(f"Successfully started charging after wake attempt {attempt + 1}")
                    return True
                elif command == "charge_stop":
                    self._post(f"/api/1/vehicles/{self.vin}/command/charge_stop")
                    self.logger.info(f"Successfully stopped charging after wake attempt {attempt + 1}")
                    return True
                    
            except Exception as retry_e:
                if "offline or asleep" in str(retry_e).lower() or "unavailable" in str(retry_e).lower():
                    self.logger.warning(f"Attempt {attempt + 1} failed - vehicle still asleep: {retry_e}")
                    if attempt < max_attempts - 1:
                        continue
                else:
                    self.logger.error(f"Command failed for different reason: {retry_e}")
                    return False
        
        self.logger.error(f"Failed to wake vehicle after {max_attempts} attempts")
        return False

    def stop_charging(self) -> bool:
        if self.dry:
            self.logger.info("[DRY-RUN] Would stop charging for VIN %s", self.vin)
            return True
        
        if not self.access_token or not self.vin:
            self.logger.error("Cannot stop charging: missing access token or VIN")
            return False
        
        try:
            self._post(f"/api/1/vehicles/{self.vin}/command/charge_stop")
            self.logger.info("Stopped charging for VIN %s", self.vin)
            return True
        except Exception as e:
            error_str = str(e).lower()
            if "vehicle_command" in error_str or "signed_command" in error_str or "unauthorized" in error_str:
                self.logger.error("Tesla deprecated simple REST commands in Oct 2023. Vehicle commands now require Tesla Vehicle Command Protocol with cryptographic keys.")
                self.logger.error("Your system can read vehicle data but cannot send commands without implementing the new protocol.")
                return False
            elif "offline or asleep" in error_str or "unavailable" in error_str:
                self.logger.info("Vehicle asleep/unavailable, attempting wake sequence...")
                return self._wake_and_retry_command("charge_stop")
            else:
                self.logger.error("Failed to stop charging: %s", e)
            return False

    def set_charging_amps(self, amps: int) -> bool:
        if self.dry:
            self.logger.info("[DRY-RUN] Would set charging amps to %s for VIN %s", amps, self.vin)
            return True
        
        if not self.access_token or not self.vin:
            self.logger.error("Cannot set charging amps: missing access token or VIN")
            return False
        
        try:
            self._post(f"/api/1/vehicles/{self.vin}/command/set_charging_amps", {"charging_amps": amps})
            self.logger.info("Set charging amps to %s for VIN %s", amps, self.vin)
            return True
        except Exception as e:
            self.logger.error("Failed to set charging amps: %s", e)
            return False
