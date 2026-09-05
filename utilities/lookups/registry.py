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
from dataclasses import dataclass
from typing import Callable

from utilities.lookups.config import ProviderConfig

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
#
# Everything static about a provider - identity, description, capabilities
# and settings fields - lives in the provider's own module at
# utilities/lookups/providers/<id>/config.py.  This catalogue fixes the display order
# and derives the rest (adapter wiring, startup probes) from those
# descriptors, so adding a provider means writing its package and adding
# one line here - there is nothing to keep in sync.
# ---------------------------------------------------------------------------

# Catalogue order also drives the order newly-shipped providers are appended
# to saved priority lists by setup.configuration._complete_provider_lists.
_CATALOGUE_ORDER = (
    "fr24",
    "opensky",
    "tar1090",
    "adsbfi",
    "adsblol",
    "airplaneslive",
    "hexdb",
    "adsbdb",
    "adsbim",
    "aerodatabox",
    "fr24api",
    "airlabs",
    "flightaware",
)

# Standard adapter class name for each capability inside a provider package.
_FACTORY_CLASS = {
    FLIGHTS: "FlightProvider",
    ROUTES: "RouteProvider",
    AIRCRAFT: "AircraftProvider",
}


def _descriptor(pid: str) -> ProviderConfig:
    import importlib

    return importlib.import_module(
        f"utilities.lookups.providers.{pid}.config"
    ).PROVIDER


def _spec(pid: str) -> ProviderSpec:
    """Build a catalogue entry from *pid*'s config descriptor.

    Adapter factories and the startup probe are derived from the
    descriptor's capabilities rather than hand-wired here.
    """
    descriptor = _descriptor(pid)
    if descriptor.id != pid:
        raise ValueError(
            f"catalogue id {pid!r} does not match descriptor id {descriptor.id!r}"
        )
    unknown = set(descriptor.capabilities) - set(_FACTORY_CLASS)
    if unknown:
        raise ValueError(
            f"provider {pid!r} declares unknown capabilities {sorted(unknown)}"
        )
    return ProviderSpec(
        id=descriptor.id,
        name=descriptor.name,
        description=descriptor.description,
        capabilities=frozenset(descriptor.capabilities),
        config=descriptor,
        factories={
            capability: _factory(
                f"utilities.lookups.providers.{pid}.{capability}",
                _FACTORY_CLASS[capability],
            )
            for capability in descriptor.capabilities
        },
        # Every flights-capable provider module exposes startup_check(settings).
        startup_check=(
            _startup_check(f"utilities.lookups.providers.{pid}.flights")
            if FLIGHTS in descriptor.capabilities
            else None
        ),
    )


PROVIDERS: dict[str, ProviderSpec] = {pid: _spec(pid) for pid in _CATALOGUE_ORDER}


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


def normalise_provider_list(entries, capability: str) -> tuple[list[dict], list[str]]:
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
