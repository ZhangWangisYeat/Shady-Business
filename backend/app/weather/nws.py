"""Hourly forecast temperature at UCLA from the US National Weather Service."""
import json
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

# campus center, rounded to 4 places because api.weather.gov redirects
# anything more precise
POINT = (34.0689, -118.4452)
# the NWS asks every client to identify itself in the User-Agent
USER_AGENT = "shady-business/0.1 (UCLA campus walking app prototype)"
TIMEOUT_S = 6
# hourly forecasts update roughly hourly, and every app launch asks, so one
# fetch per 15 minutes keeps us well inside their fair use
CACHE_S = 900

Fetch = Callable[[str], dict]


class WeatherUnavailable(Exception):
    pass


@dataclass(frozen=True)
class HourlyTemperature:
    temperature_f: float
    valid_from: datetime
    valid_to: datetime


def _fetch(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/geo+json"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
        return json.load(response)


_cache: dict = {"hourly_url": None, "periods": None, "fetched": 0.0}


def hourly_periods(fetch: Fetch | None = None, now: Callable[[], float] = time.monotonic) -> list[HourlyTemperature]:
    fetch = fetch or _fetch
    if _cache["periods"] is not None and now() - _cache["fetched"] < CACHE_S:
        return _cache["periods"]
    try:
        # the points lookup only says which forecast grid covers campus, and
        # that never changes, so it's asked once per server run
        if _cache["hourly_url"] is None:
            _cache["hourly_url"] = fetch(f"https://api.weather.gov/points/{POINT[0]},{POINT[1]}")["properties"]["forecastHourly"]
        raw = fetch(_cache["hourly_url"])["properties"]["periods"]
        periods = [HourlyTemperature(
            temperature_f=float(p["temperature"]) if p.get("temperatureUnit", "F") == "F" else float(p["temperature"]) * 9 / 5 + 32,
            valid_from=datetime.fromisoformat(p["startTime"]),
            valid_to=datetime.fromisoformat(p["endTime"]),
        ) for p in raw]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise WeatherUnavailable("Weather forecast unavailable") from exc
    if not periods:
        raise WeatherUnavailable("Weather forecast returned no hours")
    _cache.update(periods=periods, fetched=now())
    return periods


def temperature_at(when: datetime, periods: list[HourlyTemperature]) -> HourlyTemperature:
    for period in periods:
        if period.valid_from <= when < period.valid_to:
            return period
    # the forecast starts at the current hour, so a phone whose clock is a bit
    # behind (or set by hand for testing) still gets the closest hour
    return min(periods, key=lambda p: abs((p.valid_from - when).total_seconds()))
