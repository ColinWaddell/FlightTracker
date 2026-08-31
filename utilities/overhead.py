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
        # Outcome of the last fetch attempt - dict or None (status page).
        self.last_fetch = None

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
        from scenes.flight.lookups import cache, enrichment, flights
        from scenes.flight.lookups.results import FlightQuery
        from setup.configuration import Config

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

            # Remember this attempt for the status page regardless of how
            # the poll turns out below.
            self._record_fetch(outcome)

            if not outcome.ok:
                # Every enabled flight provider is unavailable - surface the
                # error state (scene logs it, falls back to the idle screen).
                self._set_error(LookupUnavailableError(outcome.errors))
                return

            for observation in outcome.observations:
                try:
                    data.append(self._to_flight(observation, enrichment))
                except (KeyError, AttributeError, TypeError):
                    continue

        except Exception as e:
            # Broad catch - providers raise a zoo of transport exceptions.
            logger.warning("Flight fetch failed: %s: %s", type(e).__name__, e)
            self._record_failure(e)
            self._set_error(e)
        else:
            with self.lock:
                self.data_store = data
                self.new_data_store = True
                self.error_store = None
                self.last_updated = time.time()
            logger.debug("Fetch complete - %d flight(s) tracked", len(data))

        finally:
            self._finish_cycle(cache)

    def _to_flight(self, observation, enrichment):
        """Enrich one live observation into a display Flight."""
        from utilities.flight import Flight

        route = enrichment.enrich(observation)

        # A local receiver's own aircraft-type database (or the feed's free
        # model text) outranks the lookup pipelines.
        plane = observation.plane or route.plane

        return Flight.from_route(
            route,
            plane=plane,
            callsign=_iata_callsign(observation),
            icao_callsign=observation.callsign,
            altitude=observation.altitude_ft or 0,
            ground_speed=int(observation.ground_speed_kt or 0),
            heading=int(observation.heading_deg or 0),
            vertical_speed=int(observation.vertical_speed_fpm or 0),
        )

    def _record_fetch(self, outcome):
        """Keep the last fetch attempt's outcome for the status page."""
        with self.lock:
            self.last_fetch = {
                "at": time.time(),
                "ok": outcome.ok,
                "provider_id": outcome.provider_id,
                "source_name": outcome.source_name,
                "errors": list(outcome.errors),
            }

    def _record_failure(self, error):
        """Record an out-of-band failure (crash between fetch and render)."""
        with self.lock:
            self.last_fetch = {
                "at": time.time(),
                "ok": False,
                "provider_id": "",
                "source_name": "",
                "errors": [str(error)],
            }

    def _set_error(self, error):
        with self.lock:
            self.data_store = []
            self.new_data_store = False
            self.error_store = error
        logger.warning("Flight fetch failed: %s", error)

    def _finish_cycle(self, cache):
        """Release the processing flag and flush the lookup cache.

        The cache is flushed once per poll cycle rather than on every
        individual put() to reduce SD-card writes on a Raspberry Pi.
        The usage tally's debounced flush rides the same cycle.
        """
        with self.lock:
            self.processing_store = False
        self.done.set()
        cache.flush()
        from scenes.flight.lookups import usage as _usage  # light import, same pattern as fetch

        _usage.flush_if_due()

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
