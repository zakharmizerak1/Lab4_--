
from models import City, WeatherPoint, WeatherForecast
from strategies import ClothingStrategy, RainStrategy, WalkStrategy, RecommendationStrategy


def create_weather(temps, risks):
    return WeatherForecast(
        City("Lviv", "Ukraine", 49.84, 24.03), "2026-10-29T12:00:00+00:00",
        tuple(WeatherPoint(f"2026-10-29T{13+i:02}:00", t, p)
              for i, (t, p) in enumerate(zip(temps, risks))),
        "DEMO"
    )


def test_three_strategies_have_distinct_rules():
    forecast = create_weather([12, 14, 15], [20, 60, 80])
    assert isinstance(WalkStrategy(), RecommendationStrategy)
    assert "indoor" in WalkStrategy().recommend(forecast)
    assert "light jacket" in ClothingStrategy().recommend(forecast)
    assert "umbrella" in RainStrategy().recommend(forecast)


def test_walk_temperature_rules():
    assert "cold" in WalkStrategy().recommend(create_weather([-7], [0]))
    assert "hot" in WalkStrategy().recommend(create_weather([35], [0]))
    assert "suitable" in WalkStrategy().recommend(create_weather([21], [0]))
    assert "shelter" in WalkStrategy().recommend(create_weather([21], [45]))


def test_clothing_rules():
    assert "warm coat" in ClothingStrategy().recommend(create_weather([-2], [5]))
    assert "jacket and warm" in ClothingStrategy().recommend(create_weather([5], [5]))
    assert "Light clothing" in ClothingStrategy().recommend(create_weather([24], [80]))
    assert "removable layers" in ClothingStrategy().recommend(create_weather([15, 25], [5, 5]))


def test_rain_strategy_counts_risky_intervals():
    assert "umbrella" in RainStrategy().recommend(create_weather([15, 15], [50, 55]))
    assert "waterproof jacket" in RainStrategy().recommend(create_weather([15], [42]))
    assert "less likely" in RainStrategy().recommend(create_weather([15], [10]))


def test_empty_forecast_does_not_crash():
    empty = create_weather([], [])
    assert all("No upcoming" in cls().recommend(empty)
               for cls in (WalkStrategy, ClothingStrategy, RainStrategy))
