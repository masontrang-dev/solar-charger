#!/usr/bin/env python3
"""
Tesla HPWC (High Power Wall Connector) Client
Provides read-only access to wall connector vitals for monitoring and plug detection.
"""

import requests
import logging
from typing import Optional, Dict


class TeslaHPWCClient:
    def __init__(self, config: dict):
        self.logger = logging.getLogger("hpwc")
        hpwc_config = config.get("hpwc", {})
        
        self.enabled = hpwc_config.get("enabled", False)
        self.ip_address = hpwc_config.get("ip_address")
        self.timeout = hpwc_config.get("timeout", 3)
        self.use_proxy = hpwc_config.get("use_proxy", False)
        self.proxy_url = hpwc_config.get("proxy_url")
        
        # Setup proxies if configured
        self.proxies = None
        if self.use_proxy and self.proxy_url:
            self.proxies = {
                'http': self.proxy_url,
                'https': self.proxy_url
            }
            self.logger.info(f"HPWC using proxy: {self.proxy_url}")
        
        if self.enabled:
            if not self.ip_address:
                self.logger.error("HPWC enabled but no IP address configured")
                self.enabled = False
            else:
                self.url = f"http://{self.ip_address}/api/1/vitals"
                proxy_info = f" via proxy {self.proxy_url}" if self.use_proxy else ""
                self.logger.info(f"HPWC client initialized: {self.url}{proxy_info}")
        else:
            self.logger.info("HPWC client disabled in config")
        
        self._last_data = None
        self._last_error = None
    
    def get_vitals(self) -> Optional[Dict]:
        """Get current vitals from HPWC.
        
        Returns:
            Dict with HPWC data, or None if unavailable/disabled
        """
        if not self.enabled:
            return None
        
        try:
            response = requests.get(self.url, timeout=self.timeout, proxies=self.proxies)
            response.raise_for_status()
            data = response.json()
            
            self._last_data = data
            self._last_error = None
            
            self.logger.debug(f"HPWC vitals: connected={data.get('vehicle_connected')}, "
                            f"current={data.get('vehicle_current_a')}A, "
                            f"session={data.get('session_s')}s, "
                            f"energy={data.get('session_energy_wh')}Wh")
            
            return data
            
        except requests.exceptions.Timeout:
            self.logger.warning(f"HPWC request timeout after {self.timeout}s")
            self._last_error = "timeout"
            return None
        except requests.exceptions.ConnectionError as e:
            self.logger.warning(f"HPWC connection error: {e}")
            self._last_error = "connection_error"
            return None
        except Exception as e:
            self.logger.error(f"HPWC error: {e}")
            self._last_error = str(e)
            return None
    
    def is_vehicle_connected(self) -> Optional[bool]:
        """Quick check if vehicle is connected.
        
        Returns:
            True if connected, False if not connected, None if HPWC unavailable
        """
        vitals = self.get_vitals()
        if vitals is None:
            return None
        return vitals.get('vehicle_connected', False)
    
    def get_session_energy_kwh(self) -> Optional[float]:
        """Get current session energy in kWh.
        
        Returns:
            Energy in kWh, or None if unavailable
        """
        if self._last_data:
            wh = self._last_data.get('session_energy_wh', 0)
            return wh / 1000.0
        return None
    
    def get_actual_current(self) -> Optional[float]:
        """Get actual vehicle current draw.
        
        Returns:
            Current in amps, or None if unavailable
        """
        if self._last_data:
            return self._last_data.get('vehicle_current_a')
        return None
    
    def get_grid_voltage(self) -> Optional[float]:
        """Get grid voltage.
        
        Returns:
            Voltage, or None if unavailable
        """
        if self._last_data:
            return self._last_data.get('grid_v')
        return None
    
    def get_status_summary(self) -> Dict:
        """Get summary status for dashboard/logging.
        
        Returns:
            Dict with key status information
        """
        if not self.enabled:
            return {"enabled": False}
        
        if self._last_data is None:
            return {
                "enabled": True,
                "available": False,
                "error": self._last_error
            }
        
        return {
            "enabled": True,
            "available": True,
            "vehicle_connected": self._last_data.get('vehicle_connected', False),
            "contactor_closed": self._last_data.get('contactor_closed', False),
            "vehicle_current_a": self._last_data.get('vehicle_current_a', 0),
            "grid_v": self._last_data.get('grid_v', 0),
            "grid_hz": self._last_data.get('grid_hz', 0),
            "session_energy_wh": self._last_data.get('session_energy_wh', 0),
            "session_energy_kwh": self.get_session_energy_kwh(),
            "session_s": self._last_data.get('session_s', 0),
            "pcba_temp_c": self._last_data.get('pcba_temp_c'),
            "handle_temp_c": self._last_data.get('handle_temp_c'),
            "evse_state": self._last_data.get('evse_state'),
        }
