import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "flight-tracker.py"
SPEC = importlib.util.spec_from_file_location("flight_tracker_module", MODULE_PATH)
flight_tracker_module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(flight_tracker_module)


def test_check_routing_reachable(monkeypatch):
    from types import SimpleNamespace

    from utilities import route_providers

    monkeypatch.setattr(route_providers, "check_routing", lambda: True)
    monkeypatch.setattr(route_providers, "set_aerodatabox_key", lambda key: None)

    cfg = SimpleNamespace(aerodatabox_api_key=None)
    assert flight_tracker_module._check_routing_reachable(cfg) is True


def test_check_routing_reachable_handles_failure(monkeypatch):
    from types import SimpleNamespace

    from utilities import route_providers

    monkeypatch.setattr(route_providers, "check_routing", lambda: False)
    monkeypatch.setattr(route_providers, "set_aerodatabox_key", lambda key: None)

    cfg = SimpleNamespace(aerodatabox_api_key=None)
    assert flight_tracker_module._check_routing_reachable(cfg) is False
