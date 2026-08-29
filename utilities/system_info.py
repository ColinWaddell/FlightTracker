"""
System telemetry for the status page.

Every metric here is read straight from /proc, /sys or the standard
library - no packages, no subprocesses.  Each getter returns None when the
host can't provide the value, so callers can simply skip what isn't
available (e.g. temperature and memory are Linux-only concepts).

The throughput helper notes: CurrantPi sampled the interface counters and
slept a second inside the request, delaying every page load.  Instead, the
last counter sample is stored module-side and each status render reports
traffic since the previous render (~15s apart thanks to auto-refresh);
the first render simply has no rate to report yet.
"""

from __future__ import annotations

import logging
import os
import shutil
import socket
import time

logger = logging.getLogger(__name__)


def _read_first_token(path: str) -> str | None:
    """First whitespace-separated token of *path*, or None."""
    try:
        with open(path) as fh:
            token = fh.read().split()[0]
    except (OSError, IndexError):
        return None
    return token


def _read(path: str) -> str | None:
    try:
        with open(path) as fh:
            return fh.read()
    except OSError:
        return None


def hostname() -> str:
    """The machine's hostname, or "" if unavailable."""
    if hasattr(os, "uname"):
        return os.uname().nodename

    return socket.gethostname() or ""


def hardware_model() -> str | None:
    """Board / processor model string, when the kernel reports one."""
    model = _read("/proc/device-tree/model")
    if model:
        return model.replace("\x00", "").strip()
    for line in (_read("/proc/cpuinfo") or "").splitlines():
        key, _, value = line.partition(":")
        if key.strip() in ("model name", "Model", "Hardware"):
            return value.strip()
    return None


def cpu_temperature() -> float | None:
    """CPU temperature in degrees Celsius, or None if no sensor reports.

    Raspberry Pis expose the SoC temperature on the first thermal zone.
    """
    try:
        zones = sorted(os.listdir("/sys/class/thermal"))
    except OSError:
        return None
    for zone in zones:
        token = _read(f"/sys/class/thermal/{zone}/temp")
        if token is None:
            continue
        try:
            return int(token) / 1000
        except ValueError:
            continue
    return None


def uptime_seconds() -> int | None:
    """Seconds since boot, from /proc/uptime."""
    token = _read("/proc/uptime")
    if token is None:
        return None
    try:
        return int(float(token.split()[0]))
    except (ValueError, IndexError):
        return None


def load_average() -> tuple[float, float, float] | None:
    """1-, 5- and 15-minute load averages.  None where unsupported."""
    try:
        one, five, fifteen = os.getloadavg()
        return round(one, 2), round(five, 2), round(fifteen, 2)
    except (OSError, ValueError):
        return None


def memory_usage() -> dict | None:
    """``{"total_kb", "used_kb", "percent"}`` from a single /proc/meminfo read.

    ``used`` follows the modern interpretation: total minus what the
    kernel could still reclaim (MemAvailable), which is the figure that
    matters when asking whether the Pi is about to fall over.
    """
    mem: dict[str, int] = {}
    for line in (_read("/proc/meminfo") or "").splitlines():
        key, _, rest = line.partition(":")
        try:
            value = int(rest.strip().split()[0])
        except (ValueError, IndexError):
            continue
        mem[key] = value
    total = mem.get("MemTotal")
    available = mem.get("MemAvailable")
    if not total or total <= 0 or available is None:
        return None
    used = max(0, total - available)
    return {
        "total_kb": total,
        "used_kb": used,
        "percent": round(100 * used / total, 1),
    }


def storage_usage(mount: str = "/") -> dict | None:
    """``{"total_gb", "used_gb", "percent"}`` for the filesystem at *path*."""

    usage = shutil.disk_usage(mount)
    if not usage.total:
        return None
    return {
        "mount": mount,
        "total_gb": usage.total / 1024**3,
        "used_gb": usage.used / 1024**3,
        "percent": round(100 * usage.used / usage.total, 1),
    }


def ip_address() -> str | None:
    """Best-effort LAN address via a UDP connect (the packet is never sent)."""

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0] or None
    except OSError:
        return None
    finally:
        sock.close()


def default_interface() -> str | None:
    """The interface currently carrying the default route, if any."""
    for line in (_read("/proc/net/route") or "").splitlines()[1:]:
        fields = line.split()
        if len(fields) > 2 and fields[1] == "00000000":
            return fields[0]
    return None


# ---------------------------------------------------------------------------
# Network throughput
#
# CurrantPi sampled the interface counters, slept a second inside the
# request (delaying every page load), then diffed.  Here the counters are
# stored between page loads instead: each render reports traffic since the
# previous render (~15s with the page's auto-refresh), and the first
# render simply has no rate to report.
# ---------------------------------------------------------------------------

_last_samples: dict[str, tuple[float, int, int]] = {}


def network_throughput() -> dict | None:
    """Downlink/uplink rate in bytes/second since the previous status view.

    Returns ``{"interface", "down_bps", "up_bps"}`` or None when the
    interface can't be found or there is no earlier sample to diff
    against.
    """
    interface = default_interface()
    if interface is None:
        return None

    counters = _counter_pair(interface)
    if counters is None:
        return None
    rx_bytes, tx_bytes = counters

    now = time.monotonic()
    previous = _last_samples.get(interface)
    _last_samples[interface] = (now, rx_bytes, tx_bytes)

    if previous is None or now <= previous[0]:
        return None

    prev_ts, prev_rx, prev_tx = previous
    elapsed = now - prev_ts
    if elapsed <= 0:
        return None

    return {
        "interface": interface,
        "elapsed_s": round(elapsed, 1),
        "down_bps": max(0, rx_bytes - prev_rx) / elapsed,
        "up_bps": (max(0, tx_bytes - prev_tx)) / elapsed,
    }


def _counter_pair(interface: str) -> tuple[int, int] | None:
    rx = _read(f"/sys/class/net/{interface}/statistics/rx_bytes")
    tx = _read(f"/sys/class/net/{interface}/statistics/tx_bytes")
    if rx is None or tx is None:
        return None
    try:
        return int(rx.split()[0]), int(tx.split()[0])
    except (IndexError, ValueError):
        return None
