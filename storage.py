
from contextlib import closing
import sqlite3
from pathlib import Path

from models import WeatherForecast


class HistoryError(RuntimeError):
    pass


class WeatherHistory:

    def __init__(self, db_path: str | Path = "weather_history.db"):
        self.db_path = str(db_path)
        self._init_database()

    def _init_database(self) -> None:
        try:
            with closing(sqlite3.connect(self.db_path)) as connection:
                with connection:
                    connection.execute("""
                        CREATE TABLE IF NOT EXISTS forecast_history (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            city TEXT NOT NULL,
                            city_key TEXT NOT NULL,
                            latitude REAL NOT NULL,
                            longitude REAL NOT NULL,
                            retrieved_at TEXT NOT NULL,
                            forecast_time TEXT NOT NULL,
                            temperature_c REAL NOT NULL,
                            precipitation_probability INTEGER NOT NULL
                                CHECK(precipitation_probability BETWEEN 0 AND 100),
                            source TEXT NOT NULL
                        )
                    """)
                    connection.execute("""
                        CREATE INDEX IF NOT EXISTS idx_city_key_id
                        ON forecast_history(city_key, id DESC)
                    """)
        except sqlite3.Error as exc:
            raise HistoryError(f"Could not initialize SQLite history: {exc}") from exc

    def save(self, forecast: WeatherForecast) -> int:
        records = [(
            forecast.city.name,
            forecast.city.name.casefold(),
            forecast.city.latitude,
            forecast.city.longitude,
            forecast.retrieved_at,
            point.forecast_time,
            point.temperature_c,
            point.precipitation_probability,
            forecast.source,
        ) for point in forecast.points]
        if not records:
            return 0
        try:
            with closing(sqlite3.connect(self.db_path)) as connection:
                with connection:
                    connection.executemany("""
                        INSERT INTO forecast_history
                        (city, city_key, latitude, longitude, retrieved_at,
                         forecast_time, temperature_c, precipitation_probability, source)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, records)
        except sqlite3.Error as exc:
            raise HistoryError(f"Could not save forecast to SQLite: {exc}") from exc
        return len(records)

    def _read(self, query: str, params: tuple) -> list[dict]:
        try:
            with closing(sqlite3.connect(self.db_path)) as connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute(query, params).fetchall()
                return [dict(row) for row in rows]
        except sqlite3.Error as exc:
            raise HistoryError(f"Could not read SQLite history: {exc}") from exc

    def get_recent(self, limit: int = 10) -> list[dict]:
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
            raise ValueError("Limit must be an integer between 1 and 100.")
        return self._read("""
            SELECT id, city, latitude, longitude, retrieved_at, forecast_time,
                   temperature_c, precipitation_probability, source
            FROM forecast_history ORDER BY id DESC LIMIT ?
        """, (limit,))

    def get_city(self, city: str, limit: int = 20) -> list[dict]:
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
            raise ValueError("Limit must be an integer between 1 and 100.")
        if not city.strip():
            raise ValueError("City name cannot be empty.")
        return self._read("""
            SELECT id, city, latitude, longitude, retrieved_at, forecast_time,
                   temperature_c, precipitation_probability, source
            FROM forecast_history WHERE city_key = ? ORDER BY id DESC LIMIT ?
        """, (city.strip().casefold(), limit))
