import logging
import time


class Controller:
    def __init__(self, config: dict):
        self.config = config
        self.logger = logging.getLogger("controller")
        ctrl = config.get("control", {})
        self.start_threshold_w = int(ctrl.get("start_export_watts", 3500))
        self.stop_threshold_w = int(ctrl.get("stop_export_watts", 1500))
        self.min_on = int(ctrl.get("min_on_seconds", 300))
        self.min_off = int(ctrl.get("min_off_seconds", 300))
        self.max_soc = int(ctrl.get("max_soc", 80))
        self.mode = ctrl.get("mode", "threshold")

        self._charging = False
        self._last_change_ts = 0.0

    def _enforce_hysteresis(self, want_on: bool) -> bool:
        now = time.time()
        elapsed = now - self._last_change_ts
        if want_on and not self._charging:
            return elapsed >= self.min_off
        if not want_on and self._charging:
            return elapsed >= self.min_on
        return False

    def decide_action(self, ctx: dict) -> dict:
        soc = ctx.get("vehicle_soc")
        plugged = ctx.get("vehicle_plugged_in", False)
        export = ctx.get("site_export_w")
        pv = ctx.get("pv_production_w", 0)

        if not plugged:
            self.logger.debug("Vehicle not plugged in; ensure stopped")
            if self._charging:
                return {"type": "stop", "reason": "unplugged"}
            return {"type": "none"}

        if soc is not None and soc >= self.max_soc:
            self.logger.info("SOC %s >= max %s; ensure stopped", soc, self.max_soc)
            if self._charging:
                return {"type": "stop", "reason": "soc_cap"}
            return {"type": "none"}

        signal_value = export if export is not None else pv

        # Threshold control
        if self.mode == "threshold":
            if not self._charging and signal_value >= self.start_threshold_w:
                if self._enforce_hysteresis(True):
                    return {"type": "start", "reason": "export_above_start"}
                else:
                    return {"type": "none"}
            if self._charging and signal_value <= self.stop_threshold_w:
                if self._enforce_hysteresis(False):
                    return {"type": "stop", "reason": "export_below_stop"}
                else:
                    return {"type": "none"}
            return {"type": "none"}

        # Future: dynamic amps
        return {"type": "none"}

    def apply_action(self, action: dict, tesla_client):
        t = action.get("type")
        if t == "start":
            self.logger.info("Starting charge (%s)", action.get("reason"))
            if tesla_client.start_charging():
                self._charging = True
                self._last_change_ts = time.time()
        elif t == "stop":
            self.logger.info("Stopping charge (%s)", action.get("reason"))
            if tesla_client.stop_charging():
                self._charging = False
                self._last_change_ts = time.time()
        elif t == "set_amps":
            amps = action.get("amps")
            self.logger.info("Setting charge amps to %s", amps)
            tesla_client.set_charging_amps(amps)
        else:
            self.logger.debug("No action")
