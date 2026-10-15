"""Actual Core-UID metadata worker and actual non-root resumption; disposable only."""

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from backend.tests.test_application_relational_production import (
    ROOT_ONLY,
    absent_paths,
    initial,
    managed_installed,
    production,
    request,
    source_installed,
    source_subject,
    stopped,
)
from three_mm_application_sdk.relational_wire import canonical
from three_mm_runtime import application_relational_preparation as preparation
from three_mm_runtime import update_helper

pytestmark = [
    ROOT_ONLY,
    pytest.mark.skipif(
        os.name != "posix", reason="Actual Core/app process credentials"
    ),
]


def test_real_core_uid_controls_recovery_and_one_shot_resume(production, monkeypatch):
    state = production
    database = Path(state.engine.url.database)
    environment = dict(
        os.environ,
        DATABASE_URL=f"sqlite:///{database}",
        UPLOADS_DIR=str(state.root),
        THREE_MM_AUTHORITY_REVIEW_KEY_DIR=str(state.key_directory),
        THREE_MM_APPLICATION_ROOT=str(state.runtime),
        PYTHONDONTWRITEBYTECODE="1",
    )

    def runner(arguments, **kwargs):
        frame = json.loads(kwargs["input"])
        state.frames.append(frame["action"])
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "backend.services.application_relational_admin_worker",
                "--core-uid",
                "1202",
                "--database",
                str(database),
                "--application-root",
                str(state.runtime),
            ],
            user=1202,
            group=1203,
            extra_groups=(),
            env=environment,
            **kwargs,
        )

    state.metadata._run = runner

    def denied(*a, **kw):
        raise PermissionError("injected pre-exec UID transition refusal")

    with monkeypatch.context() as patch:
        patch.setattr(preparation, "run_business_migrations", denied)
        result = update_helper._handle_request(
            request(state), relational_peer_uid=1202, **state.arguments
        )
        assert result == {"ok": False, "error": "relational_preparation_unconfirmed"}
    assert not state.database.exists()
    secret = state.key_path.read_bytes()

    # Diagnostic IDs only; real Core worker/CLI verifies all seals before effects.
    with state.engine.connect() as db:
        rows = [
            json.loads(row[0])
            for row in db.exec_driver_sql(
                "SELECT payload FROM application_authority_actions"
            ).fetchall()
        ]
    source = next(
        row for row in rows if row["data"]["operation"] == "relational_prepare_migrated"
    )
    namespace = next(
        row
        for row in rows
        if row["data"]["operation"] == "relational_prepare_namespace"
    )
    namespace_id = namespace["data"]["result"]["ticket"]["preparation_id"]
    source_id = source["data"]["result"]["ticket"]["preparation_id"]

    def cli(arguments):
        process = subprocess.run(
            [
                sys.executable,
                "-m",
                "backend.services.application_authority_admin",
                *arguments,
            ],
            input=state.token.encode() + b"\n",
            capture_output=True,
            timeout=45,
            start_new_session=True,
            user=1202,
            group=1203,
            extra_groups=(),
            env=environment,
        )
        assert process.returncode == 0, process.stderr.decode()
        assert state.token.encode() not in process.stdout + process.stderr
        return json.loads(process.stdout)

    inspected = cli(
        [
            "inspect-relational-preparation",
            "--installation-id",
            "1",
            "--source-preparation-id",
            source_id,
            "--source-namespace-id",
            namespace_id,
            "--expected-grant-record-revision",
            state.expected_grant,
        ]
    )
    assert inspected["state"] == "execution_unconfirmed"
    assert inspected["source_revision"] == source["revision"]
    payload = {
        "action": "recover_application_relational_preparation",
        "installation_id": 1,
        "actor_token": state.token,
        "source_preparation_id": source_id,
        "source_namespace_id": namespace_id,
        "expected_preparation_revision": inspected["source_revision"],
        "expected_grant_record_revision": state.expected_grant,
        "request_id": "e" * 32,
        "confirm_restored_empty_checkpoint": True,
    }
    state.frames.clear()
    response = update_helper._handle_request(
        payload, relational_peer_uid=1202, **state.arguments
    )
    assert response["status"] == "restored_empty_not_started", (response, state.frames)
    assert (
        state.frames
        == ["inspect_empty_preparation", "issue_empty_preparation_recovery"]
        + ["empty_preparation_recovery_checkpoint"] * 4
    )
    assert not state.database.exists() and state.key_path.read_bytes() == secret
    assert secret.hex().encode() not in canonical(response)
    inspected_recovery = cli(
        [
            "inspect-relational-preparation-recovery",
            "--installation-id",
            "1",
            "--source-recovery-id",
            "e" * 32,
        ]
    )
    assert (
        inspected_recovery["state"] == "confirmed"
        and not inspected_recovery["resumption_reserved"]
    )
    state.frames.clear()
    resumed = update_helper._handle_request(
        {
            "action": "resume_application_relational_preparation",
            "installation_id": 1,
            "actor_token": state.token,
            "source_recovery_id": "e" * 32,
            "expected_recovery_revision": inspected_recovery["source_revision"],
            "expected_grant_record_revision": state.expected_grant,
            "request_id": "f" * 32,
            "confirm_owned_business_migrations": True,
        },
        relational_peer_uid=1202,
        **state.arguments,
    )
    assert resumed["status"] == "prepared_not_started", (resumed, state.frames)
    assert (
        state.frames
        == ["inspect_preparation_resumption", "issue_preparation_resumption"]
        + ["checkpoint"] * 5
    )
    assert state.database.stat().st_uid == 1200
    with sqlite3.connect(state.database) as db:
        assert db.execute(
            "SELECT revision FROM three_mm_schema_migrations"
        ).fetchall() == [("0001",), ("0002",)]
    with state.engine.connect() as db:
        assert db.exec_driver_sql(
            "SELECT enabled,status FROM application_extension_installations WHERE id=1"
        ).fetchone() == (0, "disabled")
    assert all(call[0] == "stop" for call in state.calls)
    assert state.key_path.read_bytes() == secret
