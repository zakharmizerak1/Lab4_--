
from copy import deepcopy
from dataclasses import replace
import time
from typing import Callable

import requests

from models import City, WeatherAdapter, WeatherDataError, WeatherForecast


class ExternalServiceError(RuntimeError):
    pass


class CityNotFoundError(ValueError):
    pass


def request_json(session, url: str, params: dict) -> dict:
    try:
        response = session.get(url, params=params, timeout=10)
        response.raise_for_status()
    except requests.Timeout as exc:
        raise ExternalServiceError("Weather service timed out. Please try again.") from exc
    except requests.HTTPError as exc:
        raise ExternalServiceError(f"Weather service returned an HTTP error: {exc}") from exc
    except requests.RequestException as exc:
        raise ExternalServiceError(f"Could not connect to the weather service: {exc}") from exc
    try:
        result = response.json()
    except (ValueError, TypeError) as exc:
        raise WeatherDataError("Weather service returned invalid JSON.") from exc
    if not isinstance(result, dict):
        raise WeatherDataError("Weather service JSON response must be an object.")
    if result.get("error") is True:
        raise ExternalServiceError(str(result.get("reason", "Weather service error.")))
    return result


class GeocodingClient:

    URL = "https://geocoding-api.open-meteo.com/v1/search"

    def __init__(self, session=None):
        self.session = session if session is not None else requests.Session()

    def find_city(self, name: str) -> City:
        name = name.strip()
        if not name:
            raise ValueError("City name cannot be empty.")
        response = request_json(self.session, self.URL, {
            "name": name, "count": 1, "language": "uk", "format": "json"
        })
        results = response.get("results", [])
        if not isinstance(results, list):
            raise WeatherDataError("Geocoding response has invalid 'results'.")
        if not results:
            raise CityNotFoundError(f"City '{name}' was not found.")
        match = results[0]
        if not isinstance(match, dict):
            raise WeatherDataError("Geocoding result must be an object.")
        try:
            title, country = match["name"], match["country"]
            lat, lon = match["latitude"], match["longitude"]
            if not isinstance(title, str) or not title.strip():
                raise ValueError("invalid city name")
            if not isinstance(country, str) or not country.strip():
                raise ValueError("invalid country")
            for value in (lat, lon):
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError("invalid coordinates")
            latitude, longitude = float(lat), float(lon)
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                raise ValueError("coordinates out of range")
        except (KeyError, ValueError, TypeError, OverflowError) as exc:
            raise WeatherDataError("Geocoding response contains invalid city data.") from exc
        return City(title, country, latitude, longitude)


class ForecastProvider:

    URL = "https://api.open-meteo.com/v1/forecast"
    source = "Open-Meteo"
    forecast_days = 2

    def __init__(self, session=None):
        self.session = session if session is not None else requests.Session()
        self.request_count = 0

    def get_forecast(self, latitude: float, longitude: float) -> dict:
        self.request_count += 1
        return request_json(self.session, self.URL, {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": "temperature_2m,precipitation_probability",
            "forecast_days": self.forecast_days,
            "timezone": "auto",
        })


class ForecastCacheDecorator:

    def __init__(self, provider, ttl_seconds: float = 600,
                 timer: Callable[[], float] | None = None):
        if ttl_seconds < 0:
            raise ValueError("TTL must be non-negative.")
        self.provider = provider
        self.ttl_seconds = ttl_seconds
        self.timer = timer if timer is not None else time.monotonic
        self.cache: dict[tuple[float, float, int], tuple[float, dict]] = {}
        self.hits = 0
        self.misses = 0
        self.last_cache_hit = False
        self.source = provider.source

    @property
    def request_count(self) -> int:
        return self.provider.request_count

    def get_forecast(self, latitude: float, longitude: float) -> dict:


        key = (round(latitude, 6), round(longitude, 6), self.provider.forecast_days)
        now = self.timer()
        entry = self.cache.get(key)
        if entry is not None and now < entry[0]:
            self.hits += 1
            self.last_cache_hit = True
            return deepcopy(entry[1])

        self.misses += 1
        self.last_cache_hit = False
        response = self.provider.get_forecast(latitude, longitude)
        self.cache[key] = (self.timer() + self.ttl_seconds, deepcopy(response))
        return deepcopy(response)


class WeatherFacade:

    def __init__(self, geocoder, forecast_provider, adapter: WeatherAdapter, history):
        self.geocoder = geocoder
        self.forecast_provider = forecast_provider
        self.adapter = adapter
        self.history = history

    def get_weather(self, city_name: str) -> WeatherForecast:
        city = self.geocoder.find_city(city_name)
        payload = self.forecast_provider.get_forecast(city.latitude, city.longitude)
        result = self.adapter.normalize(payload, city, source=self.forecast_provider.source)
        result = replace(result, from_cache=self.forecast_provider.last_cache_hit)
        self.history.save(result)
        return result
