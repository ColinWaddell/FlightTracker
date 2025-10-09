from gpiozero import LED
from utilities.animator import Animator
from setup import frames
from time import sleep
import sys

# Attempt to load config data
try:
    from config import LOADING_LED_GPIO_PIN

except (ModuleNotFoundError, NameError, ImportError):
    # If there's no config data
    LOADING_LED_GPIO_PIN = 25

BLINKER_STEPS = 4

class LoadingLEDScene(object):
    def __init__(self):
        self.gpio_setup_complete = False
        self.gpio_setup()
        super().__init__()

    def gpio_setup(self):
        try:
            self.led = LED(LOADING_LED_GPIO_PIN)
            self.led.on()
            self.gpio_setup_complete = True
        except:
            print("Error initializing GPIO", file=sys.stderr)
            self.gpio_setup_complete = False

    @Animator.KeyFrame.add(4)
    def loading_led(self, count):
        reset_count = True

        if not self.gpio_setup_complete:
            self.gpio_setup()

        if self.overhead.processing:
            if self.gpio_setup_complete:
                if count % 2:
                    self.led.on()
                else:
                    self.led.off()
        else:
            # Not processing, leave LED on
            if self.gpio_setup_complete:
                self.led.on()