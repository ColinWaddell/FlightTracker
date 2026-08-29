"""Operator-code normalisation shared by route/aircraft providers."""

from __future__ import annotations


def clean_operator_code(value) -> str:
    """Normalise a provider operator-flag value to a 3-letter ICAO code.

    Providers expose the registered operator as an "operator flag code"
    (hexdb ``OperatorFlagCode``, adsbdb
    ``registered_owner_operator_flag_code``).  In practice these are ICAO
    airline designators, but the field is free-form and providers
    occasionally return blanks, registration prefixes, or longer strings.

    Returns the upper-cased code when it is exactly 3 alphabetic
    characters, otherwise ``""`` - so a malformed value is treated as
    "no operator" rather than being passed on to a logo lookup.
    """
    code = (value or "").strip().upper()
    if len(code) == 3 and code.isalpha():
        return code
    return ""