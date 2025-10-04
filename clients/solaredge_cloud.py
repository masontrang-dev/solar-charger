import logging
import time
import random
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
import requests
from tenacity import (
    retry, 
    stop_after_attempt, 
    wait_exponential, 
    retry_if_exception_type,
    before_sleep_log,
    retry_any,
    retry_if_exception
)

# Configure logger
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
    CACHE_TTL = 300  # 5 minutes cache TTL
    
    def __init__(self, config: dict):
        self.api_key = config.get("solaredge_api_key")
        self.site_id = config.get("solaredge_site_id")
        self._cache = {}
        self._last_request_time = 0
        self._circuit_open_until = 0
        self._failure_count = 0
        self.logger = logging.getLogger("solar")
        # Rate limiting - 2 minutes between requests to stay under 300/day (11h window)
        self._min_request_interval = 120  # 2 minutes in seconds between API calls
        self._circuit_open_until = 0  # Timestamp when circuit will close
        self._consecutive_errors = 0
        self._max_consecutive_errors = 3
        self._circuit_reset_time = 300  # 5 minutes circuit breaker reset
        self._jitter_range = (0.5, 1.5)  # Random jitter to prevent thundering herd
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

    def _check_rate_limit(self):
        """Ensure we don't make requests too frequently and respect rate limits."""
        self._check_circuit_breaker()
        
        now = time.time()
        time_since_last = now - self._last_request_time
        
        # Add jitter to spread out retries
        min_interval = self._min_request_interval * self._get_jitter()
        
        if time_since_last < min_interval:
            sleep_time = min_interval - time_since_last
            self.logger.debug("Rate limiting: sleeping for %.1f seconds", sleep_time)
            time.sleep(sleep_time)
            
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
        stop=stop_after_attempt(5),  # Increased max attempts
        wait=wait_exponential(
            multiplier=2,  # More aggressive backoff
            min=5,         # Start with 5s
            max=300        # Max 5 minutes between retries
        ),
        retry=retry_any(
            retry_if_exception_type(RateLimitError),
            retry_if_exception_type(requests.exceptions.RequestException)
        ),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True
    )
    def _get(self, path: str, params: dict, cache_ttl: float = 120) -> dict:  # Default to 2 minutes
        """
        Make a GET request to SolarEdge API with rate limiting and caching.
        Implements a 2-minute minimum interval between requests to respect API limits.
        
        Args:
            path: API endpoint path
            params: Query parameters
            cache_ttl: Cache TTL in seconds (default: 120s)
            
        Returns:
            dict: Response data
        """
        # Enforce minimum time between requests
        now = time.time()
        time_since_last = now - self._last_request_time
        if time_since_last < self._min_request_interval:
            wait_time = self._min_request_interval - time_since_last
            self.logger.debug(f"Rate limiting: Waiting {wait_time:.1f}s before next request")
            time.sleep(wait_time)
            
        cache_key = f"{path}:{str(sorted(params.items()))}" if cache_ttl else None
        
        # Try cache first if TTL is provided
        if cache_ttl and (cached := self._get_cached(cache_key, cache_ttl)):
            return cached
        
        try:
            # Add a small jitter to the timeout
            timeout = 10 * self._get_jitter()
            
            # Make the request
            url = f"{self.BASE}{path}"
            params = {**params, "api_key": self.api_key}
            r = requests.get(url, params=params, timeout=timeout)
            
            # Handle rate limiting
            if r.status_code == 429:
                retry_after = int(r.headers.get('Retry-After', 60))
                retry_after = min(retry_after, 300)  # Cap at 5 minutes
                self.logger.warning("Rate limited. Waiting %s seconds", retry_after)
                time.sleep(retry_after)
                self._update_circuit_breaker(False)
                raise RateLimitError(
                    f"Rate limited by SolarEdge API. Retry after {retry_after}s",
                    retry_after=retry_after
                )
                
            r.raise_for_status()  # Raise HTTPError for bad responses
            data = r.json()
            
            # Update circuit breaker on success
            self._update_circuit_breaker(True)
            
            # Cache the successful response and update last request time
            if cache_ttl and cache_key:
                self._set_cached(cache_key, data)
                
            self._last_request_time = time.time()
            return data
            
        except requests.exceptions.RequestException as e:
            # Update circuit breaker on failure
            self._update_circuit_breaker(False)
            self.logger.error(f"Request failed: {str(e)}")
            raise

    def get_power(self) -> dict:
        """Get current power data with caching and rate limiting."""
        if not self.api_key or not self.site_id:
            self.logger.debug("SolarEdge API key/site ID not set; returning zeroes")
            return {"pv_production_w": 0, "site_export_w": None}
            
        try:
            # Prefer current power flow if meter present - cache for 60 seconds
            data = self._get(
                f"/site/{self.site_id}/currentPowerFlow.json",
                {},
                cache_ttl=60  # Increased cache TTL to reduce API calls
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
        except (RateLimitError, CircuitBreakerError) as e:
            self.logger.warning("Rate limited or circuit open: %s", str(e))
            # Return cached data if available, otherwise zeros
            return {"pv_production_w": 0, "site_export_w": None}
            self.logger.warning("Rate limited or circuit open: %s", str(e))
            # Return cached data if available, otherwise zeros
            return {"pv_production_w": 0, "site_export_w": None}
            
        except Exception as e:
            self.logger.warning("Failed currentPowerFlow; falling back to overview: %s", e)
            try:
                # Fallback to overview - cache for 120 seconds
                data = self._get(
                    f"/site/{self.site_id}/overview.json",
                    {},
                    cache_ttl=120  # Increased cache TTL for fallback
                )
                life = data.get("overview", {}).get("currentPower", {})
                return {
                    "pv_production_w": int(float(life.get("power")) if life.get("power") is not None else 0),
                    "site_export_w": None,
                }
            except Exception:
                self.logger.exception("SolarEdge cloud fetch failed")
                return {"pv_production_w": 0, "site_export_w": None}
