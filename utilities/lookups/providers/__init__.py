"""
Provider adapters for external lookup services.

Each subpackage is a self-contained provider exposing some subset of:

- ``flights.py``   - live position observations (``FlightProvider``)
- ``routes.py``    - callsign route lookups (``RouteProvider``)
- ``aircraft.py``  - mode-s aircraft lookups (``AircraftProvider``)
- ``config.py``    - a :class:`lookups.config.ProviderConfig` descriptor
                     named ``PROVIDER`` describing the provider's settings

Adapters are thin: they translate between the shared result types in
:mod:`lookups.results` and each service's API, handling auth, timeouts and
response parsing.  Fallback ordering, caching and quarantine are handled
by the lookup services in :mod:`lookups.flights`, :mod:`lookups.routes`
and :mod:`lookups.aircraft`.
"""
