import sys
from time import perf_counter, sleep

# ---------------------------------------------------------------------------
# Lazy class construction - defers rgbmatrix, font, and overhead imports
# until first access so the boot screen and web interface start cheaply.
# ---------------------------------------------------------------------------

DisplayClass = None


def build_display_class():
    from setup.configuration import Config
    from setup import frames
    from setup.themes import theme_set
    import logging

    from rgbmatrix import graphics, RGBMatrix, RGBMatrixOptions

    from utilities.scene_manager import SceneManager
    from utilities.tle_manager import TLEManager
    from scenes.idle.idle_scene import IdleScene
    from scenes.flight.flight_scene import FlightScene
    from scenes.satellite.satellite_scene import SatelliteScene

    cfg = Config.instance()
    theme_set(cfg.theme)
    logger = logging.getLogger("display")

    if cfg.use_tar1090:
        from utilities.overhead_tar1090 import Overhead

        REFRESH_INTERVAL = 10
        logger.info(
            "Data source: tar1090 (%s), refresh every %ds",
            cfg.tar1090_url or "<unset>",
            REFRESH_INTERVAL,
        )
    else:
        from utilities.overhead_fr24 import Overhead

        REFRESH_INTERVAL = 30
        logger.info("Data source: FlightRadar24, refresh every %ds", REFRESH_INTERVAL)

    if cfg.loading_led_enabled:
        from scenes.loadingled import LoadingLEDIndicator as IndicatorClass
    else:
        from scenes.loadingpulse import LoadingPulseIndicator as IndicatorClass

    class Display:
        def __init__(self, matrix=None, canvas=None):
            cfg = Config.instance()

            if matrix is not None:
                self.matrix = matrix
                self.canvas = canvas
                self.from_splash = True
            else:
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
                self.from_splash = False

            def draw_square(x0, y0, x1, y1, colour):
                for x in range(x0, x1):
                    graphics.DrawLine(self.canvas, x, y0, x, y1, colour)

            overhead = Overhead()

            self.scene_manager = SceneManager()
            self.scene_manager.register(IdleScene(self.canvas, draw_square))
            self.scene_manager.register(
                FlightScene(self.canvas, draw_square, overhead, REFRESH_INTERVAL)
            )
            logger.info("Registered scenes: Idle, Flight")

            if cfg.satellite_tracking_enabled:
                tle_manager = TLEManager()
                tle_manager.start()
                self.scene_manager.register(
                    SatelliteScene(self.canvas, draw_square, tle_manager)
                )
                logger.info(
                    "Satellite tracking enabled - registered Satellite scene "
                    "(NORAD ids: %s)",
                    cfg.satellite_norad_ids,
                )
            else:
                logger.info("Satellite tracking disabled")

            self.loading = IndicatorClass(self.canvas, overhead)
            self.frames = frames

        def update_brightness(self):
            cfg = Config.instance()
            if cfg.is_in_brightness_schedule():
                self.matrix.brightness = cfg.schedule_brightness_percent
            else:
                self.matrix.brightness = cfg.brightness_percent

        def run(self):
            print("Press CTRL-C to stop")

            if self.from_splash:
                self.canvas.Clear()
                self.matrix.SwapOnVSync(self.canvas)

            self.canvas.Clear()

            frame = 0
            try:
                while True:
                    start = perf_counter()

                    if not (frame % int(self.frames.PER_SECOND)):
                        self.update_brightness()

                    self.scene_manager.kick()

                    self.loading.tick(frame)

                    self.matrix.SwapOnVSync(self.canvas)

                    frame += 1

                    elapsed = perf_counter() - start
                    sleep_time = self.frames.PERIOD - elapsed
                    if sleep_time < 0.001:
                        sleep_time = 0.001
                    elif sleep_time > 0.05:
                        sleep_time = 0.05
                    sleep(sleep_time)

            except KeyboardInterrupt:
                print("Exiting\n")
                sys.exit(0)

    return Display


def get_display_class():
    global DisplayClass
    if DisplayClass is None:
        DisplayClass = build_display_class()
    return DisplayClass


def __getattr__(name):
    if name == "Display":
        return get_display_class()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
