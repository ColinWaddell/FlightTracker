"""
Lookups: provider adapters, lookup services and shared plumbing.

Public entry points (all lazily resolved so imports stay cheap):

- ``lookups.flights``      - live flight observations
- ``lookups.routes``       - callsign route resolution
- ``lookups.aircraft``     - mode-s aircraft resolution
- ``lookups.enrichment``   - observation -> fully-resolved RouteInfo
- ``lookups.registry``     - the provider catalogue
- ``lookups.results``      - shared result types
- ``lookups.cache``        - persistent lookup cache
- ``lookups.quarantine``   - temporary provider-failure tracking
- ``lookups.config``       - provider configuration descriptors
"""

from __future__ import annotations

_LAZY_MODULES = (
    "flights",
    "routes",
    "aircraft",
    "enrichment",
    "registry",
    "results",
    "cache",
    "quarantine",
    "config",
)


def __getattr__(name):
    if name in _LAZY_MODULES:
        import importlib

        return importlib.import_module(f"lookups.{name}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
