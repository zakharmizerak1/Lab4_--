
from datetime import datetime, timezone
import pytest

from demo_data import DemoForecastProvider, DemoGeocodingClient
from models import WeatherAdapter
from services import ForecastCacheDecorator, WeatherFacade
from storage import WeatherHistory


NOW = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)


@pytest.fixture
def entries():
    return [{"name": "Lviv", "country": "Ukraine", "latitude": 49.8,
             "longitude": 24.0, "temperatures": [10, 11, 12],
             "precipitation_probabilities": [25, 50, 75]},
            {"name": "Kyiv", "country": "Ukraine", "latitude": 50.5,
             "longitude": 30.5, "temperatures": [20, 21, 22],
             "precipitation_probabilities": [0, 0, 0]}]


def test_cache_hit_ttl_expiration_and_different_locations(entries):
    current_time = [100.0]
    provider = DemoForecastProvider(entries, clock=lambda: NOW)
    cache = ForecastCacheDecorator(provider, ttl_seconds=600, timer=lambda: current_time[0])
    data1 = cache.get_forecast(49.8, 24.0)
    assert provider.request_count == 1
    assert not cache.last_cache_hit

    data1["hourly"]["temperature_2m"][0] = 1000
    current_time[0] += 10
    data2 = cache.get_forecast(49.8, 24.0)
    assert provider.request_count == 1
    assert cache.last_cache_hit
    assert data2["hourly"]["temperature_2m"][0] == 10

    cache.get_forecast(50.5, 30.5)
    assert provider.request_count == 2
    assert not cache.last_cache_hit

    current_time[0] = 700.0
    cache.get_forecast(49.8, 24.0)
    assert provider.request_count == 3
    assert not cache.last_cache_hit
    assert cache.hits == 1 and cache.misses == 3


def test_facade_uses_patterns_and_saves_history(entries, tmp_path):
    history = WeatherHistory(tmp_path / "history.db")
    cache = ForecastCacheDecorator(DemoForecastProvider(entries, clock=lambda: NOW))
    facade = WeatherFacade(DemoGeocodingClient(entries), cache,
                           WeatherAdapter(clock=lambda: NOW), history)
    first = facade.get_weather("Lviv")
    second = facade.get_weather("Lviv")
    assert not first.from_cache and second.from_cache
    assert cache.request_count == 1
    assert len(first.points) == 3
    assert len(history.get_city("lViV")) == 6
    assert history.get_recent(1)[0]["source"].startswith("DEMO")


def test_cache_ttl_zero_always_refetches(entries):
    cache = ForecastCacheDecorator(DemoForecastProvider(entries, clock=lambda: NOW),
                                   ttl_seconds=0, timer=lambda: 10)
    cache.get_forecast(49.8, 24.0)
    cache.get_forecast(49.8, 24.0)
    assert cache.request_count == 2
    assert cache.hits == 0


def test_cache_rejects_negative_ttl(entries):
    with pytest.raises(ValueError):
        ForecastCacheDecorator(DemoForecastProvider(entries), ttl_seconds=-1)
