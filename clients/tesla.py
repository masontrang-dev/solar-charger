import logging
import requests
import yaml
import urllib3

# Disable SSL warnings for Tesla HTTP proxy self-signed certificate
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from tenacity import retry, stop_after_attempt, wait_exponential


class TeslaClient:
    BASE_URL = "https://fleet-api.prd.na.vn.cloud.tesla.com"
    PROXY_URL = "https://localhost:8080"  # Tesla HTTP proxy
    
    def __init__(self, config: dict):
        self.logger = logging.getLogger("tesla")
        self.config = config
        self.dry = bool(config.get("dry_run", True))
        self.vin = config.get("tesla", {}).get("vehicle_vin")
        
        tesla_config = config.get("tesla", {}).get("api", {})
        self.access_token = tesla_config.get("access_token")
        
        if not self.access_token:
            self.logger.warning("No Tesla access token configured")
    
    def _headers(self):
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def _get(self, path: str):
        url = f"{self.BASE_URL}{path}"
        response = requests.get(url, headers=self._headers(), timeout=10)
        response.raise_for_status()
        return response.json()
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def _post(self, path: str, data: dict = None):
        # Use Tesla HTTP proxy for command endpoints
        if "/command/" in path:
            url = f"{self.PROXY_URL}{path}"
            response = requests.post(
                url, 
                headers=self._headers(), 
                json=data or {}, 
                timeout=10,
                verify=False  # Skip SSL verification for self-signed cert
            )
        else:
            # Use direct Fleet API for non-command endpoints
            url = f"{self.BASE_URL}{path}"
            response = requests.post(url, headers=self._headers(), json=data or {}, timeout=10)
        
        response.raise_for_status()
        return response.json()

    def get_state(self) -> dict:
        if not self.access_token or not self.vin:
            self.logger.debug("No Tesla access token or VIN; returning placeholder data")
            return {
                "plugged_in": True,  # assume plugged for dry-run demo
                "soc": 60,
            }
        
        try:
            # Get vehicle data from Tesla Fleet API
            data = self._get(f"/api/1/vehicles/{self.vin}/vehicle_data")
            vehicle_data = data.get("response", {})
            
            charge_state = vehicle_data.get("charge_state", {})
            vehicle_state = vehicle_data.get("vehicle_state", {})
            drive_state = vehicle_data.get("drive_state", {})
            
            return {
                "plugged_in": charge_state.get("charging_state") in ["Charging", "Stopped", "Complete"],
                "soc": charge_state.get("battery_level"),
                "charging_state": charge_state.get("charging_state"),
                "charge_limit_soc": charge_state.get("charge_limit_soc"),
                "charge_current_request": charge_state.get("charge_current_request"),
                "vehicle_state": vehicle_state.get("car_version"),
                "shift_state": drive_state.get("shift_state"),  # Park, Drive, Reverse, Neutral
                "speed": drive_state.get("speed"),
                "location": {
                    "latitude": drive_state.get("latitude"),
                    "longitude": drive_state.get("longitude"),
                }
            }
        except Exception as e:
            self.logger.warning("Failed to get Tesla vehicle state: %s", e)
            return {
                "plugged_in": True,  # fallback assumption
                "soc": 60,
            }

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
            # If vehicle is asleep, try to wake it first
            if "offline or asleep" in str(e).lower() or "unavailable" in str(e).lower():
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
                
                # Try wake_up command first (Tesla HTTP proxy uses /command/ path)
                try:
                    self._post(f"/api/1/vehicles/{self.vin}/command/wake_up")
                    self.logger.info("Wake command sent via proxy, waiting...")
                except Exception as wake_e:
                    self.logger.warning(f"Proxy wake command failed: {wake_e}")
                    # Try alternative wake path (direct Fleet API style)
                    try:
                        # Use direct Fleet API call as fallback
                        wake_url = f"{self.BASE_URL}/api/1/vehicles/{self.vin}/wake_up"
                        response = requests.post(wake_url, headers=self._headers(), timeout=10)
                        response.raise_for_status()
                        self.logger.info("Direct Fleet API wake command sent, waiting...")
                    except Exception as direct_wake_e:
                        self.logger.warning(f"Direct wake also failed: {direct_wake_e}, trying command anyway...")
                
                # Wait progressively longer for each attempt
                wait_time = 10 + (attempt * 5)  # 10s, 15s, 20s
                self.logger.info(f"Waiting {wait_time} seconds for vehicle to wake...")
                time.sleep(wait_time)
                
                # Check if vehicle is actually awake by trying to get its state
                try:
                    state_response = self._get(f"/api/1/vehicles/{self.vin}/vehicle_data")
                    if state_response.get("response"):
                        self.logger.info("Vehicle is now awake and responding")
                    else:
                        self.logger.warning("Vehicle wake status unclear")
                except Exception as state_e:
                    self.logger.warning(f"Cannot verify wake state: {state_e}")
                
                # Try the actual command
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
            # If vehicle is asleep, try to wake it first
            if "offline or asleep" in str(e).lower() or "unavailable" in str(e).lower():
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
