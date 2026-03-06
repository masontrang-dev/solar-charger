import logging
import time
import random
from typing import Optional, Any
import requests
from tenacity import (
    retry, 
    stop_after_attempt, 
    wait_exponential, 
    retry_if_exception_type,
    before_sleep_log,
    retry_any
)

logger = logging.getLogger("solaredge.cloud")

class RateLimitError(Exception):
    """Exception raised when hitting rate limits."""
    def __init__(self, message: str, retry_after: int = 60):
        self.retry_after = retry_after
        super().__init__(message)

class CircuitBreakerError(Exception):
    """Exception raised when circuit is open (too many failures)."""
    pass

class SolarEdgeCloudClient:
    BASE = "https://monitoringapi.solaredge.com"
    CACHE_TTL = 300
    
    def __init__(self, config: dict):
        solaredge_config = config.get("solaredge", {})
        cloud_config = solaredge_config.get("cloud", {})
        
        self.api_key = cloud_config.get("api_key") or config.get("solaredge_api_key")
        self.site_id = cloud_config.get("site_id") or config.get("solaredge_site_id")
        
        self._cache = {}
        self._last_request_time = 0
        self.logger = logging.getLogger("solar")
        
        # Get configurable polling intervals (with defaults)
        polling_config = config.get("polling", {})
        self._day_interval = polling_config.get("solar_day_interval", 60)
        self._night_interval = polling_config.get("solar_night_interval", 300)
        
        self._circuit_open_until = 0
        self._consecutive_errors = 0
        self._max_consecutive_errors = 3
        self._circuit_reset_time = 300
        self._jitter_range = (0.5, 1.5)
        self.last_connection_success = None
        self.last_error_message = None
        
        self.logger.info(f"SolarEdge polling: {self._day_interval}s (day), {self._night_interval}s (night)")
    def _check_circuit_breaker(self):
        """Check if the circuit breaker is open."""
        now = time.time()
        if now < self._circuit_open_until:
            raise CircuitBreakerError(
                f"Circuit breaker open. Retry after {int(self._circuit_open_until - now)} seconds"
            )

    def _update_circuit_breaker(self, success: bool):
        """Update circuit breaker state based on request success/failure."""
        if success:
            self._consecutive_errors = 0
            if self._circuit_open_until > 0:
                self._circuit_open_until = 0
                self.logger.info("Circuit breaker closed after successful request")
        else:
            self._consecutive_errors += 1
            if self._consecutive_errors >= self._max_consecutive_errors:
                self._circuit_open_until = time.time() + self._circuit_reset_time
                self.logger.warning(
                    "Circuit breaker opened due to %d consecutive errors. Will retry after %s",
                    self._consecutive_errors,
                    time.ctime(self._circuit_open_until)
                )

    def _get_jitter(self) -> float:
        """Get a random jitter value to prevent thundering herd."""
        return random.uniform(*self._jitter_range)

    def _get_cached(self, cache_key: str, ttl: float) -> Optional[Any]:
        """Get data from cache if it exists and is fresh."""
        if cache_key in self._cache:
            timestamp, data = self._cache[cache_key]
            if time.time() - timestamp < ttl:
                self.logger.debug("Cache hit for %s", cache_key)
                return data
        return None

    def _set_cached(self, cache_key: str, data: Any):
        """Store data in cache with current timestamp."""
        self._cache[cache_key] = (time.time(), data)

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=5, max=300),
        retry=retry_any(
            retry_if_exception_type(RateLimitError),
            retry_if_exception_type(requests.exceptions.RequestException)
        ),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True
    )
    def _get(self, path: str, params: dict, cache_ttl: float = 120, min_interval: int = None) -> dict:
        """Make a GET request to SolarEdge API with rate limiting and caching."""
        # Use provided min_interval or default to night_interval (most conservative)
        interval = min_interval if min_interval is not None else self._night_interval
        
        now = time.time()
        time_since_last = now - self._last_request_time
        if time_since_last < interval:
            wait_time = interval - time_since_last
            self.logger.debug(f"Rate limiting: Waiting {wait_time:.1f}s before next request")
            time.sleep(wait_time)
            
        cache_key = f"{path}:{str(sorted(params.items()))}" if cache_ttl else None
        
        if cache_ttl and (cached := self._get_cached(cache_key, cache_ttl)):
            return cached
        
        try:
            timeout = 10 * self._get_jitter()
            url = f"{self.BASE}{path}"
            params = {**params, "api_key": self.api_key}
            r = requests.get(url, params=params, timeout=timeout)
            
            if r.status_code == 429:
                retry_after = int(r.headers.get('Retry-After', 60))
                retry_after = min(retry_after, 300)
                self.logger.warning("Rate limited. Waiting %s seconds", retry_after)
                time.sleep(retry_after)
                self._update_circuit_breaker(False)
                raise RateLimitError(
                    f"Rate limited by SolarEdge API. Retry after {retry_after}s",
                    retry_after=retry_after
                )
                
            r.raise_for_status()
            data = r.json()
            
            self._update_circuit_breaker(True)
            
            if cache_ttl and cache_key:
                self._set_cached(cache_key, data)
                
            self._last_request_time = time.time()
            return data
            
        except requests.exceptions.RequestException as e:
            self._update_circuit_breaker(False)
            self.logger.error(f"Request failed: {str(e)}")
            raise

    def test_connection(self) -> bool:
        """Test the connection to SolarEdge API and verify credentials."""
        if not self.api_key or not self.site_id:
            error_msg = "SolarEdge API key or site ID not configured"
            self.logger.error(error_msg)
            self.last_connection_success = False
            self.last_error_message = error_msg
            return False
            
        try:
            self.logger.info("Testing SolarEdge API connection...")
            data = self._get(
                f"/site/{self.site_id}/details.json",
                {},
                cache_ttl=0
            )
            
            response_id = str(data.get('details', {}).get('id', '')).strip()
            expected_id = str(self.site_id).strip()
            
            if data and response_id == expected_id:
                self.logger.info("✅ SolarEdge connection successful")
                self.last_connection_success = True
                self.last_error_message = None
                return True
            else:
                error_msg = f"Site ID mismatch. Expected: {expected_id}, Got: {response_id if response_id else 'None'}"
                self.logger.error(f"Invalid response from SolarEdge API - {error_msg}")
                self.logger.debug(f"Full response: {data}")
                self.last_connection_success = False
                self.last_error_message = error_msg
                return False
            
        except Exception as e:
            error_msg = str(e)
            self.logger.error(f"SolarEdge connection test failed: {error_msg}")
            self.last_connection_success = False
            self.last_error_message = error_msg
            return False
            
    def _get_adaptive_interval(self, current_production_w: int = 0) -> int:
        """Get adaptive polling interval based on solar production."""
        # Use day interval if there's any production, otherwise night interval
        if current_production_w > 0:
            return self._day_interval
        return self._night_interval
    
    def get_power(self) -> dict:
        """Get current power data with caching and rate limiting."""
        if not self.api_key or not self.site_id:
            self.logger.debug("SolarEdge API key/site ID not set; returning zeroes")
            return {"pv_production_w": 0, "site_export_w": None}
            
        try:
            data = self._get(
                f"/site/{self.site_id}/currentPowerFlow.json",
                {},
                cache_ttl=60
            )
            site = data.get("siteCurrentPowerFlow", {})
            pv = site.get("PV", {}).get("currentPower")
            grid = site.get("GRID", {})
            grid_power = grid.get("currentPower")
            export = None
            if grid_power is not None:
                export = max(0, -float(grid_power)) if float(grid_power) < 0 else 0.0
            return {
                "pv_production_w": int(float(pv) * 1000) if pv is not None else 0,
                "site_export_w": int(export) if export is not None else None,
            }
        except (RateLimitError, CircuitBreakerError) as e:
            self.logger.warning("Rate limited or circuit open: %s", str(e))
            return {"pv_production_w": 0, "site_export_w": None}
            
        except Exception as e:
            self.logger.warning("Failed currentPowerFlow; falling back to overview: %s", e)
            try:
                data = self._get(
                    f"/site/{self.site_id}/overview.json",
                    {},
                    cache_ttl=120
                )
                life = data.get("overview", {}).get("currentPower", {})
                return {
                    "pv_production_w": int(float(life.get("power")) if life.get("power") is not None else 0),
                    "site_export_w": None,
                }
            except Exception:
                self.logger.exception("SolarEdge cloud fetch failed")
                return {"pv_production_w": 0, "site_export_w": None}
