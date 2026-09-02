import os
import sys

# Ensure the project root is on sys.path so tests can import packages
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Hermetic test data.  platformdirs resolves PLATFORM_DATA_DIR from
# XDG_DATA_HOME on Linux, so pointing it at a throwaway directory before
# any project module is imported keeps the suite from reading or writing
# the real user cache / usage / config databases.  Set the variable
# before setup.configuration is imported anywhere - its module-level
# paths are computed at import time.
os.environ.setdefault(
    "XDG_DATA_HOME", os.path.join(os.path.dirname(__file__), ".testdata")
)
