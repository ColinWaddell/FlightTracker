"""
LoadingLEDIndicator — external GPIO LED blinks while overhead is fetching.

Replaces the former LoadingLEDScene mixin.  Call tick(frame) once per
frame after the active scene has drawn.
"""

import sys

from setup.configuration import Config

try:
    import RPi.GPIO as GPIO

    _GPIO_AVAILABLE = True
except ImportError:
    _GPIO_AVAILABLE = False


class LoadingLEDIndicator:
    def __init__(self, canvas, overhead):
        # canvas is accepted for API symmetry with LoadingPulseIndicator but not used
        self._overhead = overhead
        self._setup_complete = False
        self._setup()

    def _setup(self) -> None:
        if not _GPIO_AVAILABLE:
            return
        try:
            pin = Config.instance().loading_led_gpio_pin
            if not pin:
                return
            GPIO.setwarnings(False)
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.HIGH)
            self._setup_complete = True
        except Exception:
            print("Error initializing GPIO", file=sys.stderr)

    def tick(self, frame: int) -> None:
        # Run every 4 frames (matches original @KeyFrame.add(4))
        if frame % 4:
            return

        if not self._setup_complete:
            self._setup()
        if not self._setup_complete:
            return

        pin = Config.instance().loading_led_gpio_pin
        if not pin:
            return

        if self._overhead.processing:
            count = (frame // 4) % 2
            GPIO.output(pin, GPIO.HIGH if count else GPIO.LOW)
        else:
            GPIO.output(pin, GPIO.HIGH)
