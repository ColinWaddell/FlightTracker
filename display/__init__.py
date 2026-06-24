import sys

from setup import frames
from utilities.animator import Animator

try:
    from config import TAR1090_URL
    from utilities.overhead_tar1090 import Overhead
except (ModuleNotFoundError, NameError, ImportError):
    from utilities.overhead_fr24 import Overhead

from scenes.weather import WeatherScene
from scenes.flightdetails import FlightDetailsScene
from scenes.journey import JourneyScene
from scenes.loadingpulse import LoadingPulseScene
from scenes.loadingled import LoadingLEDScene
from scenes.clock import ClockScene
from scenes.planedetails import PlaneDetailsScene
from scenes.day import DayScene
from scenes.date import DateScene

from rgbmatrix import graphics
from rgbmatrix import RGBMatrix, RGBMatrixOptions


def callsigns_match(flights_a, flights_b):
    get_callsigns = lambda flights: [f["callsign"] for f in flights]
    callsigns_a = set(get_callsigns(flights_a))
    callsigns_b = set(get_callsigns(flights_b))

    return callsigns_a == callsigns_b


try:
    from config import (
        BRIGHTNESS,
        GPIO_SLOWDOWN,
        HAT_PWM_ENABLED,
    )
except (ModuleNotFoundError, NameError):
    BRIGHTNESS = 100
    GPIO_SLOWDOWN = 1
    HAT_PWM_ENABLED = True


try:
    from config import LOADING_LED_ENABLED
except (ModuleNotFoundError, NameError, ImportError):
    LOADING_LED_ENABLED = False


class Display(
    WeatherScene,
    FlightDetailsScene,
    JourneyScene,
    LoadingLEDScene if LOADING_LED_ENABLED else LoadingPulseScene,
    PlaneDetailsScene,
    ClockScene,
    DayScene,
    DateScene,
    Animator,
):
    def __init__(self):
        options = RGBMatrixOptions()
        options.hardware_mapping = (
            "adafruit-hat-pwm" if HAT_PWM_ENABLED else "adafruit-hat"
        )
        options.rows = 32
        options.cols = 64
        options.chain_length = 1
        options.parallel = 1
        options.row_address_type = 0
        options.multiplexing = 0
        options.pwm_bits = 11
        options.brightness = BRIGHTNESS
        options.pwm_lsb_nanoseconds = 130
        options.led_rgb_sequence = "RGB"
        options.pixel_mapper_config = ""
        options.show_refresh_rate = 0
        options.gpio_slowdown = GPIO_SLOWDOWN
        options.disable_hardware_pulsing = True
        options.drop_privileges = True

        self.matrix = RGBMatrix(options=options)

        self.canvas = self.matrix.CreateFrameCanvas()
        self.canvas.Clear()

        self._data_index = 0
        self._data = []

        self.overhead = Overhead()
        self.overhead.grab_data()

        super().__init__()

        self.delay = frames.PERIOD

    def draw_square(self, x0, y0, x1, y1, colour):
        for x in range(x0, x1):
            _ = graphics.DrawLine(self.canvas, x, y0, x, y1, colour)

    @Animator.KeyFrame.add(0)
    def clear_screen(self):
        self.canvas.Clear()

    @Animator.KeyFrame.add(frames.PER_SECOND * 5)
    def check_for_loaded_data(self, count):
        if self.overhead.error is not None:
            print(f"overhead data grab failed: {self.overhead.error}")
            return

        if self.overhead.new_data:
            there_is_data = len(self._data) > 0 or not self.overhead.data_is_empty

            new_data = self.overhead.data

            data_is_different = not callsigns_match(self._data, new_data)

            if data_is_different:
                self._data_index = 0
                self._data_all_looped = False
                self._data = new_data

            reset_required = there_is_data and data_is_different

            if reset_required:
                self.reset_scene()

    @Animator.KeyFrame.add(1)
    def sync(self, count):
        _ = self.matrix.SwapOnVSync(self.canvas)

    @Animator.KeyFrame.add(frames.PER_SECOND * 30)
    def grab_new_data(self, count):
        if (
            not self.overhead.processing
            and not self.overhead.new_data
            and (self._data_all_looped or len(self._data) <= 1)
        ):
            self.overhead.grab_data()

    def run(self):
        try:
            print("Press CTRL-C to stop")
            self.play()

        except KeyboardInterrupt:
            print("Exiting\n")

            if self.overhead.processing:
                self.overhead.wait(timeout=15)

            sys.exit(0)
