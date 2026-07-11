"""
FlightTracker update manager.

Checks for tagged releases on GitHub and applies updates via git + pip.
"""

from __future__ import annotations

import json
import logging
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from utilities import routes_cache
from utilities.tle_manager import TLE_CACHE_PATH
from version import VERSION

logger = logging.getLogger("updater")

GITHUB_OWNER = "ColinWaddell"
GITHUB_REPO = "FlightTracker"
GITHUB_TAGS_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/tags"

# Project root is the parent of the utilities/ directory.
PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Version comparison
# ---------------------------------------------------------------------------


def parse_version(tag: str) -> list[int]:
    """Parse a tag string like 'v2.0.1' or '2.0.1' into [major, minor, patch]."""
    cleaned = tag.lstrip("vV").strip()
    parts = cleaned.split(".")
    result: list[int] = []
    for part in parts:
        try:
            result.append(int(part))
        except ValueError:
            # Ignore non-numeric suffixes (e.g. "2.0.1-rc1" -> [2, 0, 1])
            numeric = ""
            for ch in part:
                if ch.isdigit():
                    numeric += ch
                else:
                    break
            result.append(int(numeric) if numeric else 0)
    # Pad to 3 elements
    while len(result) < 3:
        result.append(0)
    return result[:3]


def is_newer(remote: list[int], local: list[int]) -> bool:
    """Return True if remote version is strictly greater than local."""
    for r, lcl in zip(remote, local):
        if r > lcl:
            return True
        if r < lcl:
            return False
    return False  # equal


def version_string(version: list[int]) -> str:
    """Format a version list as 'v2.0.1'."""
    return "v" + ".".join(map(str, version))


# ---------------------------------------------------------------------------
# GitHub API
# ---------------------------------------------------------------------------


def get_latest_tag() -> tuple[str | None, str | None, str | None]:
    """Query GitHub for the latest tag.

    Returns (tag_name, commit_sha, error_message).
    On failure, tag_name and commit_sha are None and error_message is set.
    """
    try:
        req = urllib.request.Request(
            GITHUB_TAGS_URL,
            headers={
                "User-Agent": f"{GITHUB_OWNER}/{GITHUB_REPO} update-checker",
                "Accept": "application/vnd.github+json",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            tags = json.loads(resp.read().decode("utf-8"))

        if not tags:
            return None, None, "No tags found on GitHub."

        latest = tags[0]
        tag_name = latest.get("name", "")
        commit_sha = latest.get("commit", {}).get("sha", "")
        return tag_name, commit_sha, None

    except urllib.error.URLError as exc:
        logger.error("Network error fetching tags: %s", exc)
        return None, None, f"Network error: {exc.reason}"
    except Exception as exc:  # noqa: BLE001
        logger.error("Error fetching tags: %s", exc)
        return None, None, f"Error: {exc}"


def get_update_info() -> dict:
    """Get full update status as a dict suitable for the web UI.

    Keys: current_version, latest_version, update_available, tag, error
    """
    tag_name, _commit_sha, error = get_latest_tag()

    current = version_string(VERSION)

    if error:
        return {
            "current_version": current,
            "latest_version": None,
            "update_available": False,
            "tag": None,
            "error": error,
        }

    remote_version = parse_version(tag_name)
    update_available = is_newer(remote_version, VERSION)

    return {
        "current_version": current,
        "latest_version": version_string(remote_version),
        "update_available": update_available,
        "tag": tag_name,
        "error": None,
    }


# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------


def detect_platform() -> str:
    """Detect whether we're on a Pi 5 or older Pi.

    Returns 'pi5' or 'pi'.
    """
    try:
        import adafruit_blinka_raspberry_pi5_piomatter  # noqa: F401

        return "pi5"
    except ImportError:
        return "pi"


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def _run_git(args: list[str], timeout: int = 60) -> tuple[bool, str]:
    """Run a git command in the project root. Returns (success, output)."""
    cmd = ["git"] + args
    try:
        result = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = (result.stdout + result.stderr).strip()
        if result.returncode != 0:
            logger.error(
                "git %s failed (rc=%d): %s", " ".join(args), result.returncode, output
            )
            return False, output
        logger.info("git %s succeeded: %s", " ".join(args), output)
        return True, output
    except subprocess.TimeoutExpired:
        return False, f"git {' '.join(args)} timed out after {timeout}s"
    except Exception as exc:  # noqa: BLE001
        return False, f"git {' '.join(args)} error: {exc}"


def is_dirty_tree() -> bool:
    """Check if the git working tree has uncommitted changes to tracked files.

    Untracked files (e.g. .bak files left by config migration) are ignored
    so they don't block updates.
    """
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=10,
        )
        return bool(result.stdout.strip())
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# Update execution
# ---------------------------------------------------------------------------


def perform_update(tag: str) -> tuple[bool, str]:
    """Apply an update by checking out the given git tag and updating deps.

    Returns (success, message).
    """
    # 1. Check for dirty working tree
    if is_dirty_tree():
        return (
            False,
            "Working tree has local modifications. Please commit or stash them "
            "before updating, or run 'git checkout -- .' to discard changes.",
        )

    # 2. Fetch tags
    # --force allows existing tags to be updated if they were moved on the remote
    # (e.g. after an amended commit). Without it, git rejects any tag that would
    # change and aborts the whole fetch.
    logger.info("Fetching tags from origin...")
    ok, msg = _run_git(["fetch", "--tags", "--force", "origin"], timeout=60)
    if not ok:
        return False, f"git fetch failed: {msg}"

    # 3. Checkout the tag
    logger.info("Checking out tag %s...", tag)
    ok, msg = _run_git(["checkout", tag], timeout=30)
    if not ok:
        return False, f"git checkout {tag} failed: {msg}"

    # 4. Update Python dependencies
    platform = detect_platform()
    requirements_file = PROJECT_ROOT / "platforms" / platform / "requirements.txt"
    if not requirements_file.exists():
        # Fall back to pi if platform-specific file missing
        requirements_file = PROJECT_ROOT / "platforms" / "pi" / "requirements.txt"

    venv_pip = PROJECT_ROOT / "env" / "bin" / "pip"
    if not venv_pip.exists():
        # Windows venv layout
        venv_pip = PROJECT_ROOT / "env" / "Scripts" / "pip.exe"

    logger.info("Installing dependencies from %s...", requirements_file)
    try:
        result = subprocess.run(
            [str(venv_pip), "install", "-r", str(requirements_file)],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = (result.stdout + result.stderr).strip()
        if result.returncode != 0:
            logger.error("pip install failed (rc=%d): %s", result.returncode, output)
            return False, f"pip install failed: {output}"
        logger.info("pip install succeeded")
    except subprocess.TimeoutExpired:
        return False, "pip install timed out after 120s"
    except Exception as exc:  # noqa: BLE001
        return False, f"pip install error: {exc}"

    # 5. Clear on-disk caches so stale entries don't survive the update
    logger.info("Clearing caches...")
    routes_cache.clear()
    if TLE_CACHE_PATH.exists():
        try:
            TLE_CACHE_PATH.unlink()
        except OSError as exc:
            logger.warning("Could not delete TLE cache: %s", exc)

    return True, f"Successfully updated to {tag}."
