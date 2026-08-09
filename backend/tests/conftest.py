import os
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
    TEST_DATABASE_PATH.unlink(missing_ok=True)
