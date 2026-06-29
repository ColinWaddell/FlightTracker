from utilities.animator import Animator
from setup import frames
from setup.configuration import Config
from time import sleep
import RPi.GPIO as GPIO
import sys

BLINKER_STEPS = 4


class LoadingLEDScene(object):
    def __init__(self):
        self.gpio_setup_complete = False
        self.gpio_setup()
        super().__init__()

    def gpio_setup(self):
        try:
            pin = Config.instance().loading_led_gpio_pin
            if not pin:
                self.gpio_setup_complete = False
                return
            GPIO.setwarnings(False)
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.HIGH)
            self.gpio_setup_complete = True
        except:
            print("Error initializing GPIO", file=sys.stderr)
            self.gpio_setup_complete = False

    @Animator.KeyFrame.add(4)
    def loading_led(self, count):
        reset_count = True

        if not self.gpio_setup_complete:
            self.gpio_setup()

        if not self.gpio_setup_complete:
            return

        pin = Config.instance().loading_led_gpio_pin
        if not pin:
            return

        if self.overhead.processing:
            GPIO.output(pin, GPIO.HIGH if count % 2 else GPIO.LOW)

        else:
            # Not processing, leave LED on
            GPIO.output(pin, GPIO.HIGH)
