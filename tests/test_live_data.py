from utilities.flight import Flight
from web.app import (
    _build_flight_rows,
    _build_forecast_rows,
    _build_weather_current_rows,
    _format_last_updated_value,
)


def test_get_live_data_overhead_uses_cached_instance_without_refresh(monkeypatch):
    from web.app import _get_live_data_overhead

    class DummyOverhead:
        def __init__(self):
            self.data = []

        def refresh(self):
            raise AssertionError("refresh should not be called")

    overhead = DummyOverhead()

    monkeypatch.setattr("display.get_overhead_instance", lambda: overhead)
    monkeypatch.setattr("web.app._select_overhead_class", lambda: (None, "dummy"))

    returned_overhead, data_source_name = _get_live_data_overhead()

    assert returned_overhead is overhead
    assert data_source_name == "dummy"


def test_build_weather_current_rows_flattens_nested_astro_and_omits_lists():
    weather_data = {
        "temp_c": 12.5,
        "description": "Cloudy",
        "hourly": [{"temp_c": 13.0}],
        "astro": {"sunrise": "06:00 AM", "moon_phase": "Waxing Crescent"},
    }

    rows = _build_weather_current_rows(weather_data)

    assert any(row["key"] == "temp_c" and row["value"] == "12.5" for row in rows)
    assert any(
        row["key"] == "astro.sunrise" and row["value"] == "06:00 AM" for row in rows
    )
    assert not any(row["key"] == "hourly" for row in rows)


def test_build_forecast_rows_collects_columns_from_all_days():
    rows, columns = _build_forecast_rows(
        [
            {"maxtemp_c": 20.0, "mintemp_c": 10.0},
            {"maxtemp_c": 22.0, "condition_code": 100},
        ]
    )

    assert columns == ["condition_code", "maxtemp_c", "mintemp_c"]
    assert rows[0]["maxtemp_c"] == "20.0"
    assert rows[1]["condition_code"] == "100"


def test_build_flight_rows_uses_flight_fields():
    flights = [Flight(callsign="ABC123", altitude=1200, plane="A320")]

    rows, columns = _build_flight_rows(flights)

    assert columns[0] == "callsign"
    assert rows[0]["callsign"] == "ABC123"
    assert rows[0]["altitude"] == "1200"


def test_format_last_updated_value_formats_timestamp():
    assert _format_last_updated_value(1720000000) == "2024-07-03 10:46:40"
    assert _format_last_updated_value(None) == ""
