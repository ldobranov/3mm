import os
import sys
from pathlib import Path

import pytest

TEST_DATABASE_PATH = Path("/tmp/3mm-pytest.db")
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DATABASE_PATH.as_posix()}"


@pytest.fixture(autouse=True)
def clear_settings_cache():
    from backend.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def pytest_sessionfinish(session, exitstatus):
    for module_name in ("backend.database", "backend.utils.db_engine"):
        module = sys.modules.get(module_name)
        engine = getattr(module, "engine", None)
        if engine is not None:
            engine.dispose()
    TEST_DATABASE_PATH.unlink(missing_ok=True)
