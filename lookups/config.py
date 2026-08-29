"""
Declarative configuration descriptors for lookup providers.

Each provider describes its configuration requirements in code via a
:class:`ProviderConfig` holding :class:`ConfigField` descriptors (see
``lookups/providers/*/config.py``).  The same descriptors drive:

* defaults for the central configuration file,
* validation of persisted configuration (field-level),
* web UI form fields (label, type, help text),
* sensitive/private-field handling (masking in the settings page and
  redaction in the safe-to-post config export).

The central configuration system (``setup/configuration.py``) owns
persistence; provider modules never read or write config files themselves.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Sentinel rendered/sent by the web UI in place of a stored secret.
# Posting this exact value back means "keep the existing value".
MASK = "**********"

# Redaction marker used by the safe-to-post config export.
REDACTED = "***REDACTED***"


# ---------------------------------------------------------------------------
# Field / provider descriptors
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConfigField:
    """One provider setting.

    ``type``      - "text" | "password" | "int" | "float" | "bool".
    ``required``  - provider cannot be used until this field is non-empty.
    ``sensitive`` - the value must never appear in the settings page HTML
                    or the safe-to-post config export.  Note that this is
                    independent of ``type``: text fields may be sensitive.
    """

    key: str
    label: str
    type: str = "text"
    default: Any = ""
    description: str = ""
    required: bool = False
    sensitive: bool = False

    def coerce(self, value: Any) -> Any:
        """Coerce *value* to the field's type; raises ValueError/TypeError when invalid."""
        if self.type == "int":
            return int(value)
        if self.type == "float":
            return float(value)
        if self.type == "bool":
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.strip().lower() in ("1", "true", "yes", "on")
            return bool(value)
        # text & password
        if value is None:
            return ""
        return str(value)

    @classmethod
    def password(cls, key: str, label: str, **kwargs) -> ConfigField:
        kwargs.setdefault("type", "password")
        kwargs.setdefault("sensitive", True)
        return cls(key=key, label=label, **kwargs)

    def as_dict_view(self) -> dict:
        """JSON-safe descriptor for the web UI (values are added by the caller)."""
        return {
            "key": self.key,
            "label": self.label,
            "type": self.type,
            "description": self.description,
            "required": self.required,
            "sensitive": self.sensitive,
        }


@dataclass(frozen=True)
class ProviderConfig:
    """A provider's configuration descriptor.

    This is the single source of truth for a provider: identity (id, name,
    description), the capabilities it implements, and its settings fields.
    The registry catalogue in ``lookups/registry.py`` derives everything
    else (adapter wiring, startup probes) from here.
    """

    id: str
    name: str
    description: str = ""
    # Capability ids served by this provider ("flights", "routes", "aircraft").
    capabilities: tuple[str, ...] = ()
    fields: tuple[ConfigField, ...] = ()

    def field(self, key: str) -> ConfigField | None:
        for f in self.fields:
            if f.key == key:
                return f
        return None

    def defaults(self) -> dict:
        """Default values for every field, keyed by field name."""
        return {f.key: f.default for f in self.fields}

    def missing_required(self, values: dict) -> list[str]:
        """Return the keys of required fields missing (or blank) in *values*."""
        missing = []
        for f in self.fields:
            if not f.required:
                continue
            value = (values or {}).get(f.key)
            if value is None or str(value).strip() == "":
                missing.append(f.key)
        return missing

    def is_configured(self, values: dict | None) -> bool:
        """True when the provider has everything it needs to be used."""
        return not self.missing_required(values or {})

    def sensitive_fields(self) -> list[ConfigField]:
        return [f for f in self.fields if f.sensitive]


# ---------------------------------------------------------------------------
# Settings validation (field-level, schema-driven)
# ---------------------------------------------------------------------------


def validate_provider_settings(
    provider: ProviderConfig,
    values: Any,
) -> tuple[dict, list[str]]:
    """Validate persisted settings for *provider* against its descriptor.

    Returns ``(clean_settings, warnings)``.

    * Missing fields are filled from the descriptor defaults (nested
      defaults - a partial stored subtree never overrides whole defaults).
    * Unknown keys are dropped (no requirement to preserve them).
    * Invalid typed values are replaced by the field default with a
      warning - one bad value never invalidates the rest of the subtree.
    """
    stored = values if isinstance(values, dict) else {}
    clean: dict = {}
    warnings: list[str] = []

    defaults = provider.defaults()
    clean.update(defaults)

    for f in provider.fields:
        if f.key not in stored:
            continue
        raw = stored[f.key]
        try:
            clean[f.key] = f.coerce(raw)
        except (TypeError, ValueError):
            clean[f.key] = f.default
            warnings.append(f"Invalid value for {provider.id}.{f.key} - using default")

    for key in stored:
        if key not in defaults:
            warnings.append(f"Ignoring unknown setting {provider.id}.{key}")

    for w in warnings:
        logger.warning(w)

    return clean, warnings


def provider_settings_view(provider: ProviderConfig, settings: dict) -> dict:
    """Build the web-UI view of one provider's settings.

    Sensitive fields are replaced by the masked sentinel (the real value
    never reaches the browser); empty fields are rendered as "".
    """
    view = {}
    for f in provider.fields:
        value = settings.get(f.key, f.default)
        if f.sensitive:
            value = MASK if str(value) else ""
        view[f.key] = value
    return view


def apply_submitted_settings(
    provider: ProviderConfig,
    stored: dict,
    submitted: dict,
) -> tuple[dict, bool]:
    """Merge submitted form values into stored settings.

    Sensitive fields use mask-token semantics:
    * :data:`MASK` (or blank *submitted* for a sensitive field that is set,
      depending on the UI contract) keeps the existing value,
    * an empty string clears the value,
    * anything else replaces it.

    Returns ``(clean_settings, changed)``.
    """
    merged = dict(stored)
    changed = False
    for f in provider.fields:
        if f.key not in submitted:
            continue
        if f.sensitive:
            current = str(stored.get(f.key, "") or "")
            posted = str(submitted[f.key] or "")
            if posted == MASK:
                # Masked value posted back - keep whatever is stored.
                new = current
            elif posted == "":
                new = ""
            else:
                new = posted
            if new != current:
                changed = True
            merged[f.key] = new
        else:
            try:
                new = f.coerce(submitted[f.key])
            except (TypeError, ValueError):
                continue  # invalid form input ignored - keep stored/default
            if new != merged.get(f.key, f.default):
                changed = True
            merged[f.key] = new

    clean, _ = validate_provider_settings(provider, merged)
    return clean, changed


# ---------------------------------------------------------------------------
# Schema-driven redaction
# ---------------------------------------------------------------------------
