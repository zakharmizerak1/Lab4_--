
from datetime import datetime, timezone
import pytest

from models import City, WeatherAdapter, WeatherDataError


NOW = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
CITY = City("Lviv", "Ukraine", 49.84, 24.03)


def sample():
    return {"utc_offset_seconds": 7200, "hourly": {
        "time": ["2026-10-29T13:00", "2026-10-29T14:00", "2026-10-29T15:00",
                 "2026-10-29T16:00", "2026-10-29T17:00"],
        "temperature_2m": [10, 11, 12, 13, 14],
        "precipitation_probability": [10, 20, 30, 40, 50],
    }}


def test_adapter_chooses_next_three_city_local_hours():
    weather = WeatherAdapter(clock=lambda: NOW).normalize(sample(), CITY)
    assert len(weather.points) == 3
    assert [p.forecast_time for p in weather.points] == [
        "2026-10-29T14:00", "2026-10-29T15:00", "2026-10-29T16:00"]
    assert [p.temperature_c for p in weather.points] == [11.0, 12.0, 13.0]
    assert weather.retrieved_at == "2026-10-29T12:00:00+00:00"
    assert weather.city == CITY


def test_adapter_handles_fewer_than_three_future_hours():
    data = sample()
    for key in data["hourly"]:
        data["hourly"][key] = data["hourly"][key][:2]
    weather = WeatherAdapter(clock=lambda: NOW).normalize(data, CITY)
    assert len(weather.points) == 1


def test_adapter_handles_zero_upcoming_hours():
    data = sample()
    data["hourly"]["time"] = ["2026-10-28T13:00", "2026-10-28T14:00",
                               "2026-10-28T15:00", "2026-10-28T16:00", "2026-10-28T17:00"]
    assert WeatherAdapter(clock=lambda: NOW).normalize(data, CITY).points == ()


def test_adapter_skips_null_values():
    data = sample()
    data["hourly"]["temperature_2m"][1] = None
    weather = WeatherAdapter(clock=lambda: NOW).normalize(data, CITY)
    assert weather.points[0].forecast_time == "2026-10-29T15:00"


@pytest.mark.parametrize("change", [
    lambda d: d.pop("hourly"),
    lambda d: d["hourly"].pop("temperature_2m"),
    lambda d: d["hourly"]["time"].pop(),
    lambda d: d["hourly"]["temperature_2m"].__setitem__(0, "cold"),
    lambda d: d["hourly"]["precipitation_probability"].__setitem__(0, -1),
    lambda d: d["hourly"]["precipitation_probability"].__setitem__(0, 101),
    lambda d: d["hourly"]["time"].__setitem__(0, "not-a-time"),
    lambda d: d["hourly"]["time"].__setitem__(2, "2026-10-29T12:00"),
])
def test_adapter_rejects_malformed_forecast(change):
    data = sample()
    change(data)
    with pytest.raises(WeatherDataError):
        WeatherAdapter(clock=lambda: NOW).normalize(data, CITY)
