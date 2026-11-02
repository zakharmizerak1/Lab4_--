
import sqlite3
from models import City, WeatherForecast, WeatherPoint
from storage import HistoryError, WeatherHistory
import pytest


def sample(city="Львів"):
    return WeatherForecast(
        City(city, "Ukraine", 49.84, 24.03), "2026-10-29T12:00:00+00:00",
        (WeatherPoint("2026-10-29T13:00", 12.5, 20),
         WeatherPoint("2026-10-29T14:00", 13.0, 50)), "Open-Meteo")


def test_database_created_and_persists_across_restarts(tmp_path):
    path = tmp_path / "weather_history.db"
    first = WeatherHistory(path)
    assert path.exists()
    assert first.save(sample()) == 2
    second = WeatherHistory(path)
    assert len(second.get_recent()) == 2
    assert second.get_recent()[0]["temperature_c"] == 13.0
    assert second.get_city("ЛЬВІВ")[0]["city"] == "Львів"


def test_city_filter_and_sql_injection_is_not_executed(tmp_path):
    db = WeatherHistory(tmp_path / "weather_history.db")
    db.save(sample())
    db.save(sample("Київ"))
    assert len(db.get_city("Львів")) == 2
    assert len(db.get_city("Київ")) == 2
    assert db.get_city("Львів' OR 1=1 --") == []
    assert len(db.get_recent()) == 4


def test_history_validates_limit(tmp_path):
    db = WeatherHistory(tmp_path / "weather_history.db")
    with pytest.raises(ValueError):
        db.get_recent(0)
    with pytest.raises(ValueError):
        db.get_city("Lviv", 101)


def test_missing_db_table_raises_readable_error(tmp_path):
    path = tmp_path / "weather_history.db"
    db = WeatherHistory(path)
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE forecast_history")
    with pytest.raises(HistoryError, match="Could not read"):
        db.get_recent()
    with pytest.raises(HistoryError, match="Could not save"):
        db.save(sample())


def test_invalid_database_directory_raises_error(tmp_path):
    with pytest.raises(HistoryError, match="Could not initialize"):
        WeatherHistory(tmp_path / "missing_subfolder" / "weather_history.db")
