"""
Overhead facade: the flight-scene data source.

One class replaces the three per-source overhead modules (fr24/osn/
tar1090).  It delegates live positions to :mod:`lookups.flights` and
per-aircraft enrichment to :mod:`lookups.enrichment`, then adapts the
results to the :class:`~utilities.flight.Flight` objects the flight scene
expects.  The threading contract is unchanged:

- ``grab_data()``    - start a background fetch (no-op while busy)
- ``refresh()``      - run a fetch synchronously
- ``wait(timeout)``  - block until the current fetch finishes
- properties         - ``new_data``/``processing``/``error``/``data``/
                       ``data_is_empty``/``last_updated``

Error state replaces the old per-source placeholder flights ("Check
tar1090 URL" etc.): when every flight provider is unavailable the scene
logs the error and falls back to the idle screen instead of displaying a
fake aircraft.
"""

from __future__ import annotations

import logging
import time
from threading import Event, Lock, Thread

logger = logging.getLogger(__name__)


def _iata_callsign(observation) -> str:
    """Display callsign honouring the configured IATA/ICAO format.

    ``obs.flight_number`` (the IATA flight number, when the feed supplies
    it) takes precedence; otherwise the bundled airline table converts the
    ICAO callsign, falling back to the ICAO callsign when unmapped.
    """
    from setup.configuration import Config

    icao_callsign = observation.callsign
    if Config.instance().callsign_format != "iata":
        return icao_callsign
    if observation.flight_number:
        return observation.flight_number
    from assets.airlines.convert import icao_flight_to_iata

    return icao_flight_to_iata(icao_callsign) or icao_callsign


class Overhead:
    """Flight data source facade - same contract the scene always had."""

    def __init__(self):
        self.lock = Lock()
        self.done = Event()

        self.thread = None
        self.data_store = []
        self.new_data_store = False
        self.processing_store = False
        self.error_store = None
        self.last_updated = None

    # ------------------------------------------------------------------
    # Scene contract (threaded fetch)
    # ------------------------------------------------------------------

    def grab_data(self):
        with self.lock:
            if self.processing_store:
                return False

            self.processing_store = True
            self.new_data_store = False
            self.error_store = None
            self.done.clear()
            self.thread = Thread(target=self.grab_data_impl, name="overhead-grabber")

        self.thread.start()
        return True

    def refresh(self):
        with self.lock:
            if self.processing_store:
                return False

            self.processing_store = True
            self.new_data_store = False
            self.error_store = None
            self.done.clear()

        self.grab_data_impl()
        return True

    def wait(self, timeout=None):
        finished = self.done.wait(timeout)
        if finished and self.thread is not None:
            self.thread.join()

        return finished

    # ------------------------------------------------------------------
    # Fetch implementation
    # ------------------------------------------------------------------

    def grab_data_impl(self):
        from lookups import cache, enrichment, flights
        from lookups.results import FlightQuery
        from setup.configuration import Config
        from utilities.flight import Flight

        cfg = Config.instance()
        data = []

        try:
            query = FlightQuery(
                zone=cfg.zone_home,
                home=cfg.location_home,
                min_altitude_m=cfg.flight_min_altitude,
                max_altitude_m=cfg.flight_max_altitude,
                max_results=cfg.max_flight_lookup,
            )

            outcome = flights.fetch_flights(query)

            if not outcome.ok:
                raise LookupUnavailableError(outcome.errors)

            for observation in outcome.observations:
                try:
                    route = enrichment.enrich(observation)

                    # A local receiver's own aircraft-type database (or the
                    # feed's free model text) outranks the lookup pipelines.
                    plane = observation.plane or route.plane

                    icao_callsign = observation.callsign
                    display_callsign = _iata_callsign(observation)

                    data.append(
                        Flight.from_route(
                            route,
                            plane=plane,
                            callsign=display_callsign,
                            icao_callsign=icao_callsign,
                            altitude=observation.altitude_ft or 0,
                            ground_speed=int(observation.ground_speed_kt or 0),
                            heading=int(observation.heading_deg or 0),
                            vertical_speed=int(observation.vertical_speed_fpm or 0),
                        )
                    )
                except (KeyError, AttributeError, TypeError):
                    continue

            with self.lock:
                self.data_store = data
                self.new_data_store = True
                self.error_store = None
                self.last_updated = time.time()
            logger.debug(
                "Fetch complete via %s - %d flight(s) tracked",
                outcome.provider_id,
                len(data),
            )

        except LookupUnavailableError as e:
            # All enabled flight providers unavailable - surface the error
            # state (scene logs it, falls back to the idle screen).
            logger.warning("Flight fetch failed: %s", e)
            with self.lock:
                self.data_store = []
                self.new_data_store = False
                self.error_store = e

        except Exception as e:
            # Broad catch - providers raise a zoo of transport exceptions.
            logger.warning("Flight fetch failed: %s: %s", type(e).__name__, e)
            with self.lock:
                self.data_store = []
                self.new_data_store = False
                self.error_store = e

        finally:
            with self.lock:
                self.processing_store = False
            self.done.set()
            # Flush the lookup cache once per poll cycle rather than on
            # every individual put() to reduce SD-card writes on a Pi.
            cache.flush()

    # ------------------------------------------------------------------
    # Properties (scene contract)
    # ------------------------------------------------------------------

    @property
    def new_data(self):
        with self.lock:
            return self.new_data_store

    @property
    def processing(self):
        with self.lock:
            return self.processing_store

    @property
    def error(self):
        with self.lock:
            return self.error_store

    @property
    def data(self):
        with self.lock:
            self.new_data_store = False
            return list(self.data_store)

    @property
    def data_is_empty(self):
        with self.lock:
            return len(self.data_store) == 0


class LookupUnavailableError(Exception):
    """Raised to move a FlightFetchOutcome's errors into the error state."""

    def __init__(self, errors):
        self.errors = list(errors or [])
        super().__init__("; ".join(self.errors) or "no flight data available")