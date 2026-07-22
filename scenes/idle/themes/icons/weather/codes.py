CODE_MAPPINGS = {
    1000: ["sun", "moon", "rays", "moon_rays", 0],  # Sunny
    1003: ["cloud_sun", "cloud_moon", "rays", "moon_rays", 1],  # Partly cloudy
    1006: ["cloud", "cloud_moon", "", "", 0],  # Cloudy
    1009: ["cloud_dark", "cloud_dark", "", "", 0],  # Overcast
    1012: ["", "", "dusty", "dusty", 0],  # Haze
    1015: ["", "", "dusty", "dusty", 0],  # Dust haze
    1018: ["", "", "dusty", "dusty", 1],  # Blowing dust
    1021: ["", "", "dusty", "dusty", 2],  # Dust storm
    1024: ["", "", "dusty", "dusty", 2],  # Sandstorm
    1027: ["", "", "dusty", "dusty", 2],  # Severe sandstorm
    1030: ["", "", "mist", "mist", 0],  # Mist
    1033: ["", "", "mist", "mist", 1],  # Smoke
    1036: ["", "", "mist", "mist", 1],  # Smoky haze
    1039: ["", "", "mist", "mist", 1],  # Smog
    1042: ["", "", "mist", "mist", 2],  # Severe smog
    1045: ["", "", "dusty", "dusty", 2],  # Saharan dust
    1048: ["", "", "dusty", "dusty", 2],  # Dust
    1063: ["cloud", "cloud_moon", "rain", "rain", 0],  # Patchy rain possible
    1066: ["cloud", "cloud_moon", "snow", "snow", 0],  # Patchy snow possible
    1069: ["cloud", "cloud_moon", "sleet", "sleet", 1],  # Patchy sleet possible
    1072: [
        "cloud",
        "cloud_moon",
        "rain",
        "rain",
        0,
    ],  # Patchy freezing drizzle possible
    1087: [
        "cloud",
        "cloud_moon",
        "thunder",
        "thunder",
        0,
    ],  # Thundery outbreaks possible
    1114: ["cloud", "cloud_moon", "blowing_snow", "blowing_snow", 1],  # Blowing snow
    1117: ["cloud_dark", "cloud_dark", "snow", "snow", 2],  # Blizzard
    1135: ["", "", "fog", "fog", 1],  # Fog
    1147: ["", "", "fog", "fog", 1],  # Freezing fog
    1150: ["cloud", "cloud_moon", "rain", "rain", 0],  # Patchy light drizzle
    1153: ["cloud", "cloud_moon", "rain", "rain", 0],  # Light drizzle
    1168: ["cloud", "cloud_dark", "rain", "rain", 1],  # Freezing drizzle
    1171: ["cloud_dark", "cloud_dark", "rain", "rain", 2],  # Heavy freezing drizzle
    1180: ["cloud", "cloud_moon", "rain", "rain", 0],  # Patchy light rain
    1183: ["cloud", "cloud_moon", "rain", "rain", 0],  # Light rain
    1186: ["cloud", "cloud_dark", "rain", "rain", 1],  # Moderate rain at times
    1189: ["cloud", "cloud_dark", "rain", "rain", 1],  # Moderate rain
    1192: ["cloud", "cloud_dark", "rain", "rain", 2],  # Heavy rain at times
    1195: ["cloud_dark", "cloud_dark", "rain", "rain", 2],  # Heavy rain
    1198: ["cloud", "cloud_moon", "rain", "rain", 0],  # Light freezing rain
    1201: [
        "cloud_dark",
        "cloud_dark",
        "rain",
        "rain",
        2,
    ],  # Moderate or heavy freezing rain
    1204: ["cloud", "cloud_moon", "sleet", "sleet", 0],  # Light sleet
    1207: ["cloud_dark", "cloud_dark", "sleet", "sleet", 2],  # Moderate or heavy sleet
    1210: ["cloud", "cloud_moon", "snow", "snow", 0],  # Patchy light snow
    1213: ["cloud", "cloud_moon", "snow", "snow", 0],  # Light snow
    1216: ["cloud", "cloud_dark", "snow", "snow", 1],  # Patchy moderate snow
    1219: ["cloud", "cloud_dark", "snow", "snow", 1],  # Moderate snow
    1222: ["cloud", "cloud_dark", "snow", "snow", 2],  # Patchy heavy snow
    1225: ["cloud_dark", "cloud_dark", "snow", "snow", 2],  # Heavy snow
    1237: ["cloud", "cloud_dark", "snow", "snow", 1],  # Ice pellets
    1240: ["cloud", "cloud_moon", "rain", "rain", 0],  # Light rain shower
    1243: ["cloud", "cloud_dark", "rain", "rain", 2],  # Moderate or heavy rain shower
    1246: ["cloud_dark", "cloud_dark", "rain", "rain", 2],  # Torrential rain shower
    1249: ["cloud", "cloud_moon", "sleet", "sleet", 0],  # Light sleet showers
    1252: [
        "cloud_dark",
        "cloud_dark",
        "sleet",
        "sleet",
        2,
    ],  # Moderate or heavy sleet showers
    1255: ["cloud", "cloud_moon", "snow", "snow", 0],  # Light snow showers
    1258: [
        "cloud_dark",
        "cloud_dark",
        "snow",
        "snow",
        2,
    ],  # Moderate or heavy snow showers
    1261: ["cloud", "cloud_moon", "snow", "snow", 0],  # Light showers of ice pellets
    1264: [
        "cloud_dark",
        "cloud_dark",
        "snow",
        "snow",
        2,
    ],  # Moderate or heavy showers of ice pellets
    1273: [
        "cloud_sun",
        "cloud_moon",
        "thunder_rain",
        "thunder_rain",
        0,
    ],  # Patchy light rain with thunder
    1276: [
        "cloud_dark",
        "cloud_dark",
        "thunder_rain",
        "thunder_rain",
        2,
    ],  # Moderate or heavy rain with thunder
    1279: [
        "snow_cloud",
        "snow_cloud",
        "thunder_snow",
        "thunder_snow",
        1,
    ],  # Patchy light snow with thunder
    1282: [
        "snow_cloud",
        "snow_cloud",
        "thunder_snow",
        "thunder_snow",
        2,
    ],  # Moderate or heavy snow with thunder
}


def code_to_icon(code: int, night: bool):
    """Return (icon_name, animation_name) for a condition code.

    ``icon_name`` or ``animation_name`` may be ``None``.
    """
    row = CODE_MAPPINGS.get(code)

    if not row:
        return None, None

    icon = row[1] if night else row[0]
    animation = row[3] if night else row[2]
    return icon, animation


def code_to_weather(code: int, night: bool):
    """Return (icon_name, animation_name, intensity) for a condition code.

    ``icon_name`` or ``animation_name`` may be ``None``.
    ``intensity`` is 0 (light), 1 (medium), or 2 (heavy).
    Returns ``(None, None, 0)`` for unknown codes.
    """
    row = CODE_MAPPINGS.get(code)

    if not row:
        return None, None, 0

    icon = row[1] if night else row[0]
    animation = row[3] if night else row[2]
    intensity = row[4]
    return icon, animation, intensity
