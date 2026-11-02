
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from models import City
from services import CityNotFoundError


class DemoGeocodingClient:
    def __init__(self, entries: list[dict]):
        self.cities = {item["name"].casefold(): item for item in entries}

    def find_city(self, name: str) -> City:
        if not name.strip():
            raise ValueError("City name cannot be empty.")
        item = self.cities.get(name.strip().casefold())
        if item is None:
            raise CityNotFoundError(f"Demo city '{name}' was not found in input.json.")
        return City(item["name"], item["country"], item["latitude"], item["longitude"])


class DemoForecastProvider:

    source = "DEMO synthetic sample (not real weather)"
    forecast_days = 2

    def __init__(self, entries: list[dict], clock=None):
        self.cities = {(item["latitude"], item["longitude"]): item for item in entries}
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.request_count = 0

    def get_forecast(self, latitude: float, longitude: float) -> dict:
        self.request_count += 1
        item = self.cities[(latitude, longitude)]
        now = self.clock().astimezone(timezone.utc)

        starting_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        n = len(item["temperatures"])
        if n != len(item["precipitation_probabilities"]):
            raise ValueError("Demo input arrays must be equally long.")
        return {
            "utc_offset_seconds": 0,
            "hourly": {
                "time": [(starting_hour + timedelta(hours=i)).replace(tzinfo=None).isoformat(timespec="minutes")
                         for i in range(n)],
                "temperature_2m": item["temperatures"],
                "precipitation_probability": item["precipitation_probabilities"],
            },
        }


def load_demo(path: str | Path = "input.json") -> list[dict]:
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if data.get("sample_data_only") is not True or not isinstance(data.get("cities"), list):
        raise ValueError("input.json must contain a synthetic-demo cities array.")
    return data["cities"]
