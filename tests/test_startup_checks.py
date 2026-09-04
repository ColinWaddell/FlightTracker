import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "flight-tracker.py"
SPEC = importlib.util.spec_from_file_location("flight_tracker_module", MODULE_PATH)
flight_tracker_module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(flight_tracker_module)


def test_check_data_source(monkeypatch):
    import utilities.lookups.flights as flights_service

    monkeypatch.setattr(flights_service, "startup_check", lambda: True)
    assert flight_tracker_module._check_data_source(None) is True


def test_check_data_source_handles_failure(monkeypatch):
    import utilities.lookups.flights as flights_service

    def boom():
        raise RuntimeError("nope")

    monkeypatch.setattr(flights_service, "startup_check", boom)
    assert flight_tracker_module._check_data_source(None) is False


def test_check_routing_reachable(monkeypatch):
    import utilities.lookups.routes as routes_service

    monkeypatch.setattr(routes_service, "check_routing", lambda: True)

    assert flight_tracker_module._check_routing_reachable(None) is True


def test_check_routing_reachable_handles_failure(monkeypatch):
    import utilities.lookups.routes as routes_service

    monkeypatch.setattr(routes_service, "check_routing", lambda: False)
    assert flight_tracker_module._check_routing_reachable(None) is False
