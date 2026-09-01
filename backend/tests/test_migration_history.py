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
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert "settings" in tables
    assert "devices" in tables
    assert "automation_proposals" in tables
    assert "automation_revisions" in tables
    assert "ai_jobs" in tables
    assert "ai_usage_ledger" in tables
    assert "extension_projects" in tables
    assert "extension_project_files" in tables
    assert "extension_project_builds" in tables
    assert "application_extension_installations" in tables
    installation_columns = {
        column["name"]
        for column in inspector.get_columns("application_extension_installations")
    }
    assert "configuration" in installation_columns
    assert "application_permission_grants" in tables
    assert "application_kiosk_enrollments" in tables
    assert "application_kiosk_terminals" in tables
    assert "application_event_deliveries" in tables
    assert "application_event_cursors" in tables
    assert "application_secret_references" in tables
    assert "application_connector_bindings" in tables
    assert "application_connector_attempts" in tables
    assert "application_job_states" in tables
    assert "application_sync_checkpoints" in tables
    build_columns = {column["name"] for column in inspector.get_columns("extension_project_builds")}
    assert {"artifact_path", "package_kind", "installed_at"} <= build_columns
    engine.dispose()

    _alembic(database_url, "upgrade", "head")
    _alembic(database_url, "downgrade", "base")

    engine = create_engine(database_url)
    assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
    engine.dispose()
