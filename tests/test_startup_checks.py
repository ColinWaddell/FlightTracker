import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "flight-tracker.py"
SPEC = importlib.util.spec_from_file_location("flight_tracker_module", MODULE_PATH)
flight_tracker_module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(flight_tracker_module)


def test_check_hexdb_reachability(monkeypatch):
    class DummyResponse:
        status_code = 200

    calls = []

    def fake_get(url, timeout):
        calls.append((url, timeout))
        return DummyResponse()

    monkeypatch.setattr("requests.get", fake_get)

    assert flight_tracker_module._check_hexdb_reachable() is True
    assert calls == [("https://hexdb.io", 5)]


def test_check_hexdb_reachability_handles_failure(monkeypatch):
    def fake_get(url, timeout):
        raise RuntimeError("boom")

    monkeypatch.setattr("requests.get", fake_get)

    assert flight_tracker_module._check_hexdb_reachable() is False
