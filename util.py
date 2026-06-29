import requests
import datetime
import time


def is_daylight_saving_time(
    dt: datetime.datetime | None = None, timezone_name: str | None = None
) -> bool:
    """
    Determines whether Daylight Saving Time (summer time) is in effect.

    Args:
        dt: The datetime to check. Defaults to current local time.
        timezone_name: Optional timezone name (e.g. 'America/New_York', 'Europe/London').
                       Requires the 'zoneinfo' module (Python 3.9+) or 'pytz'.
                       If None, uses the system's local timezone.

    Returns:
        True if DST/summer time is active, False otherwise.
    """
    if timezone_name:
        try:
            from zoneinfo import ZoneInfo

            tz = ZoneInfo(timezone_name)
            if dt is None:
                dt = datetime.datetime.now(tz)
            else:
                dt = dt.replace(tzinfo=tz)
            return bool(dt.dst())
        except ImportError:
            try:
                import pytz

                tz = pytz.timezone(timezone_name)
                if dt is None:
                    dt = datetime.datetime.now(tz)
                else:
                    dt = tz.localize(dt)
                return bool(dt.dst())
            except ImportError:
                raise ImportError(
                    "A named timezone requires 'zoneinfo' (Python 3.9+) or 'pytz'. "
                    "Install pytz with: pip install pytz"
                )

    # Fall back to system local time
    if dt is None:
        return bool(time.daylight and time.localtime().tm_isdst > 0)

    # For a naive datetime, use mktime to probe the local timezone
    ts = dt.timetuple()
    local = time.localtime(time.mktime(ts))
    return local.tm_isdst > 0


def get_sunset():
    endpoint = "https://api.sunrise-sunset.org/json"
    with requests.Session() as session:
        response = session.get(
            endpoint, params={"lat": 510507.7, "lng": 102245.4, "tzid": "Europe/Berlin"}
        )
        data = response.json()
        sunset_time = data["results"]["sunset"]
        adjusted_sunset_datetime = datetime.datetime.strptime(
            sunset_time, "%I:%M:%S %p"
        ) + datetime.timedelta(hours=1 if is_daylight_saving_time() else 0)
        return adjusted_sunset_datetime.strftime("%I:%M:%S %p")
