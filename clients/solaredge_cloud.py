import logging
import time
import requests
from typing import Optional, Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, before_sleep_log

# Configure logger for tenacity
logger = logging.getLogger("solaredge.cloud")

class RateLimitError(Exception):
    """Exception raised when hitting rate limits."""
    pass


class SolarEdgeCloudClient:
    BASE = "https://monitoringapi.solaredge.com"
    CACHE_TTL = 300  # 5 minutes cache TTL
    
    def __init__(self, config: dict):
        self.logger = logging.getLogger("solaredge.cloud")
        se = config.get("solaredge", {})
        self.api_key = se.get("cloud", {}).get("api_key")
        self.site_id = se.get("cloud", {}).get("site_id")
        self._cache: Dict[str, tuple[float, Any]] = {}  # key: (timestamp, data)
        self._last_request_time = 0
        self._min_request_interval = 1.0  # Minimum seconds between API calls

    def _check_rate_limit(self):
        """Ensure we don't make requests too frequently and respect rate limits."""
        now = time.time()
        time_since_last = now - self._last_request_time
        if time_since_last < self._min_request_interval:
            time.sleep(self._min_request_interval - time_since_last)
        self._last_request_time = time.time()

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
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=60),  # Exponential backoff up to 60s
        retry=retry_if_exception_type((RateLimitError, requests.exceptions.RequestException)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True
    )
    def _get(self, path: str, params: dict, cache_ttl: float = None):
        """Make a GET request to SolarEdge API with rate limiting and caching."""
        cache_key = f"{path}:{str(sorted(params.items()))}" if cache_ttl else None
        
        # Try cache first if TTL is provided
        if cache_ttl and (cached := self._get_cached(cache_key, cache_ttl)):
            return cached

        # Respect rate limits
        self._check_rate_limit()
        
        url = f"{self.BASE}{path}"
        params = {**params, "api_key": self.api_key}
        
        try:
            r = requests.get(url, params=params, timeout=10)
            
            # Handle rate limiting
            if r.status_code == 429:
                retry_after = int(r.headers.get('Retry-After', 60))
                self.logger.warning("Rate limited. Waiting %s seconds", retry_after)
                time.sleep(retry_after)
                raise RateLimitError(f"Rate limited by SolarEdge API. Retry after {retry_after}s")
                
            r.raise_for_status()
            
            data = r.json()
            
            # Cache the successful response
            if cache_ttl and cache_key:
                self._set_cached(cache_key, data)
                
            return data
            
        except requests.exceptions.RequestException as e:
            self.logger.error("Request failed: %s", str(e))
            raise

    def get_power(self) -> dict:
        """Get current power data with caching and rate limiting."""
        if not self.api_key or not self.site_id:
            self.logger.debug("SolarEdge API key/site ID not set; returning zeroes")
            return {"pv_production_w": 0, "site_export_w": None}
            
        try:
            # Prefer current power flow if meter present - cache for 30 seconds
            data = self._get(
                f"/site/{self.site_id}/currentPowerFlow.json",
                {},
                cache_ttl=30  # Cache for 30 seconds
            )
            site = data.get("siteCurrentPowerFlow", {})
            pv = site.get("PV", {}).get("currentPower")
            grid = site.get("GRID", {})
            # grid 'status' may be 'Active'; 'currentPower' positive import, negative export
            grid_power = grid.get("currentPower")
            export = None
            if grid_power is not None:
                # Convert to export watts (positive when exporting)
                export = max(0, -float(grid_power)) if float(grid_power) < 0 else 0.0
            return {
                "pv_production_w": int(float(pv) * 1000) if pv is not None else 0,  # Convert kW to W
                "site_export_w": int(export) if export is not None else None,
            }
        except Exception as e:
            self.logger.warning("Failed currentPowerFlow; falling back to overview: %s", e)
            try:
                # Fallback to overview - cache for 60 seconds
                data = self._get(
                    f"/site/{self.site_id}/overview.json",
                    {},
                    cache_ttl=60  # Cache for 60 seconds
                )
                life = data.get("overview", {}).get("currentPower", {})
                return {
                    "pv_production_w": int(float(life.get("power")) if life.get("power") is not None else 0),
                    "site_export_w": None,
                }
            except Exception:
                self.logger.exception("SolarEdge cloud fetch failed")
                return {"pv_production_w": 0, "site_export_w": None}
