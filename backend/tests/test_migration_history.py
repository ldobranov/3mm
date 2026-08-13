import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_CONFIG = REPOSITORY_ROOT / "backend" / "alembic.ini"


def _alembic(database_url: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(ALEMBIC_CONFIG),
            *arguments,
        ],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )


def test_clean_database_migrates_to_head_and_back_to_base(tmp_path):
    database_path = tmp_path / "clean-migration.db"
    database_url = f"sqlite:///{database_path.as_posix()}"

    _alembic(database_url, "upgrade", "head")
    _alembic(database_url, "check")

    engine = create_engine(database_url)
    tables = set(inspect(engine).get_table_names())
    assert "settings" in tables
    assert "devices" in tables
    assert "automation_proposals" in tables
    assert "automation_revisions" in tables
    assert "ai_jobs" in tables
    assert "ai_usage_ledger" in tables
    engine.dispose()

    _alembic(database_url, "upgrade", "head")
    _alembic(database_url, "downgrade", "base")

    engine = create_engine(database_url)
    assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
    engine.dispose()
