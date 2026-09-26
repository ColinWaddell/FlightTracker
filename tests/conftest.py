import os
import sys

import pytest

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


@pytest.fixture
def fresh_config(monkeypatch):
    """An isolated in-memory Config for tests that touch settings.

    House pattern (see test_configuration.py): build via __new__, set
    data_store directly, and stub save() so nothing touches the real
    config.json.  instance() is patched so production code that pulls
    the singleton sees this instance.
    """
    from setup.configuration import Config

    cfg = Config.__new__(Config)
    cfg.data_store = {}
    cfg._sun_cache = {}
    monkeypatch.setattr(Config, "save", lambda self: None)
    monkeypatch.setattr(Config, "instance", classmethod(lambda cls: cfg))
    return cfg
