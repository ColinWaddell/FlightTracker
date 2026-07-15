WEATHER_CODE_TO_ICON = {
    "1000": {"day": "clear_day.png", "night": "clear_night.png"},
    "1003": {"day": "partly_cloudy_day.png", "night": "partly_cloudy_night.png"},
    "1006": {"day": "cloudy.png", "night": "cloudy.png"},
    "1009": {"day": "cloudy.png", "night": "cloudy.png"},
    "1012": {"day": "haze.png", "night": "haze.png"},
    "1015": {"day": "haze.png", "night": "haze.png"},
    "1018": {"day": "haze.png", "night": "haze.png"},
    "1021": {"day": "haze.png", "night": "haze.png"},
    "1024": {"day": "haze.png", "night": "haze.png"},
    "1027": {"day": "haze.png", "night": "haze.png"},
    "1030": {"day": "fog.png", "night": "fog.png"},
    "1033": {"day": "haze.png", "night": "haze.png"},
    "1036": {"day": "haze.png", "night": "haze.png"},
    "1039": {"day": "haze.png", "night": "haze.png"},
    "1042": {"day": "haze.png", "night": "haze.png"},
    "1045": {"day": "haze.png", "night": "haze.png"},
    "1048": {"day": "haze.png", "night": "haze.png"},
    "1063": {"day": "rain_1.png", "night": "rain_1.png"},
    "1066": {"day": "snow_2.png", "night": "snow_2.png"},
    "1069": {"day": "sleet.png", "night": "sleet.png"},
    "1072": {"day": "sleet.png", "night": "sleet.png"},
    "1087": {"day": "thunderstorm_1.png", "night": "thunderstorm_1.png"},
    "1114": {"day": "snow_3.png", "night": "snow_3.png"},
    "1117": {"day": "snow_3.png", "night": "snow_3.png"},
    "1135": {"day": "fog.png", "night": "fog.png"},
    "1147": {"day": "fog_2.png", "night": "fog_2.png"},
    "1150": {"day": "rain_1.png", "night": "rain_1.png"},
    "1153": {"day": "rain_1.png", "night": "rain_1.png"},
    "1168": {"day": "sleet.png", "night": "sleet.png"},
    "1171": {"day": "sleet_3.png", "night": "sleet_3.png"},
    "1180": {"day": "rain_1.png", "night": "rain_1.png"},
    "1183": {"day": "rain_1.png", "night": "rain_1.png"},
    "1186": {"day": "rain_2.png", "night": "rain_2.png"},
    "1189": {"day": "rain_2.png", "night": "rain_2.png"},
    "1192": {"day": "rain_3.png", "night": "rain_3.png"},
    "1195": {"day": "rain_3.png", "night": "rain_3.png"},
    "1198": {"day": "sleet.png", "night": "sleet.png"},
    "1201": {"day": "sleet_3.png", "night": "sleet_3.png"},
    "1204": {"day": "sleet.png", "night": "sleet.png"},
    "1207": {"day": "sleet_3.png", "night": "sleet_3.png"},
    "1210": {"day": "snow_2.png", "night": "snow_2.png"},
    "1213": {"day": "snow_2.png", "night": "snow_2.png"},
    "1216": {"day": "snow.png", "night": "snow.png"},
    "1219": {"day": "snow.png", "night": "snow.png"},
    "1222": {"day": "snow_3.png", "night": "snow_3.png"},
    "1225": {"day": "snow_3.png", "night": "snow_3.png"},
    "1237": {"day": "hail.png", "night": "hail.png"},
    "1240": {"day": "rain_1.png", "night": "rain_1.png"},
    "1243": {"day": "rain_2.png", "night": "rain_2.png"},
    "1246": {"day": "rain_3.png", "night": "rain_3.png"},
    "1249": {"day": "sleet.png", "night": "sleet.png"},
    "1252": {"day": "sleet_3.png", "night": "sleet_3.png"},
    "1255": {"day": "snow_2.png", "night": "snow_2.png"},
    "1258": {"day": "snow_3.png", "night": "snow_3.png"},
    "1261": {"day": "hail.png", "night": "hail.png"},
    "1264": {"day": "hail.png", "night": "hail.png"},
    "1273": {"day": "thunderstorm_1.png", "night": "thunderstorm_1.png"},
    "1276": {"day": "thunderstorm.png", "night": "thunderstorm.png"},
    "1279": {"day": "thunderstorm_1.png", "night": "thunderstorm_1.png"},
    "1282": {"day": "thunderstorm.png", "night": "thunderstorm.png"},
}

# Fallback icon when a condition code is not in the mapping.
_FALLBACK_ICON = {"day": "cloudy.png", "night": "cloudy.png"}


def weather_icon(condition_code: int, is_day: bool) -> str:
    """Return the PNG filename for a WeatherAPI condition code.

    ``condition_code`` is an int (e.g. 1000 for clear sky).
    ``is_day`` selects the day or night variant.
    """
    entry = WEATHER_CODE_TO_ICON.get(str(condition_code), _FALLBACK_ICON)
    return entry["day"] if is_day else entry["night"]
