from __future__ import annotations

from datetime import date
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from travel_assistant.config import DESTINATION, LATITUDE, LONGITUDE, TIMEZONE

API_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT = 15.0
MAX_FORECAST_DAYS = 16

WMO_CODES: dict[int, tuple[str, bool]] = {
    0: ("Clear sky", True),
    1: ("Mainly clear", True),
    2: ("Partly cloudy", True),
    3: ("Overcast", True),
    45: ("Fog", False),
    48: ("Depositing rime fog", False),
    51: ("Light drizzle", False),
    53: ("Moderate drizzle", False),
    55: ("Dense drizzle", False),
    56: ("Light freezing drizzle", False),
    57: ("Dense freezing drizzle", False),
    61: ("Slight rain", False),
    63: ("Moderate rain", False),
    65: ("Heavy rain", False),
    66: ("Light freezing rain", False),
    67: ("Heavy freezing rain", False),
    71: ("Slight snow fall", False),
    73: ("Moderate snow fall", False),
    75: ("Heavy snow fall", False),
    77: ("Snow grains", False),
    80: ("Slight rain showers", False),
    81: ("Moderate rain showers", False),
    82: ("Violent rain showers", False),
    85: ("Slight snow showers", False),
    86: ("Heavy snow showers", False),
    95: ("Thunderstorm", False),
    96: ("Thunderstorm with slight hail", False),
    99: ("Thunderstorm with heavy hail", False),
}

mcp = FastMCP("weather")


def describe(code: int | None) -> tuple[str, bool]:
    if code is None:
        return "Unknown", True
    return WMO_CODES.get(int(code), (f"Unknown condition (WMO {code})", True))


def _error(message: str, detail: str = "") -> dict[str, Any]:
    return {
        "status": "error",
        "tool_source": "MCP weather server (Open-Meteo)",
        "error": message,
        "detail": detail,
        "guidance": (
            "Weather data is unavailable. Say so explicitly and offer the itinerary "
            "without weather adjustment. Do not estimate or recall a forecast."
        ),
    }


def _call_api(params: dict[str, Any]) -> dict[str, Any] | dict[str, str]:
    query = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "timezone": TIMEZONE,
        **params,
    }
    try:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
            response = client.get(API_URL, params=query)
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException:
        return _error("Weather service timed out", f"No response within {TIMEOUT}s")
    except httpx.HTTPStatusError as exc:
        return _error("Weather service returned an error", f"HTTP {exc.response.status_code}")
    except httpx.HTTPError as exc:
        return _error("Could not reach the weather service", str(exc))
    except ValueError as exc:
        return _error("Weather service returned malformed data", str(exc))


@mcp.tool()
def get_current_weather() -> dict[str, Any]:
    """Get current weather conditions in Singapore right now.

    Use for questions about weather at this moment ("what's the weather like?",
    "is it raining now?"). For anything about later today or future days, use
    get_weather_forecast instead.
    """
    payload = _call_api(
        {
            "current": (
                "temperature_2m,apparent_temperature,relative_humidity_2m,"
                "precipitation,weather_code,wind_speed_10m"
            )
        }
    )
    if payload.get("status") == "error":
        return payload

    current = payload.get("current", {})
    condition, outdoor_friendly = describe(current.get("weather_code"))

    return {
        "status": "ok",
        "tool_source": "MCP weather server (Open-Meteo)",
        "location": DESTINATION,
        "observed_at": current.get("time"),
        "condition": condition,
        "temperature_c": current.get("temperature_2m"),
        "feels_like_c": current.get("apparent_temperature"),
        "humidity_pct": current.get("relative_humidity_2m"),
        "precipitation_mm": current.get("precipitation"),
        "wind_speed_kmh": current.get("wind_speed_10m"),
        "outdoor_friendly": outdoor_friendly,
    }


@mcp.tool()
def get_weather_forecast(days: int = 3) -> dict[str, Any]:
    """Get a day-by-day weather forecast for Singapore.

    Use when planning ahead: multi-day itineraries, "will it rain during my trip?",
    or deciding between indoor and outdoor activities on a future day.

    Args:
        days: Number of days to forecast starting today, 1 to 16. Defaults to 3.
            For a three-day itinerary, pass 3.
    """
    if not isinstance(days, int) or days < 1:
        return _error("Invalid `days`", f"Expected an integer >= 1, got {days!r}")
    if days > MAX_FORECAST_DAYS:
        return _error(
            f"Forecast limited to {MAX_FORECAST_DAYS} days",
            f"Requested {days}. Ask the user to plan within {MAX_FORECAST_DAYS} days.",
        )

    payload = _call_api(
        {
            "daily": (
                "weather_code,temperature_2m_max,temperature_2m_min,"
                "precipitation_sum,precipitation_probability_max"
            ),
            "forecast_days": days,
        }
    )
    if payload.get("status") == "error":
        return payload

    daily = payload.get("daily", {})
    dates = daily.get("time", [])

    forecast = []
    for index, day in enumerate(dates):
        condition, outdoor_friendly = describe(daily.get("weather_code", [])[index])
        rain_chance = daily.get("precipitation_probability_max", [])[index]

        forecast.append(
            {
                "date": day,
                "weekday": date.fromisoformat(day).strftime("%A"),
                "condition": condition,
                "temp_max_c": daily.get("temperature_2m_max", [])[index],
                "temp_min_c": daily.get("temperature_2m_min", [])[index],
                "precipitation_mm": daily.get("precipitation_sum", [])[index],
                "rain_probability_pct": rain_chance,
                "outdoor_friendly": outdoor_friendly and (rain_chance or 0) < 60,
            }
        )

    return {
        "status": "ok",
        "tool_source": "MCP weather server (Open-Meteo)",
        "location": DESTINATION,
        "days": len(forecast),
        "forecast": forecast,
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
