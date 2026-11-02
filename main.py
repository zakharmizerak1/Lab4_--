
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from demo_data import DemoForecastProvider, DemoGeocodingClient, load_demo
from models import WeatherAdapter, WeatherForecast, WeatherDataError
from services import (CityNotFoundError, ExternalServiceError, ForecastCacheDecorator,
                      ForecastProvider, GeocodingClient, WeatherFacade)
from storage import HistoryError, WeatherHistory
from strategies import STRATEGIES


ROOT = Path(__file__).resolve().parent
INPUT_FILE = ROOT / "input.json"
OUTPUT_FILE = ROOT / "output.json"
DATABASE_FILE = ROOT / "weather_history.db"


def show_forecast(forecast: WeatherForecast) -> None:
    city = forecast.city
    print(f"\nWeather for {city.name}, {city.country} ({city.latitude:.4f}, {city.longitude:.4f})")
    print(f"Source: {forecast.source}")
    print(f"Retrieved/used at: {forecast.retrieved_at} (UTC)")
    print(f"Forecast cache: {'HIT' if forecast.from_cache else 'MISS'}")
    if not forecast.points:
        print("No upcoming hourly intervals were available.")
        return
    print(f"{'Forecast time (city local)':<28} {'Temp (C)':>10} {'Rain (%)':>10}")
    for point in forecast.points:
        print(f"{point.forecast_time:<28} {point.temperature_c:>10.1f} "
              f"{point.precipitation_probability:>10d}")


def show_recommendations(forecast: WeatherForecast) -> dict[str, str]:
    print("\nRecommendations for the SAME weather data:")
    outputs = {}
    for _, (label, strategy) in STRATEGIES.items():
        text = strategy.recommend(forecast)
        outputs[label] = text
        print(f"  {label}: {text}")
    return outputs


def show_history(rows: list[dict]) -> None:
    if not rows:
        print("No matching history records.")
        return
    print(f"\n{'ID':<5} {'City':<12} {'Forecast time':<19} "
          f"{'C':>6} {'Rain %':>7}   {'Retrieved (UTC)':<25}")
    for row in rows:
        print(f"{row['id']:<5} {row['city'][:12]:<12} {row['forecast_time']:<19} "
              f"{row['temperature_c']:>6.1f} {row['precipitation_probability']:>7d}   "
              f"{row['retrieved_at']}")


