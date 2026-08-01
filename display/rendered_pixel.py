from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TypeAlias

from setup.colours import Colour

# A single sparse column:
#     y coordinate -> pixel colour
#
# Missing y coordinates are blank.
PixelColumn: TypeAlias = dict[int, Colour]


# Concrete output format produced by renderers.
#
# The list index is the x coordinate.
# Each item contains only the lit pixels in that column.
RenderedPixels: TypeAlias = list[PixelColumn]


# Read-only forms accepted by code which only consumes rendered pixels.
PixelColumnView: TypeAlias = Mapping[int, Colour]
RenderedPixelsView: TypeAlias = Sequence[PixelColumnView]


# Used later when describing changes to the physical display.
# None means blank the pixel.
PixelValue: TypeAlias = Colour | None


# A change to one physical pixel.
PixelUpdate: TypeAlias = tuple[int, int, PixelValue]
