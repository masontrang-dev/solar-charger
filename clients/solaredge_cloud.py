import logging
import requests
from tenacity import retry, stop_after_attempt, wait_exponential


class SolarEdgeCloudClient:
    BASE = "https://monitoringapi.solaredge.com"

    def __init__(self, config: dict):
        self.logger = logging.getLogger("solaredge.cloud")
        se = config.get("solaredge", {})
        self.api_key = se.get("cloud", {}).get("api_key")
        self.site_id = se.get("cloud", {}).get("site_id")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def _get(self, path: str, params: dict):
        url = f"{self.BASE}{path}"
        params = {**params, "api_key": self.api_key}
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()

    def get_power(self) -> dict:
        if not self.api_key or not self.site_id:
            self.logger.debug("SolarEdge API key/site ID not set; returning zeroes")
            return {"pv_production_w": 0, "site_export_w": None}
        try:
            # Prefer current power flow if meter present
            data = self._get(f"/site/{self.site_id}/currentPowerFlow.json", {})
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
                data = self._get(f"/site/{self.site_id}/overview.json", {})
                life = data.get("overview", {}).get("currentPower", {})
                return {
                    "pv_production_w": int(float(life.get("power")) if life.get("power") is not None else 0),
                    "site_export_w": None,
                }
            except Exception:
                self.logger.exception("SolarEdge cloud fetch failed")
                return {"pv_production_w": 0, "site_export_w": None}
