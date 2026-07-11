import sys
from time import perf_counter, sleep

# ---------------------------------------------------------------------------
# Lazy class construction - defers panel, font, and overhead imports
# until first access so the boot screen and web interface start cheaply.
# ---------------------------------------------------------------------------

DisplayClass = None


def build_display_class():
    import logging

    from display.panel_factory import get_panel
    from scenes.flight.flight_scene import FlightScene
    from scenes.idle.idle_scene import IdleScene
    from scenes.satellite.satellite_scene import SatelliteScene
    from setup import frames
    from setup.configuration import Config
    from setup.themes import theme_set
    from utilities.scene_manager import SceneManager
    from utilities.tle_manager import TLEManager

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
                # Came from splash screen - reuse the already-initialised panel
                self.panel = get_panel()
                self.canvas = canvas
                self.from_splash = True
            else:
                self.panel = get_panel()
                self.panel.init_matrix(
                    width=64,
                    height=32,
                    brightness=cfg.brightness_percent,
                    rotation=180 if cfg.screen_rotate else 0,
                    hat_pwm=cfg.hat_pwm_enabled,
                    gpio_slowdown=cfg.gpio_slowdown,
                )
                self.canvas = self.panel.create_canvas()
                self.panel.clear(self.canvas)
                self.from_splash = False

            overhead = Overhead()

            self.scene_manager = SceneManager()
            self.scene_manager.register(IdleScene(self.canvas, self.panel))
            self.scene_manager.register(
                FlightScene(self.canvas, self.panel, overhead, REFRESH_INTERVAL)
            )
            logger.info("Registered scenes: Idle, Flight")

            if cfg.satellite_tracking_enabled:
                tle_manager = TLEManager()
                tle_manager.start()
                self.scene_manager.register(
                    SatelliteScene(self.canvas, self.panel, tle_manager)
                )
                logger.info(
                    "Satellite tracking enabled - registered Satellite scene "
                    "(NORAD ids: %s)",
                    cfg.satellite_norad_ids,
                )
            else:
                logger.info("Satellite tracking disabled")

            self.loading = IndicatorClass(self.canvas, self.panel, overhead)
            self.frames = frames
            self.frame_period = max(
                0.001, self.frames.PERIOD * cfg.display_speed_factor
            )
            self.brightness_update_interval = max(1, int(round(1 / self.frame_period)))

        def update_brightness(self):
            cfg = Config.instance()
            if cfg.is_in_brightness_schedule():
                self.panel.set_brightness(cfg.schedule_brightness_percent)
            else:
                self.panel.set_brightness(cfg.brightness_percent)

        def run(self):
            print("Press CTRL-C to stop")

            if self.from_splash:
                self.panel.clear(self.canvas)
                self.panel.swap(self.canvas)

            self.panel.clear(self.canvas)

            frame = 0
            try:
                while True:
                    start = perf_counter()

                    if not (frame % self.brightness_update_interval):
                        self.update_brightness()

                    self.scene_manager.kick()

                    self.loading.tick(frame)

                    self.panel.swap(self.canvas)

                    frame += 1

                    elapsed = perf_counter() - start
                    sleep_time = self.frame_period - elapsed
                    if sleep_time < 0.001:
                        sleep_time = 0.001
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
