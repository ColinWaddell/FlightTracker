"""Tests for the conditions idle theme's wind arrow direction helper.

The conditions scene draws an arrow icon beside the wind speed.  The
``wind_arrow_mode`` setting picks which way it points:

- ``from``: toward the bearing the wind blows from (weather-vane style,
  the original behaviour - see issue #130 discussion);
- ``to``: toward the direction the wind is travelling (the reciprocal
  bearing).
"""

from scenes.idle.themes.conditions_idle_theme import (
    _CARDINAL_DIRECTIONS,
    ConditionsIdleTheme,
)


class TestWindArrowCardinal:
    """Unit tests for ConditionsIdleTheme._wind_arrow_cardinal()."""

    def test_from_mode_points_upwind(self):
        # A 140° wind blows from the SE - the arrow points SE (original
        # behaviour, unchanged).
        assert ConditionsIdleTheme._wind_arrow_cardinal(140.0, "from") == "SE"

    def test_to_mode_points_downwind(self):
        # A 140° wind travels toward 320° - the arrow points NW.
        assert ConditionsIdleTheme._wind_arrow_cardinal(140.0, "to") == "NW"

    def test_to_mode_wraps_bearing(self):
        # A 0° wind (from N) travels toward 180° (S)...
        assert ConditionsIdleTheme._wind_arrow_cardinal(0.0, "to") == "S"
        # ...and a 300° wind (from WNW) travels toward 120°, which lands
        # in the SE sector.
        assert ConditionsIdleTheme._wind_arrow_cardinal(300.0, "to") == "SE"

    def test_unknown_mode_falls_back_to_from(self):
        assert ConditionsIdleTheme._wind_arrow_cardinal(140.0, "bogus") == "SE"

    def test_boundary_rounds_half_up(self):
        # 22.5° sits on the N/NE boundary - floor(x / 45 + 0.5) puts it in
        # NE (not N) and its reciprocal in SW (not S).
        assert ConditionsIdleTheme._wind_arrow_cardinal(22.5, "from") == "NE"
        assert ConditionsIdleTheme._wind_arrow_cardinal(22.5, "to") == "SW"

    def test_modes_are_opposite_cardinals(self):
        # For every bearing the two modes must point in cardinals exactly
        # four sectors (180°) apart.
        for degrees in range(0, 360, 15):
            from_cardinal = ConditionsIdleTheme._wind_arrow_cardinal(
                float(degrees), "from"
            )
            to_cardinal = ConditionsIdleTheme._wind_arrow_cardinal(float(degrees), "to")
            index_from = _CARDINAL_DIRECTIONS.index(from_cardinal)
            index_to = _CARDINAL_DIRECTIONS.index(to_cardinal)
            assert (index_to - index_from) % 8 == 4, f"bearing {degrees}°"
