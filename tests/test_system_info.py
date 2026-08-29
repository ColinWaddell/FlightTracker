"""Tests for the status-page system telemetry (utilities/system_info.py).

These read the real host - assertions are shaped to hold on any Linux box
(and, where possible, anywhere Python runs), not to assert specific values.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def client():
    from web.app import app

    flask_client = app.test_client()
    with flask_client.session_transaction() as sess:
        sess["authenticated"] = True
    return flask_client


class TestSystemInfo:
    def test_hostname_non_empty(self):
        from utilities.system_info import hostname

        assert hostname()

    def test_uptime_seconds_positive(self):
        from utilities.system_info import uptime_seconds

        uptime = uptime_seconds()
        assert uptime is not None
        assert uptime > 0

    def test_load_average_returned_triple(self):
        from utilities.system_info import load_average

        load = load_average()
        assert load is not None
        one, five, fifteen = load
        assert all(v >= 0 for v in (one, five, fifteen))

    def test_memory_shape(self):
        from utilities.system_info import memory_usage

        memory = memory_usage()
        if memory is None:  # non-Linux host - nothing to assert
            return
        assert memory["total_kb"] > 0
        assert memory["used_kb"] >= 0
        assert 0 <= memory["percent"] <= 100

    def test_storage_shape(self):
        from utilities.system_info import storage_usage

        storage = storage_usage("/")
        assert storage is not None
        assert storage["total_gb"] > 0
        assert 0 <= storage["percent"] <= 100

    def test_temperature_none_or_plausible(self):
        from utilities.system_info import cpu_temperature

        temp = cpu_temperature()
        assert temp is None or 0 < temp < 120

    def test_ip_is_dotted_quad_or_none(self):
        from utilities.system_info import ip_address

        ip = ip_address()
        assert ip is None or len(ip.split(".")) == 4

    def test_throughput_first_call_has_no_rate(self):
        from utilities.system_info import _last_samples, network_throughput

        _last_samples.clear()
        first = network_throughput()
        # A default-route interface exists on the test host (CI has one too),
        # but the very first call cannot report a rate.
        assert first is None

    def test_throughput_second_call_reports_rate(self, monkeypatch):

        from utilities import system_info

        interface = system_info.default_interface()
        if interface is None:
            return  # host has no routing table (e.g. sandboxed CI)
        monkeypatch.setattr(system_info.time, "monotonic", system_info.time.monotonic)
        system_info.network_throughput()
        second = system_info.network_throughput()
        if second is None:
            return  # counters unreadable on this host
        assert second["down_bps"] >= 0
        assert second["up_bps"] >= 0


class TestHumaniseUptime:
    def test_days(self):
        from web.app import _humanise_uptime

        assert _humanise_uptime(5 * 86400 + 3 * 3600) == "5d 3h"

    def test_hours(self):
        from utilities.system_info import uptime_seconds  # noqa: F401
        from web.app import _humanise_uptime

        assert _humanise_uptime(6 * 3600 + 12 * 60) == "6h 12m"

    def test_minutes_only(self):
        from web.app import _humanise_uptime

        assert _humanise_uptime(4 * 60) == "4m"


class TestStatusPageTelemetry:
    def test_status_page_includes_system_card(self, client):
        html = client.get("/status").get_data(as_text=True)
        assert "System" in html

    def test_status_page_shows_hostname(self, client):
        from utilities.system_info import hostname

        html = client.get("/status").get_data(as_text=True)
        assert hostname() in html

    def test_status_page_shows_uptime(self, client):
        from utilities.system_info import uptime_seconds
        from web.app import _humanise_uptime

        uptime = uptime_seconds()
        if uptime is None:
            return
        assert _humanise_uptime(uptime) in client.get("/status").get_data(as_text=True)
