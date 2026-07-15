WEATHER_CODE_TO_ICON = {
  "1000": { "day": "sunny_day.png", "night": "sunny_night.png" },
  "1003": { "day": "partly_cloudy_day.png", "night": "partly_cloudy_night.png" },
  "1006": { "day": "cloudy.png", "night": "cloudy.png" },
  "1009": { "day": "overcast.png", "night": "overcast.png" },
  "1012": { "day": "cloudy.png", "night": "cloudy.png" },
  "1015": { "day": "cloudy.png", "night": "cloudy.png" },
  "1018": { "day": "cloudy.png", "night": "cloudy.png" },
  "1021": { "day": "cloudy.png", "night": "cloudy.png" },
  "1024": { "day": "cloudy.png", "night": "cloudy.png" },
  "1027": { "day": "cloudy.png", "night": "cloudy.png" },
  "1030": { "day": "cloudy.png", "night": "cloudy.png" },
  "1033": { "day": "cloudy.png", "night": "cloudy.png" },
  "1036": { "day": "cloudy.png", "night": "cloudy.png" },
  "1039": { "day": "cloudy.png", "night": "cloudy.png" },
  "1042": { "day": "cloudy.png", "night": "cloudy.png" },
  "1045": { "day": "cloudy.png", "night": "cloudy.png" },
  "1048": { "day": "cloudy.png", "night": "cloudy.png" },
  "1063": { "day": "light_rain_day.png", "night": "light_rain.png" },
  "1066": { "day": "snow_day.png", "night": "snow_night.png" },
  "1069": { "day": "sleet.png", "night": "sleet.png" },
  "1072": { "day": "sleet.png", "night": "sleet.png" },
  "1087": { "day": "thunderstorm.png", "night": "thunderstorm.png" },
  "1114": { "day": "snow_day.png", "night": "snow_night.png" },
  "1117": { "day": "snow_day.png", "night": "snow_night.png" },
  "1135": { "day": "cloudy.png", "night": "cloudy.png" },
  "1147": { "day": "cloudy.png", "night": "cloudy.png" },
  "1150": { "day": "light_rain_day.png", "night": "light_rain.png" },
  "1153": { "day": "light_rain_day.png", "night": "light_rain.png" },
  "1168": { "day": "sleet.png", "night": "sleet.png" },
  "1171": { "day": "sleet.png", "night": "sleet.png" },
  "1180": { "day": "light_rain_day.png", "night": "light_rain.png" },
  "1183": { "day": "rain_day.png", "night": "rain_night.png" },
  "1186": { "day": "rain_day.png", "night": "rain_night.png" },
  "1189": { "day": "rain_day.png", "night": "rain_night.png" },
  "1192": { "day": "heavy_rain.png", "night": "heavy_rain.png" },
  "1195": { "day": "heavy_rain.png", "night": "heavy_rain.png" },
  "1198": { "day": "sleet.png", "night": "sleet.png" },
  "1201": { "day": "sleet.png", "night": "sleet.png" },
  "1204": { "day": "sleet.png", "night": "sleet.png" },
  "1207": { "day": "sleet.png", "night": "sleet.png" },
  "1210": { "day": "snow_day.png", "night": "snow_night.png" },
  "1213": { "day": "snow_day.png", "night": "snow_night.png" },
  "1216": { "day": "snow_day.png", "night": "snow_night.png" },
  "1219": { "day": "snow_day.png", "night": "snow_night.png" },
  "1222": { "day": "snow_day.png", "night": "snow_night.png" },
  "1225": { "day": "snow_day.png", "night": "snow_night.png" },
  "1237": { "day": "sleet.png", "night": "sleet.png" },
  "1240": { "day": "light_rain_day.png", "night": "light_rain.png" },
  "1243": { "day": "rain_day.png", "night": "rain_night.png" },
  "1246": { "day": "heavy_rain.png", "night": "heavy_rain.png" },
  "1249": { "day": "sleet.png", "night": "sleet.png" },
  "1252": { "day": "sleet.png", "night": "sleet.png" },
  "1255": { "day": "snow_day.png", "night": "snow_night.png" },
  "1258": { "day": "snow_day.png", "night": "snow_night.png" },
  "1261": { "day": "sleet.png", "night": "sleet.png" },
  "1264": { "day": "sleet.png", "night": "sleet.png" },
  "1273": { "day": "thunderstorm_rain.png", "night": "thunderstorm_rain.png" },
  "1276": { "day": "thunderstorm.png", "night": "thunderstorm.png" },
  "1279": { "day": "thunderstorm_rain.png", "night": "thunderstorm_rain.png" },
  "1282": { "day": "thunderstorm.png", "night": "thunderstorm.png" }
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