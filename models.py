
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Callable


class WeatherDataError(ValueError):
    pass


@dataclass(frozen=True)
class City:
    name: str
    country: str
    latitude: float
    longitude: float


@dataclass(frozen=True)
class WeatherPoint:
    forecast_time: str
    temperature_c: float
    precipitation_probability: int


@dataclass(frozen=True)
class WeatherForecast:
    city: City
    retrieved_at: str
    points: tuple[WeatherPoint, ...]
    source: str
    from_cache: bool = False


class WeatherAdapter:

    def __init__(self, clock: Callable[[], datetime] | None = None):
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def _number(value, field: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (float, int)):
            raise WeatherDataError(f"Invalid numeric value in '{field}'.")
        number = float(value)
        if not isfinite(number):
            raise WeatherDataError(f"Non-finite value in '{field}'.")
        return number

    def normalize(self, payload: dict, city: City, source: str = "Open-Meteo") -> WeatherForecast:
        if not isinstance(payload, dict) or not isinstance(payload.get("hourly"), dict):
            raise WeatherDataError("Forecast response is missing the 'hourly' object.")

        hourly = payload["hourly"]
        fields = ("time", "temperature_2m", "precipitation_probability")
        lists = []
        for key in fields:
            value = hourly.get(key)
            if not isinstance(value, list):
                raise WeatherDataError(f"Forecast response is missing array '{key}'.")
            lists.append(value)
        if len({len(value) for value in lists}) != 1:
            raise WeatherDataError("Hourly arrays have inconsistent lengths.")

        offset_seconds = self._number(payload.get("utc_offset_seconds", 0), "utc_offset_seconds")
        if not -86400 < offset_seconds < 86400:
            raise WeatherDataError("Invalid UTC offset.")

        now = self.clock()
        if now.tzinfo is None:
            raise ValueError("Clock must produce timezone-aware UTC datetimes.")
        local_now = (now.astimezone(timezone.utc) + timedelta(seconds=offset_seconds)).replace(tzinfo=None)

        points: list[WeatherPoint] = []
        previous_time = None
        for stamp, temperature, probability in zip(*lists):
            if not isinstance(stamp, str):
                raise WeatherDataError("Invalid forecast timestamp.")
            try:
                moment = datetime.fromisoformat(stamp)
            except ValueError as exc:
                raise WeatherDataError(f"Invalid forecast timestamp: {stamp}.") from exc
            if moment.tzinfo is not None:
                raise WeatherDataError("Expected local forecast timestamps without an offset.")
            if previous_time is not None and moment <= previous_time:
                raise WeatherDataError("Forecast timestamps must be strictly increasing.")
            previous_time = moment
            if temperature is None or probability is None:

                continue
            temp = self._number(temperature, "temperature_2m")
            precip = self._number(probability, "precipitation_probability")
            if not 0 <= precip <= 100 or not precip.is_integer():
                raise WeatherDataError("Precipitation probability must be an integer from 0 to 100.")
            if moment >= local_now and len(points) < 3:
                points.append(WeatherPoint(stamp, temp, int(precip)))

        return WeatherForecast(
            city=city,
            retrieved_at=now.astimezone(timezone.utc).isoformat(timespec="seconds"),
            points=tuple(points),
            source=source,
        )
