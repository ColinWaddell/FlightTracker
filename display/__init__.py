import sys

from setup.configuration import Config
from setup import frames
from setup.themes import theme_set
from utilities.animator import Animator

from rgbmatrix import graphics
from rgbmatrix import RGBMatrix, RGBMatrixOptions

from scenes.weather import WeatherScene
from scenes.flightdetails import FlightDetailsScene
from scenes.journey import JourneyScene
from scenes.loadingpulse import LoadingPulseScene
from scenes.loadingled import LoadingLEDScene
from scenes.clock import ClockScene
from scenes.planedetails import PlaneDetailsScene
from scenes.day import DayScene
from scenes.date import DateScene


def callsigns_match(flights_a, flights_b):
    get_callsigns = lambda flights: [f["callsign"] for f in flights]
    return set(get_callsigns(flights_a)) == set(get_callsigns(flights_b))


_cfg = Config.instance()
theme_set(_cfg.theme)

if _cfg.use_tar1090:
    from utilities.overhead_tar1090 import Overhead
else:
    from utilities.overhead_fr24 import Overhead

_loading_scene = LoadingLEDScene if _cfg.loading_led_enabled else LoadingPulseScene


class Display(
    WeatherScene,
    FlightDetailsScene,
    JourneyScene,
    _loading_scene,
    PlaneDetailsScene,
    ClockScene,
    DayScene,
    DateScene,
    Animator,
):
    def __init__(self):
        cfg = Config.instance()

        options = RGBMatrixOptions()
        options.hardware_mapping = (
            "adafruit-hat-pwm" if cfg.hat_pwm_enabled else "adafruit-hat"
        )
        options.rows = 32
        options.cols = 64
        options.chain_length = 1
        options.parallel = 1
        options.row_address_type = 0
        options.multiplexing = 0
        options.pwm_bits = 11
        options.brightness = cfg.brightness_percent
        options.pwm_lsb_nanoseconds = 130
        options.led_rgb_sequence = "RGB"
        options.pixel_mapper_config = "Rotate:180" if cfg.screen_rotate else ""
        options.show_refresh_rate = 0
        options.gpio_slowdown = cfg.gpio_slowdown
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

            if there_is_data and data_is_different:
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
