"""
Provider registry.

A single, hand-maintained catalogue of every known lookup provider: what
it is called, which capabilities it implements, how to describe and
validate its settings, and how to construct its capability adapters.

The registry is deliberately *manual* - adding a provider means adding an
entry here plus a subpackage under :mod:`lookups.providers`.  Unknown
provider ids in configuration are rejected (with a warning) rather than
silently kept, so typos can't create providers that silently never run.

Import graph note: this module is imported by ``setup.configuration`` at
boot.  Provider descriptors are imported eagerly here (they are small and
the config store needs their schemas anyway), but the heavy API clients
are imported lazily inside the factories below, which only run when a
provider is actually used.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

from lookups.config import ProviderConfig

logger = logging.getLogger(__name__)

# Capability ids shared by this registry and the provider descriptors.
FLIGHTS = "flights"
ROUTES = "routes"
AIRCRAFT = "aircraft"

# Config attribute that stores the priority list for each capability.
# Route and aircraft providers share one list: both capabilities resolve
# the same "where is it going / what is it" chain, ordered by the user.
_PRIORITY_LIST_ATTR = {
    "flights": "flight_providers",
    "routes": "route_providers",
    "aircraft": "route_providers",
}


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
    capabilities: frozenset[str]
    config: ProviderConfig
    # Capability factories: capability id -> callable(settings) -> adapter.
    factories: dict[str, Callable[[dict], object]]
    # Optional reachability probe for the startup screen.  Takes the
    # provider's validated settings and must be status-agnostic (a 4xx
    # response still counts as "reachable").
    startup_check: Callable[[dict], bool] | None = None
    notes: tuple = field(default=())

    def implements(self, capability: str) -> bool:
        return capability in self.capabilities

    def factory(self, capability: str) -> Callable[[dict], object] | None:
        return self.factories.get(capability)


# ---------------------------------------------------------------------------
# Lazy factories
#
# Provider modules import their heavy API clients at module level, so the
# factory imports the module on first use.  The registry itself only ever
# touches the lightweight config descriptors.
# ---------------------------------------------------------------------------


def _factory(module: str, class_name: str) -> Callable[[dict], object]:
    """Build a capability factory that imports its module on first use."""

    def factory(settings: dict):
        import importlib

        return getattr(importlib.import_module(module), class_name)(settings)

    return factory


def _startup_check(module: str) -> Callable[[dict], bool]:
    """Adapt a provider module's ``startup_check(settings)`` probe."""

    def check(settings: dict) -> bool:
        import importlib

        return bool(importlib.import_module(module).startup_check(settings))

    return check


# ---------------------------------------------------------------------------
# The catalogue
# ---------------------------------------------------------------------------


def _descriptor(pid: str) -> ProviderConfig:
    import importlib

    return importlib.import_module(f"lookups.providers.{pid}.config").PROVIDER


def _spec(
    pid: str,
    name: str,
    description: str,
    capabilities: tuple[str, ...],
    factories: dict[str, tuple[str, str]],
    startup_module: str | None = None,
) -> ProviderSpec:
    """Build a ProviderSpec, mapping factory tuples to lazy factories.

    Each *factories* entry maps a capability id to
    ``(module_name, ClassName)``; the module is imported on first use.
    """
    return ProviderSpec(
        id=pid,
        name=name,
        description=description,
        capabilities=frozenset(capabilities),
        config=_descriptor(pid),
        factories={
            capability: _factory(f"lookups.providers.{module_name}", class_name)
            for capability, (module_name, class_name) in factories.items()
        },
        startup_check=(_startup_check(f"lookups.providers.{startup_module}") if startup_module else None),
    )


