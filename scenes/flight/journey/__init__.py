"""Journey label widgets for the flight scene.

Two label strategies, selected once at scene construction via
:func:`make_label` based on ``cfg.airport_display_style``:

* :class:`ShortCodeLabel` - static IATA codes + pixel arrow (style 0).
* :class:`FullNameLabel` - bounce-scrolled ``"IATA>name"`` lines (styles 1-4).

Both accept a ``text_x_origin`` (and the full-name label an
``available_width``) so the journey text can be shifted right to
accommodate the airline icon at (0, 0).
"""

from scenes.flight.journey.full_label import FullNameLabel
from scenes.flight.journey.make_label import make_label
from scenes.flight.journey.short_label import ShortCodeLabel

__all__ = ["FullNameLabel", "ShortCodeLabel", "make_label"]
