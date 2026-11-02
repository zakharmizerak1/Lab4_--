
from unittest.mock import Mock
import pytest
import requests

from models import WeatherDataError
from services import (CityNotFoundError, ExternalServiceError, ForecastProvider,
                      GeocodingClient, request_json)


class FakeResponse:
    def __init__(self, payload, error=None):
        self.payload = payload
        self.error = error

    def raise_for_status(self):
        if self.error:
            raise self.error

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def session_with(response):
    return Mock(get=Mock(return_value=response))


def test_geocode_success_and_correct_parameters():
    session = session_with(FakeResponse({"results": [{"name": "Львів",
        "country": "Ukraine", "latitude": 49.84, "longitude": 24.03}]}))
    client = GeocodingClient(session)
    city = client.find_city("Lviv")
    assert city.name == "Львів"
    assert city.latitude == 49.84
    _, kwargs = session.get.call_args
    assert kwargs["params"]["name"] == "Lviv"
    assert kwargs["timeout"] == 10


def test_unknown_city():
    client = GeocodingClient(session_with(FakeResponse({"results": []})))
    with pytest.raises(CityNotFoundError):
        client.find_city("Unknownplace000")


def test_forecast_provider_uses_hourly_api():
    session = session_with(FakeResponse({"hourly": {"time": [],
        "temperature_2m": [], "precipitation_probability": []}}))
    provider = ForecastProvider(session)
    provider.get_forecast(49.84, 24.03)
    _, kwargs = session.get.call_args
    assert kwargs["params"]["timezone"] == "auto"
    assert kwargs["params"]["hourly"] == "temperature_2m,precipitation_probability"
    assert provider.request_count == 1


def test_timeout():
    session = Mock(get=Mock(side_effect=requests.Timeout("expired")))
    with pytest.raises(ExternalServiceError, match="timed out"):
        GeocodingClient(session).find_city("Lviv")


def test_http_error():
    session = session_with(FakeResponse({}, requests.HTTPError("503 unavailable")))
    with pytest.raises(ExternalServiceError, match="HTTP"):
        GeocodingClient(session).find_city("Lviv")


def test_connection_error():
    session = Mock(get=Mock(side_effect=requests.ConnectionError("offline")))
    with pytest.raises(ExternalServiceError, match="connect"):
        GeocodingClient(session).find_city("Lviv")


def test_invalid_json():
    with pytest.raises(WeatherDataError, match="JSON"):
        request_json(session_with(FakeResponse(ValueError("bad json"))), "example", {})


def test_invalid_geocoding_data():
    with pytest.raises(WeatherDataError, match="invalid city data"):
        GeocodingClient(session_with(FakeResponse({"results": [
            {"name": "Lviv", "country": "Ukraine", "latitude": 999, "longitude": 1}
        ]}))).find_city("Lviv")


def test_api_error_message():
    with pytest.raises(ExternalServiceError, match="bad coordinate"):
        request_json(session_with(FakeResponse({"error": True, "reason": "bad coordinate"})),
                     "example", {})
