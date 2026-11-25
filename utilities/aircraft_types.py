"""ICAO type designator -> body-class lookup for the aircraft body filter.

Backs the flight scene's body-type filter with the bundled
``assets/aircraft_types.json`` table (see ``assets/aircraft_types.py`` for the
sources and the README's Attribution section).  The table maps an ICAO
aircraft type designator (``A20N``, ``B77W``, ``AT76``, ...) to a one-letter
body-class token:

=========  ====================  ============================================
token      bucket                basis
=========  ====================  ============================================
``w``      wide-body jet         wake J/H/S jet, minus narrow-body exceptions
``n``      narrow-body jet       wake M jet, mainstream
``r``      regional jet          wake M jet in the regional families
``t``      turboprop             turboprop/turboshaft engine
``b``      business jet          bizjet families, or light jet
``g``      light / GA            wake L, non-rotorcraft, non-jet
``h``      rotorcraft            helicopter / gyrocopter / tiltrotor
``m``      military              curated (doc 8643 cannot express it)
=========  ====================  ============================================

Designators absent from the table are *unclassified* - callers read them as
the :data:`UNKNOWN` bucket (``"u"``), which is a settings checkbox like the
rest, never a silently excluded state.

Two predicates serve the two filter layers:

* :func:`provider_allows` - the provider/fetch layer drops only *known*
  classes the user disabled, before the per-provider result cap.  An
  unclassified record always passes here: the feed may not carry the
  designator (OpenSky) or the airframe may just be unlisted, and dropping on
  that would hide aircraft the display filter would classify.
* :func:`is_allowed` - the display layer (overhead facade).  Unclassified
  flights pass only when the Unknown bucket is allowed, and this is also
  where a type that enrichment filled in late gets judged.
"""

from __future__ import annotations

import json
from pathlib import Path

UNKNOWN = "u"
ALL_BUCKETS = "wnrtbghmu"

# Settings-page checkbox labels, in canonical token order (Unknown last).
BUCKET_LABELS = (
    ("w", "Wide-body jets"),
    ("n", "Narrow-body jets"),
    ("r", "Regional jets"),
    ("t", "Turboprops"),
    ("b", "Business jets"),
    ("g", "Light & general aviation"),
    ("h", "Rotorcraft"),
    ("m", "Military"),
    (UNKNOWN, "Unknown"),
)

_TABLE_PATH = Path(__file__).parents[1] / "assets" / "aircraft_types.json"
_table: dict[str, str] | None = None


def _load_table() -> dict[str, str]:
    """Load the bundled table once; a missing/broken file degrades to empty."""
    global _table
    if _table is None:
        try:
            with open(_TABLE_PATH) as fh:
                loaded = json.load(fh)
            _table = loaded if isinstance(loaded, dict) else {}
        except Exception:  # noqa: BLE001 - asset problems must never crash a poll
            _table = {}
    return _table


def class_of(icao_type: str) -> str | None:
    """Body-class token for *icao_type*, or None when unclassified.

    Case-insensitive; blank input is always unclassified.
    """
    if not icao_type:
        return None
    return _load_table().get(icao_type.strip().upper())


def provider_allows(icao_type: str, allowed: frozenset[str] | None) -> bool:
    """Fetch-layer predicate - drop only *known* disallowed classes.

    ``None`` *allowed* means no filter is configured: everything passes
    (filter-off no-op).  Unclassified designs always pass; the Unknown
    checkbox is not consulted here (see the module docstring).
    """
    if allowed is None:
        return True
    bucket = class_of(icao_type)
    return bucket is None or bucket in allowed


def is_allowed(icao_type: str, allowed: frozenset[str] | None) -> bool:
    """Display-layer predicate - unclassified flights follow the Unknown box.

    ``None`` *allowed* means no filter is configured: everything passes.
    """
    if allowed is None:
        return True
    return (class_of(icao_type) or UNKNOWN) in allowed


def canonicalise(raw: str | None, default: str = ALL_BUCKETS) -> str:
    """Sanitise a submitted/stored bucket string into canonical form.

    Keeps only valid tokens, deduplicated, in canonical order.  ``None``
    (the setting was never posted - e.g. an old client or a fresh install)
    becomes *default*.  An empty string is a deliberate, legal choice ("show
    nothing") and is preserved; only *non-empty* garbage falls back to
    *default*.
    """
    if raw is None:
        return default
    valid = {c for c in raw.lower() if c in ALL_BUCKETS}
    if not valid:
        return "" if raw == "" else default
    return "".join(c for c in ALL_BUCKETS if c in valid)
