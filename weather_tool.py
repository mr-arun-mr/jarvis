"""Weather (Open-Meteo, no API key) and time."""
import json
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

import config

KEYWORDS = ["weather", "temperature", "rain", "forecast", "umbrella", "hot", "cold", "time", "date", "day is"]

CODES = {0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast", 45: "fog", 48: "fog",
         51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 61: "light rain", 63: "rain", 65: "heavy rain",
         71: "light snow", 73: "snow", 75: "heavy snow", 80: "showers", 81: "showers", 82: "heavy showers",
         95: "thunderstorm", 96: "thunderstorm with hail", 99: "thunderstorm with hail"}


def _json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=15) as r:
        return json.load(r)


def get_weather(city: str = "") -> str:
    """Current conditions and a 3-day outlook. Uses the default city from config.json if none is given."""
    city = (city or config.load()["default_city"]).strip()
    if not city:
        return "ERROR: Which city? Ask the user, or set default_city in config.json."
    try:
        geo = _json("https://geocoding-api.open-meteo.com/v1/search?count=1&name=" + urllib.parse.quote(city))
        if not geo.get("results"):
            return f"ERROR: Could not find a place called '{city}'."
        p = geo["results"][0]
        q = urllib.parse.urlencode({
            "latitude": p["latitude"], "longitude": p["longitude"], "timezone": "auto", "forecast_days": 3,
            "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
        })
        w = _json("https://api.open-meteo.com/v1/forecast?" + q)
    except OSError as e:
        return f"ERROR: Weather service unreachable ({e})."
    c, d = w["current"], w["daily"]
    lines = [f"{p['name']}, {p.get('country', '')}: {c['temperature_2m']}C (feels {c['apparent_temperature']}C), "
             f"{CODES.get(c['weather_code'], 'unknown')}, wind {c['wind_speed_10m']} km/h"]
    for i, day in enumerate(d["time"]):
        lines.append(f"- {day}: {d['temperature_2m_min'][i]} to {d['temperature_2m_max'][i]}C, "
                     f"{CODES.get(d['weather_code'][i], '?')}, rain chance {d['precipitation_probability_max'][i]}%")
    return "\n".join(lines)


ALIASES = {"india": "Asia/Kolkata", "mumbai": "Asia/Kolkata", "delhi": "Asia/Kolkata", "bangalore": "Asia/Kolkata",
           "uk": "Europe/London", "pst": "America/Los_Angeles", "est": "America/New_York",
           "san francisco": "America/Los_Angeles", "china": "Asia/Shanghai", "japan": "Asia/Tokyo"}


def _resolve_zone(name: str) -> str:
    """Accept 'Asia/Tokyo', or just a city like 'Tokyo' / 'new york'."""
    key = name.strip().lower().replace("_", " ")
    if key in ALIASES:
        return ALIASES[key]
    for zone in available_timezones():
        if zone.lower() == name.strip().lower() or zone.rsplit("/", 1)[-1].lower().replace("_", " ") == key:
            return zone
    return name.strip()


def get_time(timezone: str = "") -> str:
    """Current date and time, locally or in an IANA timezone like 'Asia/Tokyo'."""
    try:
        now = datetime.now(ZoneInfo(_resolve_zone(timezone))) if timezone else datetime.now().astimezone()
    except ZoneInfoNotFoundError:
        return f"ERROR: Unknown place '{timezone}'. Try a city name like 'Tokyo' or a zone like 'Europe/London'."
    return now.strftime("%A %d %B %Y, %H:%M %Z")


def _t(name, desc, props, required=None):
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": required or []}}}


TOOLS = [
    _t("get_weather", "Real current weather and 3-day forecast. Leave city EMPTY to use the user's home city; only set it if the user names a different place.", {"city": {"type": "string", "description": "Only if the user names a place"}}),
    _t("get_time", "The real current date and time, optionally in another timezone.", {"timezone": {"type": "string"}}),
]
FUNCTIONS = {"get_weather": get_weather, "get_time": get_time}
