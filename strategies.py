
from abc import ABC, abstractmethod

from models import WeatherForecast


class RecommendationStrategy(ABC):

    @abstractmethod
    def recommend(self, forecast: WeatherForecast) -> str:
        raise NotImplementedError


class WalkStrategy(RecommendationStrategy):

    def recommend(self, forecast: WeatherForecast) -> str:
        if not forecast.points:
            return "No upcoming forecast intervals available for a walking recommendation."
        temperatures = [point.temperature_c for point in forecast.points]
        highest_rain_risk = max(point.precipitation_probability for point in forecast.points)
        average_temp = sum(temperatures) / len(temperatures)
        if highest_rain_risk >= 70:
            return "High chance of rain: consider an indoor activity instead of a walk."
        if average_temp < -5:
            return "It is very cold: a short walk would be more comfortable than a long one."
        if average_temp > 30:
            return "It is very hot: consider walking at a cooler time of day."
        if highest_rain_risk >= 40:
            return "A walk is possible, but plan a short route with shelter nearby."
        return "Conditions look suitable for an outdoor walk."


class ClothingStrategy(RecommendationStrategy):

    def recommend(self, forecast: WeatherForecast) -> str:
        if not forecast.points:
            return "No upcoming forecast intervals available for a clothing recommendation."
        temperatures = [point.temperature_c for point in forecast.points]
        coldest, warmest = min(temperatures), max(temperatures)
        if coldest < 0:
            clothing = "Wear a warm coat, hat and gloves."
        elif coldest < 10:
            clothing = "Wear a jacket and warm layers."
        elif coldest < 20:
            clothing = "Wear a light jacket or sweater."
        else:
            clothing = "Light clothing should be comfortable."
        if warmest - coldest >= 8:
            clothing += " Use removable layers: temperatures vary considerably."
        return clothing


class RainStrategy(RecommendationStrategy):

    def recommend(self, forecast: WeatherForecast) -> str:
        if not forecast.points:
            return "No upcoming forecast intervals available for a rain recommendation."
        chances = [point.precipitation_probability for point in forecast.points]
        maximum = max(chances)
        risky_intervals = sum(value >= 50 for value in chances)
        if maximum >= 70 or risky_intervals >= 2:
            return "Take an umbrella and waterproof footwear: rain is quite likely."
        if maximum >= 40:
            return "Consider a small umbrella or a waterproof jacket."
        return "Rain is less likely; an umbrella may not be necessary."


STRATEGIES = {
    "1": ("Walking", WalkStrategy()),
    "2": ("Clothing", ClothingStrategy()),
    "3": ("Rain preparation", RainStrategy()),
}