PROVIDERS: dict[str, ProviderSpec] = {
    spec.id: spec
    for spec in (
        _spec(
            "fr24",
            "FlightRadar24",
            "Live flights from the FlightRadar24 feed. Works without an "
            "API key, but the feed is the least reliable of the online "
            "providers.",
            ("flights", "routes", "aircraft"),
            {
                "flights": ("fr24.flights", "FlightProvider"),
                "routes": ("fr24.routes", "RouteProvider"),
                "aircraft": ("fr24.aircraft", "AircraftProvider"),
            },
            startup_module="fr24.flights",
        ),
        _spec(
            "opensky",
            "OpenSky Network",
            "Live aircraft state vectors via the OpenSky Network REST API "
            "(OAuth2 client credentials).",
            ("flights",),
            {"flights": ("opensky.flights", "FlightProvider")},
            startup_module="opensky.flights",
        ),
        _spec(
            "tar1090",
            "tar1090",
            "A local / self-hosted tar1090 (or dump1090) receiver fed by "
            "your own ADS-B antenna.",
            ("flights",),
            {"flights": ("tar1090.flights", "FlightProvider")},
            startup_module="tar1090.flights",
        ),
        _spec(
            "hexdb",
            "HexDB",
            "Free route and aircraft database at hexdb.io. No API key "
            "required.",
            ("routes", "aircraft"),
            {
                "routes": ("hexdb.routes", "RouteProvider"),
                "aircraft": ("hexdb.aircraft", "AircraftProvider"),
            },
        ),
        _spec(
            "adsbdb",
            "adsbdb.com",
            "Free callsign-route and aircraft database at adsbdb.com. No "
            "API key required.",
            ("routes", "aircraft"),
            {
                "routes": ("adsbdb.routes", "RouteProvider"),
                "aircraft": ("adsbdb.aircraft", "AircraftProvider"),
            },
        ),
        _spec(
            "aerodatabox",
            "AeroDataBox",
            "Commercial flight and aircraft data via RapidAPI.",
            ("routes", "aircraft"),
            {
                "routes": ("aerodatabox.routes", "RouteProvider"),
                "aircraft": ("aerodatabox.aircraft", "AircraftProvider"),
            },
        ),
    )
}


def provider_spec(pid: str) -> ProviderSpec | None:
    """The catalogue entry for *pid*, or None if unknown."""
    return PROVIDERS.get(pid)


def specs_for_capability(capability: str) -> list[ProviderSpec]:
    """All known providers that implement *capability*, in catalogue order."""
    return [spec for spec in PROVIDERS.values() if capability in spec.capabilities]


# ---------------------------------------------------------------------------
# Configuration plumbing (imports Config lazily to avoid cycles)
# ---------------------------------------------------------------------------


def load_config():
    """The process-wide Config instance (read lazily)."""
    from setup.configuration import Config

    return Config.instance()


def normalise_provider_list(
    entries, capability: str
) -> tuple[list[dict], list[str]]:
    """Validate/sanitize one persisted provider priority list.

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
        if not spec.implements(capability):
            warnings.append(f"provider {pid!r} does not support {capability}; dropped")
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


def resolve_chain(cfg, capability: str) -> list[tuple[str, object]]:
    """Construct the provider chain for *capability*.

    Walks the user's priority list for *capability* (``route_providers``
    for both the routes and aircraft chains) and builds an adapter for
    each entry that is enabled and fully configured.  Returns
    ``[(provider_id, adapter), ...]`` in priority order; adapters are
    memoised (see :func:`get_adapter`).
    """
    chain: list[tuple[str, object]] = []
    for entry in getattr(cfg, _PRIORITY_LIST_ATTR[capability]):
        if not entry.get("enabled"):
            continue
        spec = PROVIDERS.get(entry["provider"])
        if spec is None or not spec.implements(capability):
            continue
        settings = cfg.provider_settings(spec.id)
        if not spec.config.is_configured(settings):
            continue
        adapter = get_adapter(capability, spec.id, settings)
        if adapter is not None:
            chain.append((spec.id, adapter))
    return chain


def top_provider(cfg, capability: str) -> ProviderSpec | None:
    """The highest-priority enabled, configured provider for *capability*."""
    chain = resolve_chain(cfg, capability)
    return PROVIDERS[chain[0][0]] if chain else None


# ---------------------------------------------------------------------------
# Adapter construction (memoised - sessions/tokens survive across polls)
# ---------------------------------------------------------------------------

_adapter_cache: dict[tuple, object] = {}


def _settings_fingerprint(settings: dict) -> tuple:
    """Hashable snapshot of *settings* so config edits rebuild adapters."""
    return tuple(sorted((key, str(value)) for key, value in settings.items()))


def get_adapter(capability: str, pid: str, settings: dict) -> object | None:
    """Return the (cached) capability adapter for *pid*.

    Adapters are rebuilt automatically when their settings change, so
    configuration edits take effect without a restart.
    """
    key = (capability, pid, _settings_fingerprint(settings))
    adapter = _adapter_cache.get(key)
    if adapter is None:
        spec = PROVIDERS.get(pid)
        factory = spec.factory(capability) if spec else None
        if factory is None:
            return None
        adapter = factory(settings)
        _adapter_cache[key] = adapter
    return adapter


def reset_adapters() -> None:
    """Drop all memoised adapters (tests and config reloads)."""
    _adapter_cache.clear()
