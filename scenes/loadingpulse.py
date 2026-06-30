"""
LoadingPulseIndicator — top-right pixel pulses while overhead is fetching.

Replaces the former LoadingPulseScene mixin.  Call tick(frame) once per
frame after the active scene has drawn.
"""

from setup import colours

BLINKER_POSITION = (63, 0)
BLINKER_STEPS = 10
BLINKER_COLOUR = colours.WHITE


class LoadingPulseIndicator:
    def __init__(self, canvas, overhead):
        self._canvas = canvas
        self._overhead = overhead
        self._count = 0

    def tick(self, frame: int) -> None:
        # Run every 2 frames (matches original @KeyFrame.add(2))
        if frame % 2:
            return

        if self._overhead.processing:
            brightness = (1 - (self._count / BLINKER_STEPS)) / 2
            brightness = max(0.0, min(1.0, brightness))
            v = int(brightness * BLINKER_COLOUR.red)  # WHITE is (255,255,255)
            self._canvas.SetPixel(BLINKER_POSITION[0], BLINKER_POSITION[1], v, v, v)
            if self._count >= BLINKER_STEPS - 1:
                self._count = 0
            else:
                self._count += 1
        else:
            self._canvas.SetPixel(BLINKER_POSITION[0], BLINKER_POSITION[1], 0, 0, 0)
            self._count = 0