class WeatherAssistant:

    def __init__(self, db_path=DATABASE_FILE, input_path=INPUT_FILE):
        self.history = WeatherHistory(db_path)
        entries = load_demo(input_path)
        self.demo_provider = ForecastCacheDecorator(DemoForecastProvider(entries))
        self.demo = WeatherFacade(
            DemoGeocodingClient(entries), self.demo_provider, WeatherAdapter(), self.history
        )
        self.live_provider = ForecastCacheDecorator(ForecastProvider())
        self.live = WeatherFacade(
            GeocodingClient(), self.live_provider, WeatherAdapter(), self.history
        )
        self.last_forecast: WeatherForecast | None = None
        self.last_city: str | None = None
        self.last_mode: str | None = None
        self.results: list[dict] = []

    def get_weather(self, name: str, mode: str) -> WeatherForecast:
        facade = self.demo if mode == "demo" else self.live
        forecast = facade.get_weather(name)
        self.last_forecast = forecast
        self.last_city = name
        self.last_mode = mode
        show_forecast(forecast)
        outputs = show_recommendations(forecast)
        self.results.append({
            "city": forecast.city.name,
            "country": forecast.city.country,
            "latitude": forecast.city.latitude,
            "longitude": forecast.city.longitude,
            "retrieved_at": forecast.retrieved_at,
            "source": forecast.source,
            "from_cache": forecast.from_cache,
            "points": [vars(p) for p in forecast.points],
            "recommendations": outputs,
        })
        return forecast

    def run_demo(self) -> None:
        print("\n*** OFFLINE DEMO: fictional examples, NOT a live weather forecast ***")
        for city_name in ("Lviv", "Kyiv", "Odesa"):
            self.get_weather(city_name, "demo")
        print("\nRepeating Lviv during TTL to demonstrate a cache HIT:")
        self.get_weather("Lviv", "demo")
        print(f"Mock provider calls: {self.demo_provider.request_count}; "
              f"cache hits: {self.demo_provider.hits}; "
              f"cache misses: {self.demo_provider.misses}")

    def save_output(self, path=OUTPUT_FILE) -> None:
        data = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "warning": "DEMO source means fictional sample data; only Open-Meteo is live.",
            "forecasts": self.results,
            "cache_stats": {
                "demo": {"provider_calls_not_http": self.demo_provider.request_count,
                         "hits": self.demo_provider.hits, "misses": self.demo_provider.misses},
                "live": {"actual_forecast_http_requests": self.live_provider.request_count,
                         "hits": self.live_provider.hits, "misses": self.live_provider.misses},
            },
            "latest_history": self.history.get_recent(50),
        }
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
        print(f"\nResults saved to: {path}")

    def menu(self) -> None:
        while True:
            print("\n========== WEATHER ASSISTANT ==========")
            print("1. Run example from input.json (OFFLINE DEMO)")
            print("2. Get LIVE weather for a city (Open-Meteo)")
            print("3. Choose a recommendation strategy / compare all")
            print("4. Show latest SQLite history")
            print("5. Show SQLite history for one city")
            print("6. Repeat last query (demonstrate TTL cache)")
            print("7. Save results to output.json")
            print("8. Save and exit")
            try:
                choice = input("\nChoose an action (1-8): ").strip()
                if choice == "1":
                    self.run_demo()
                elif choice == "2":
                    name = input("Enter city name: ").strip()
                    self.get_weather(name, "live")
                elif choice == "3":
                    if self.last_forecast:
                        print("Choose: 1 - Walking, 2 - Clothing, 3 - Rain preparation, A - All")
                        strategy_choice = input("Strategy: ").strip().upper()
                        if strategy_choice == "A":
                            show_recommendations(self.last_forecast)
                        elif strategy_choice in STRATEGIES:
                            label, strategy = STRATEGIES[strategy_choice]
                            print(f"{label}: {strategy.recommend(self.last_forecast)}")
                        else:
                            print("Unknown strategy. Choose 1, 2, 3 or A.")
                    else:
                        print("Get a forecast first (option 1 or 2).")
                elif choice == "4":
                    show_history(self.history.get_recent())
                elif choice == "5":
                    name = input("Enter city name: ").strip()
                    show_history(self.history.get_city(name))
                elif choice == "6":
                    if self.last_city is None or self.last_mode is None:
                        print("Get a forecast first (option 1 or 2).")
                    else:
                        print("\nRepeating query for:", self.last_city)
                        self.get_weather(self.last_city, self.last_mode)
                        provider = (self.demo_provider if self.last_mode == "demo"
                                    else self.live_provider)
                        print(f"Provider calls: {provider.request_count}; "
                              f"cache hits: {provider.hits}; cache misses: {provider.misses}")
                elif choice == "7":
                    self.save_output()
                elif choice == "8":
                    self.save_output()
                    print("Goodbye!")
                    break
                else:
                    print("Unknown command. Please choose a number from 1 to 8.")
            except (ValueError, CityNotFoundError, ExternalServiceError, WeatherDataError,
                    HistoryError, OSError, json.JSONDecodeError, KeyError) as exc:
                print(f"Error: {exc}")
            except (KeyboardInterrupt, EOFError):
                print("\nProgram stopped by the user.")
                break


def main():
    parser = argparse.ArgumentParser(description="Open-Meteo Weather Assistant")
    parser.add_argument("--auto", "--demo", action="store_true",
                        help="Run the sample input.json entirely offline and save output.json")
    parser.add_argument("--live", metavar="CITY", help="Query a real city using the live API")
    args = parser.parse_args()
    try:
        app = WeatherAssistant()
        if args.auto:
            app.run_demo()
            app.save_output()
        elif args.live:
            app.get_weather(args.live, "live")
            app.save_output()
        else:
            app.menu()
    except (ValueError, ExternalServiceError, WeatherDataError, HistoryError,
            OSError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
