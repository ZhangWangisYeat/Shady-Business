from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.weather import nws

HOURLY = "https://api.weather.gov/gridpoints/LOX/149,48/forecast/hourly"


def fake_nws(calls):
    def fetch(url):
        calls.append(url)
        if "/points/" in url:
            return {"properties": {"forecastHourly": HOURLY}}
        return {"properties": {"periods": [
            {"startTime": "2026-10-17T13:00:00-07:00", "endTime": "2026-10-17T14:00:00-07:00", "temperature": 78, "temperatureUnit": "F"},
            {"startTime": "2026-10-17T14:00:00-07:00", "endTime": "2026-10-17T15:00:00-07:00", "temperature": 27, "temperatureUnit": "C"},
        ]}}
    return fetch


@pytest.fixture(autouse=True)
def clear_cache():
    nws._cache.update(hourly_url=None, periods=None, fetched=0.0)


def test_picks_the_hour_containing_the_time_and_converts_celsius():
    periods = nws.hourly_periods(fake_nws([]), now=lambda: 0)
    assert nws.temperature_at(datetime.fromisoformat("2026-10-17T13:30:00-07:00"), periods).temperature_f == 78
    assert nws.temperature_at(datetime.fromisoformat("2026-10-17T14:10:00-07:00"), periods).temperature_f == pytest.approx(80.6)


def test_time_outside_the_forecast_gets_the_nearest_hour():
    periods = nws.hourly_periods(fake_nws([]), now=lambda: 0)
    assert nws.temperature_at(datetime.fromisoformat("2026-10-17T09:00:00-07:00"), periods).temperature_f == 78


def test_forecast_is_cached_and_points_lookup_happens_once():
    calls = []
    fetch = fake_nws(calls)
    nws.hourly_periods(fetch, now=lambda: 0)
    nws.hourly_periods(fetch, now=lambda: 60)
    assert len(calls) == 2
    nws.hourly_periods(fetch, now=lambda: nws.CACHE_S + 1)
    assert calls[2] == HOURLY and len(calls) == 3


def test_provider_failure_is_a_clear_503(monkeypatch):
    def broken(url):
        raise OSError("network down")
    monkeypatch.setattr(nws, "_fetch", broken)
    response = TestClient(app).get("/api/weather", params={"at": "2026-10-17T13:30:00-07:00"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "WEATHER_UNAVAILABLE"


def test_endpoint_returns_fahrenheit_and_source(monkeypatch):
    monkeypatch.setattr(nws, "_fetch", fake_nws([]))
    data = TestClient(app).get("/api/weather", params={"at": "2026-10-17T13:30:00-07:00"}).json()
    assert data["temperature_f"] == 78
    assert data["temperature_c"] == pytest.approx(25.56, abs=0.01)
    assert "National Weather Service" in data["source"]


def test_time_without_offset_is_rejected():
    assert TestClient(app).get("/api/weather", params={"at": "2026-10-17T13:30:00"}).status_code == 422
