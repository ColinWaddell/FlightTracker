"""Tests for utilities.aircraft_types - the body-filter classifier module."""

import pytest

from utilities import aircraft_types as at


@pytest.fixture(autouse=True)
def _reset_table_cache():
    at._table = None
    yield
    at._table = None


def test_class_of_returns_token():
    assert at.class_of("A20N") == "n"
    assert at.class_of("B77W") == "w"
    assert at.class_of("e145") == "r"  # case-insensitive
    assert at.class_of(" AT76 ") == "t"  # whitespace-clean


def test_class_of_unclassified():
    assert at.class_of("") is None
    assert at.class_of(None) is None
    assert at.class_of("ZZZZ") is None  # not a real designator
    assert at.class_of("RRJ") is None  # absent from both sources


def test_provider_allows_none_is_noop():
    assert at.provider_allows("A388", None) is True
    assert at.provider_allows("", None) is True


def test_provider_allows_drops_known_disallowed():
    allowed = frozenset("t")  # turboprop-only panel
    assert at.provider_allows("AT76", allowed) is True
    assert at.provider_allows("B77W", allowed) is False


def test_provider_allows_keeps_unknown_regardless():
    # Unset types always pass the fetch layer - even with Unknown unticked.
    allowed = frozenset("t")
    assert at.provider_allows("ZZZZ", allowed) is True
    assert at.provider_allows("", allowed) is True


def test_is_allowed_unknown_unticked_hides_unclassified():
    allowed = frozenset("wnrtbghm")  # everything but Unknown
    assert at.is_allowed("A320", allowed) is True
    assert at.is_allowed("ZZZZ", allowed) is False
    assert at.is_allowed("", allowed) is False


def test_is_allowed_unknown_ticked_shows_unclassified():
    allowed = frozenset("u")
    assert at.is_allowed("ZZZZ", allowed) is True
    assert at.is_allowed("A320", allowed) is False


def test_is_allowed_all_tokens_and_unknown():
    everything = frozenset(at.ALL_BUCKETS)  # "wnrtbghmu"
    assert at.is_allowed("A320", everything) is True
    assert at.is_allowed("ZZZZ", everything) is True


def test_canonicalise_defaults_on_missing():
    assert at.canonicalise(None) == "wnrtbghmu"


def test_canonicalise_preserves_deliberate_empty():
    assert at.canonicalise("") == ""


def test_canonicalise_garbage_falls_back():
    assert at.canonicalise("xyz") == "wnrtbghmu"


def test_canonicalise_dedupes_and_orders():
    assert at.canonicalise("utwuw") == "wtu"  # canonical token order
    assert at.canonicalise("TT") == "t"


def test_basket_labels_cover_all_buckets():
    labels = dict(at.BUCKET_LABELS)
    assert set(labels) == frozenset(at.ALL_BUCKETS)
    assert all(label.strip() for _, label in at.BUCKET_LABELS)
