from datetime import datetime, timedelta
import pytz
from astral import LocationInfo
from astral.sun import sun


def is_daytime(config: dict) -> bool:
    dt_cfg = config.get("control", {}).get("daytime", {})
    tzname = dt_cfg.get("timezone", "UTC")
    tz = pytz.timezone(tzname)
    now = datetime.now(tz)

    if dt_cfg.get("use_sun_times", True):
        # You can refine location via config; using geofence center if set
        geo = config.get("control", {}).get("home_geofence", {})
        lat = float(geo.get("latitude", 0.0))
        lon = float(geo.get("longitude", 0.0))
        loc = LocationInfo(latitude=lat, longitude=lon)
        s = sun(loc.observer, date=now.date(), tzinfo=tz)
        start = s["sunrise"] + timedelta(minutes=int(dt_cfg.get("sunrise_offset_min", -30)))
        end = s["sunset"] + timedelta(minutes=int(dt_cfg.get("sunset_offset_min", 30)))
        return start <= now <= end

    # Fallback: fixed hours could be added here
    return True
