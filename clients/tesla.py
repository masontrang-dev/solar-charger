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
            self.logger.error("Failed to start charging: %s", e)
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
