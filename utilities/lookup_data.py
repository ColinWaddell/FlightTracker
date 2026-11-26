"""Single owner of the bundled lookup data directory.

Every bundled local lookup (airport tables, aircraft body classes, airline
codes and logos) ships in ``assets/lookups/`` as generated data: the
FlightTracker-Scrappers repository builds the whole folder and its refresh
process drops it in unchanged.  Never hand-edit its files - regenerate from
the Scrappers repository and copy the results in.
"""

from __future__ import annotations

from pathlib import Path

LOOKUPS_DIR = Path(__file__).parents[1] / "assets" / "lookups"
