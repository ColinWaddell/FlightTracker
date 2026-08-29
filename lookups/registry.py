"""
Provider registry.

A single, hand-maintained catalogue of every known lookup provider: what
it is called, which capabilities it implements, how to describe and
validate its settings, and how to construct its capability adapters.

The registry is deliberately *manual* - adding a provider means adding an
entry here plus its subpackage under :mod:`lookups.providers`.  Unknown
provider ids in configuration are rejected (with a warning) rather than
silently kept, so typos can't create providers that silently never run.

Import graph note: this module is imported by ``setup.configuration`` at
boot.  It must only import provider *config descriptors* and lazy
constructors - never the heavy API clients - so startup stays cheap.
Capability modules import their own heavy dependencies (FlightRadarAPI,
requests sessions) inside their factories below, which run only when a
provider is actually used.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from lookups.config import ProviderConfig

# ---------------------------------------------------------------------------
# Provider specification
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProviderSpec:
    """Catalogue entry for one lookup provider."""

    id: str
    name: str
    description: str
    # Capability ids implemented by this provider.
    capabilities: frozenset
    config: ProviderConfig
    # Optional factories: capability id -> callable(settings) -> adapter.
    # Absent factories mean "capability implemented but not provided here"
    # and are never consulted.
    flight_factory: Callable[[dict], object] | None = None
    route_factory: Callable[[dict], object] | None = None
    aircraft_factory: Callable[[dict], object] | None = None
    # Optional per-provider startup probes (status-agnostic reachability).
    startup_check: Callable[[], bool] | None = None
    # Human-readable notes surfaced in the web UI (e.g. "no API key
    # required"), separate from the long description.
    notes: tuple = field(default=())

    def implements(self, capability: str) -> bool:
        return capability in self.capabilities

    def factory_for(self, capability: str):
        return {
            "flights": self.flight_factory,
            "routes": self.route_factory,
            "aircraft": self.aircraft_factory,
        }.get(capability)


# ---------------------------------------------------------------------------
# Lazy capability factories
#
# Each factory imports its module on first call so the registry itself
# stays import-light.  Settings dicts come from the configuration store.
# ---------------------------------------------------------------------------


def _fr24_flights(settings):
    from lookups.providers.fr24.flights import FlightProvider

    return FlightProvider(settings)


def _fr24_routes(settings):
    from lookups.providers.fr24.routes import RouteProvider

    return RouteProvider(settings)


def _fr24_aircraft(settings):
    from lookups.providers.fr24.aircraft import AircraftProvider

    return AircraftProvider(settings)


def _fr24_startup_check():
    from lookups.providers.fr24.flights import startup_check

    return startup_check()


def _opensky_flights(settings):
    from lookups.providers.opensky.flights import FlightProvider

    return FlightProvider(settings)


def _opensky_startup_check():
    from lookups.providers.opensky.flights import startup_check

    return startup_check()


def _tar1090_flights(settings):
    from lookups.providers.tar1090.flights import FlightProvider

    return FlightProvider(settings)


def _tar1090_startup_check():
    from lookups.providers.tar1090.flights import startup_check
    from setup.configuration import Config

    return startup_check(Config.instance().provider_settings("tar1090").get("url", ""))


def _hexdb_routes(settings):
    from lookups.providers.hexdb.routes import RouteProvider

    return RouteProvider(settings)


def _hexdb_aircraft(settings):
    from lookups.providers.hexdb.aircraft import AircraftProvider

    return AircraftProvider(settings)


def _adsbdb_routes(settings):
    from lookups.providers.adsbdb.routes import RouteProvider

    return RouteProvider(settings)


def _adsbdb_aircraft(settings):
    from lookups.providers.adsbdb.aircraft import AircraftProvider

    return AircraftProvider(settings)


def _aerodatabox_routes(settings):
    from lookups.providers.aerodatabox.routes import RouteProvider

    return RouteProvider(settings)


def _aerodatabox_aircraft(settings):
    from lookups.providers.aerodatabox.aircraft import AircraftProvider

    return AircraftProvider(settings)


# ---------------------------------------------------------------------------
# The catalogue
# ---------------------------------------------------------------------------


def _spec(pid, config_module, capabilities, **kwargs) -> ProviderSpec:
    """Build a ProviderSpec, importing its descriptor module lazily.

    Importing each config module at catalog-build time would drag every
    provider package into boot; the descriptors are tiny, though, and the
    config store needs the full schemas at validation time anyway - so
    they *are* imported eagerly, just kept dependency-free.
    """
    import importlib

    mod = importlib.import_module(config_module)
    descriptor: ProviderConfig = mod.PROVIDER
    return ProviderSpec(
        id=pid,
        name=descriptor.name,
        description=descriptor.description,
        capabilities=frozenset(capabilities),
        config=descriptor,
        **kwargs,
    )


PROVIDERS: dict[str, ProviderSpec] = {
    spec.id: spec
    for spec in (
        _spec(
            "fr24",
            "lookups.providers.fr24.config",
            ("flights", "routes", "aircraft"),
            flight_factory=_fr24_flights,
            route_factory=_fr24_routes,
            aircraft_factory=_fr24_aircraft,
            startup_check=_fr24_startup_check,
        ),
        _spec(
            "opensky",
            "lookups.providers.opensky.config",
            ("flights",),
            flight_factory=_opensky_flights,
            startup_check=_opensky_startup_check,
        ),
        _spec(
            "tar1090",
            "lookups.providers.tar1090.config",
            ("flights",),
            flight_factory=_tar1090_flights,
            startup_check=_tar1090_startup_check,
        ),
        _spec(
            "hexdb",
            "lookups.providers.hexdb.config",
            ("routes", "aircraft"),
            route_factory=_hexdb_routes,
            aircraft_factory=_hexdb_aircraft,
        ),
        _spec(
            "adsbdb",
            "lookups.providers.adsbdb.config",
            ("routes", "aircraft"),
            route_factory=_adsbdb_routes,
            aircraft_factory=_adsbdb_aircraft,
        ),
        _spec(
            "aerodatabox",
            "lookups.providers.aerodatabox.config",
            ("routes", "aircraft"),
            route_factory=_aerodatabox_routes,
            aircraft_factory=_aerodatabox_aircraft,
        ),
    )
}

# Legacy capability labels used by the configuration schema.
CAPABILITY_FLIGHTS = "flights"
CAPABILITY_ROUTES = "routes"
CAPABILITY_AIRCRAFT = "aircraft"


# ---------------------------------------------------------------------------
# Provider list helpers
# ---------------------------------------------------------------------------


def normalise_provider_list(
    entries, capability: str
) -> tuple[list[dict], list[str]]:
    """Validate/sanitize one persisted provider list.

    *entries* is the raw value stored under ``flight_providers`` /
    ``route_providers``: a list of ``{"provider": id, "enabled": bool}``.

    Returns ``(clean_entries, warnings)``:

    - Unknown provider ids are dropped with a warning.
    - Providers lacking *capability* are dropped with a warning.
    - Missing/invalid ``enabled`` values coerce to False.
    - Duplicates keep their first occurrence only.
    """
    warnings: list[str] = []
    clean: list[dict] = []
    seen: set[str] = set()

    if not isinstance(entries, list):
        if entries not in (None, {}, ()):
            warnings.append(
                f"{capability} providers list must be a list; got "
                f"{type(entries).__name__}"
            )
        return [], warnings

    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("provider"):
            warnings.append(f"ignored malformed {capability} provider entry")
            continue
        pid = str(entry.get("provider", "")).strip()
        spec = PROVIDERS.get(pid)
        if spec is None:
            warnings.append(f"unknown provider {pid!r} dropped from {capability} list")
            continue
        if capability not in spec.capabilities:
            warnings.append(
                f"provider {pid!r} does not support {capability}; dropped"
            )
            continue
        if pid in seen:
            continue
        enabled = entry.get("enabled", False)
        if not isinstance(enabled, bool):
            warnings.append(
                f"provider {pid!r} enabled={enabled!r} is not a bool; treating as False"
            )
            enabled = bool(enabled)
        seen.add(pid)
        clean.append({"provider": pid, "enabled": enabled})

    return clean, warnings


def specs_for_capability(capability: str) -> list[ProviderSpec]:
    """All known provider specs that implement *capability*, catalogue order."""
    return [s for s in PROVIDERS.values() if capability in s.capabilities]


def provider_spec(pid: str) -> ProviderSpec | None:
    return PROVIDERS.get(pid)


def provider_settings_key(pid: str) -> str:
    """Config key holding *pid*'s settings subtree."""
    return f"providers.{pid}"
