from datetime import UTC, datetime, timedelta
import hashlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import (
    create_engine,
    select,
)
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import backend.database  # noqa: F401

from backend.config import (
    AppSettings,
    UpdateCatalogSettings,
)
from backend.db.audit_log import AuditLog
from backend.db.base import Base
from backend.db.device import (
    Device,
    DeviceCommand,
)
from backend.db.user import User
from backend.routes.node_updates import (
    _current_node_release_id,
    router,
)
from backend.services.node_release_catalog import (
    NodeReleaseManifest,
    PublishedNodeRelease,
)
from backend.utils import jwt_utils
from backend.utils.auth import hash_password
from backend.utils.db_utils import get_db
from backend.utils.jwt_utils import (
    create_access_token,
)


DEVICE_ID = "dev_" + "a" * 32

TAG = "v0.3.0-beta.25"

ARCHIVE = "3mm-0.3.0-beta.25-" "node-armv6l.tar.gz"

DATA = b"official-node-release"

SHA = hashlib.sha256(DATA).hexdigest()


@pytest.mark.parametrize(
    "outcome,expected",
    [
        (None, None),
        ({"status": "accepted"}, None),
        ({"status": "running"}, None),
        ({"status": "unknown"}, None),
        ({"status": "failed"}, None),
        ({"status": "rolled_back"}, "v0.3.0-beta.24"),
        ({"status": "succeeded", "device_id": "dev_" + "b" * 32}, None),
        ({"status": "not-a-valid-outcome"}, None),
    ],
)
def test_current_release_does_not_fall_back_past_newer_attempt(
    tmp_path, monkeypatch, outcome, expected
):
    _, db, engine, _, _ = make_client(tmp_path, monkeypatch)
    try:
        device = db.scalar(select(Device).where(Device.device_id == DEVICE_ID))
        now = datetime.now(UTC)
        for index, override in enumerate([{"status": "succeeded"}, outcome]):
            operation_id = "nodeupd_" + str(index) * 32
            operation = {
                "schema_version": 1,
                "operation_id": operation_id,
                "device_id": DEVICE_ID,
                "release_id": TAG,
                "archive_sha256": SHA,
                "status": "succeeded",
                "updated_at": now.isoformat(),
                "previous_release_id": "v0.3.0-beta.24",
            }
            if override is not None:
                operation.update(override)
            db.add(
                DeviceCommand(
                    command_id="cmd_" + str(index) * 32,
                    device_id=device.id,
                    command_type="agent.update.apply",
                    payload={},
                    idempotency_key="node-update-apply:" + operation_id,
                    status="succeeded" if index == 0 else "delivered",
                    result={"operation": operation} if override is not None else None,
                    created_at=now + timedelta(seconds=index),
                    expires_at=now + timedelta(minutes=2),
                )
            )
        db.commit()
        assert _current_node_release_id(db, device) == expected
    finally:
        db.close()
        engine.dispose()


def test_check_is_read_only_admin_only_and_rejects_revoked_devices(
    tmp_path, monkeypatch
):
    client, db, engine, admin_token, viewer_token = make_client(tmp_path, monkeypatch)
    try:
        path = f"/api/v1/devices/{DEVICE_ID}/node-updates/check"
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        assert client.get(path).status_code == 401
        assert (
            client.get(
                path, headers={"Authorization": f"Bearer {viewer_token}"}
            ).status_code
            == 403
        )
        response = client.get(path, headers=admin_headers)
        assert response.status_code == 200
        assert response.json()["current_release_id"] is None
        assert response.json()["update_available"] is None
        assert db.scalar(select(DeviceCommand)) is None
        device = db.scalar(select(Device).where(Device.device_id == DEVICE_ID))
        device.revoked_at = datetime.now(UTC)
        db.commit()
        assert client.get(path, headers=admin_headers).status_code == 409
        assert (
            client.get(
                "/api/v1/devices/dev_" + "b" * 32 + "/node-updates/check",
                headers=admin_headers,
            ).status_code
            == 404
        )
    finally:
        db.close()
        engine.dispose()


@pytest.fixture(autouse=True)
def jwt_secret(monkeypatch):
    monkeypatch.setattr(
        jwt_utils,
        "SECRET_KEY",
        "test-only-key-with-at-least-32-bytes",
    )


def release():
    manifest = NodeReleaseManifest.model_validate(
        {
            "schema_version": 1,
            "profile": "node",
            "version": "0.3.0-beta.25",
            "release_id": TAG,
            "commit": "b" * 40,
            "channel": "beta",
            "dependencies": {
                "apt_packages": [],
            },
            "artifacts": [
                {
                    "architecture": "armv6l",
                    "python": "3.13",
                    "filename": ARCHIVE,
                    "sha256": SHA,
                    "size_bytes": len(DATA),
                    "download_url": (
                        "https://github.com/"
                        "ldobranov/3mm/"
                        f"releases/download/{TAG}/"
                        f"{ARCHIVE}"
                    ),
                }
            ],
        }
    )

    return PublishedNodeRelease(
        tag=TAG,
        manifest=manifest,
        artifact=manifest.artifacts[0],
    )


def make_client(
    tmp_path,
    monkeypatch,
    *,
    role="node",
):
    engine = create_engine(
        "sqlite://",
        connect_args={
            "check_same_thread":
                False,
        },
        poolclass=StaticPool,
    )

    Base.metadata.create_all(
        engine
    )

    db = Session(engine)

    admin = User(
        username="admin",
        email="admin@example.com",
        hashed_password=hash_password(
            "password"
        ),
        role="admin",
    )

    viewer = User(
        username="viewer",
        email="viewer@example.com",
        hashed_password=hash_password(
            "password"
        ),
        role="user",
    )

    device = Device(
        device_id=DEVICE_ID,
        display_name="zero",
        role=role,
        protocol_version="1.0",
        approved_at=datetime.now(UTC),
    )

    db.add_all(
        [
            admin,
            viewer,
            device,
        ]
    )

    db.commit()

    settings = AppSettings(
        updates=UpdateCatalogSettings(
            staging_dir=(
                tmp_path
                / "updates"
            ),
            minimum_free_bytes=(
                64
                * 1024
                * 1024
            ),
            max_artifact_bytes=(
                1024
                * 1024
            ),
        )
    )

    monkeypatch.setattr(
        "backend.routes.node_updates.get_settings",
        lambda: settings,
    )

    monkeypatch.setattr(
        (
            "backend.routes.node_updates."
            "find_published_node_release"
        ),
        lambda *_args, **_kwargs:
            release(),
    )

    def download(
        _release,
        destination,
        _settings,
    ):
        destination.write_bytes(
            DATA
        )

        return destination

    monkeypatch.setattr(
        (
            "backend.routes.node_updates."
            "download_published_node_archive"
        ),
        download,
    )

    app = FastAPI()
    app.include_router(router)

    app.dependency_overrides[
        get_db
    ] = lambda: db

    client = TestClient(app)

    return (
        client,
        db,
        engine,
        create_access_token(
            str(admin.id),
            {"role": "admin"},
        ),
        create_access_token(
            str(viewer.id),
            {"role": "user"},
        ),
    )


def test_prepare_is_admin_only_and_queues_exact_agent_request(
    tmp_path,
    monkeypatch,
):
    (
        client,
        db,
        engine,
        admin_token,
        viewer_token,
    ) = make_client(
        tmp_path,
        monkeypatch,
    )

    try:
        forbidden = client.post(
            (
                f"/api/v1/devices/"
                f"{DEVICE_ID}"
                "/node-updates/prepare"
            ),
            headers={
                "Authorization":
                    f"Bearer {viewer_token}"
            },
            json={
                "channel": "beta",
            },
        )

        assert forbidden.status_code == 403

        response = client.post(
            (
                f"/api/v1/devices/"
                f"{DEVICE_ID}"
                "/node-updates/prepare"
            ),
            headers={
                "Authorization":
                    f"Bearer {admin_token}"
            },
            json={
                "channel": "beta",
            },
        )

        assert response.status_code == 202

        body = response.json()

        assert (
            body["prepared"]["device_id"]
            == DEVICE_ID
        )

        assert (
            body["prepared"]["release_id"]
            == TAG
        )

        assert (
            body["prepared"][
                "archive_sha256"
            ]
            == SHA
        )

        command = db.execute(
            select(DeviceCommand)
        ).scalar_one()

        assert (
            command.command_type
            == "agent.update.prepare"
        )

        assert (
            command.payload["device_id"]
            == DEVICE_ID
        )

        assert (
            command.payload["operation_id"]
            == body["prepared"][
                "operation_id"
            ]
        )

        assert (
            command.payload[
                "archive_sha256"
            ]
            == SHA
        )

        assert (
            set(command.payload)
            == {
                "schema_version",
                "operation_id",
                "device_id",
                "release_id",
                "archive_sha256",
                "archive_size_bytes",
            }
        )

        audit = db.execute(
            select(AuditLog)
        ).scalar_one()

        assert (
            audit.action
            == "NODE_UPDATE_PREPARED"
        )

    finally:
        db.close()
        engine.dispose()


def test_prepare_rejects_non_node_device(
    tmp_path,
    monkeypatch,
):
    (
        client,
        db,
        engine,
        admin_token,
        _,
    ) = make_client(
        tmp_path,
        monkeypatch,
        role="hub",
    )

    try:
        response = client.post(
            (
                f"/api/v1/devices/"
                f"{DEVICE_ID}"
                "/node-updates/prepare"
            ),
            headers={
                "Authorization":
                    f"Bearer {admin_token}"
            },
            json={
                "channel": "beta",
            },
        )

        assert response.status_code == 409

        assert (
            db.execute(
                select(DeviceCommand)
            ).scalar_one_or_none()
            is None
        )

    finally:
        db.close()
        engine.dispose()


def test_prepare_request_cannot_supply_url_path_or_shell(
    tmp_path,
    monkeypatch,
):
    (
        client,
        db,
        engine,
        admin_token,
        _,
    ) = make_client(
        tmp_path,
        monkeypatch,
    )

    try:
        for extra in (
            {
                "download_url":
                    "https://evil.example/x"
            },
            {
                "path":
                    "/tmp/release.tar.gz"
            },
            {
                "command":
                    "rm -rf /"
            },
        ):
            response = client.post(
                (
                    f"/api/v1/devices/"
                    f"{DEVICE_ID}"
                    "/node-updates/prepare"
                ),
                headers={
                    "Authorization":
                        f"Bearer {admin_token}"
                },
                json={
                    "channel":
                        "beta",
                    **extra,
                },
            )

            assert (
                response.status_code
                == 422
            )

        assert (
            db.execute(
                select(DeviceCommand)
            ).scalar_one_or_none()
            is None
        )

    finally:
        db.close()
        engine.dispose()


def test_prepare_status_is_durable_from_command_record(
    tmp_path,
    monkeypatch,
):
    (
        client,
        db,
        engine,
        admin_token,
        _,
    ) = make_client(
        tmp_path,
        monkeypatch,
    )

    try:
        prepare_response = client.post(
            (
                f"/api/v1/devices/"
                f"{DEVICE_ID}"
                "/node-updates/prepare"
            ),
            headers={
                "Authorization":
                    f"Bearer {admin_token}"
            },
            json={
                "channel": "beta",
            },
        )

        assert (
            prepare_response.status_code
            == 202
        )

        prepared = (
            prepare_response.json()[
                "prepared"
            ]
        )

        operation_id = (
            prepared["operation_id"]
        )

        status_response = client.get(
            (
                f"/api/v1/devices/"
                f"{DEVICE_ID}"
                f"/node-updates/"
                f"{operation_id}"
            ),
            headers={
                "Authorization":
                    f"Bearer {admin_token}"
            },
        )

        assert (
            status_response.status_code
            == 200
        )

        assert (
            status_response.json()[
                "state"
            ]
            == "queued"
        )

        command = db.execute(
            select(DeviceCommand)
        ).scalar_one()

        command.status = "succeeded"
        command.result = {
            "operation_id":
                operation_id,
            "release_id":
                TAG,
            "archive_sha256":
                SHA,
            "archive_size_bytes":
                len(DATA),
            "prepared_at":
                datetime.now(
                    UTC
                ).isoformat(),
        }

        command.completed_at = (
            datetime.now(UTC)
        )

        db.commit()

        # The status comes from durable Core state,
        # not from an in-memory Agent response.
        status_response = client.get(
            (
                f"/api/v1/devices/"
                f"{DEVICE_ID}"
                f"/node-updates/"
                f"{operation_id}"
            ),
            headers={
                "Authorization":
                    f"Bearer {admin_token}"
            },
        )

        assert (
            status_response.status_code
            == 200
        )

        body = (
            status_response.json()
        )

        assert (
            body["state"]
            == "prepared"
        )

        assert (
            body["command_status"]
            == "succeeded"
        )

        assert (
            body["agent_prepared_at"]
            is not None
        )

    finally:
        db.close()
        engine.dispose()


def test_prepare_status_rejects_corrupt_agent_identity(
    tmp_path,
    monkeypatch,
):
    (
        client,
        db,
        engine,
        admin_token,
        _,
    ) = make_client(
        tmp_path,
        monkeypatch,
    )

    try:
        response = client.post(
            (
                f"/api/v1/devices/"
                f"{DEVICE_ID}"
                "/node-updates/prepare"
            ),
            headers={
                "Authorization":
                    f"Bearer {admin_token}"
            },
            json={
                "channel": "beta",
            },
        )

        operation_id = (
            response.json()[
                "prepared"
            ][
                "operation_id"
            ]
        )

        command = db.execute(
            select(DeviceCommand)
        ).scalar_one()

        command.status = "succeeded"

        command.result = {
            "operation_id":
                operation_id,
            "release_id":
                TAG,
            "archive_sha256":
                "0" * 64,
            "archive_size_bytes":
                len(DATA),
            "prepared_at":
                datetime.now(
                    UTC
                ).isoformat(),
        }

        db.commit()

        status_response = client.get(
            (
                f"/api/v1/devices/"
                f"{DEVICE_ID}"
                f"/node-updates/"
                f"{operation_id}"
            ),
            headers={
                "Authorization":
                    f"Bearer {admin_token}"
            },
        )

        assert (
            status_response.status_code
            == 409
        )

    finally:
        db.close()
        engine.dispose()

def test_check_reports_current_and_latest_node_release(
    tmp_path,
    monkeypatch,
):
    (
        client,
        db,
        engine,
        admin_token,
        _,
    ) = make_client(
        tmp_path,
        monkeypatch,
    )

    try:
        device = db.scalar(
            select(Device).where(
                Device.device_id == DEVICE_ID
            )
        )

        now = datetime.now(UTC)

        db.add(
            DeviceCommand(
                command_id="cmd_" + "c" * 32,
                device_id=device.id,
                command_type="agent.update.apply",
                payload={},
                idempotency_key=(
                    "node-update-apply:"
                    "nodeupd_" + "d" * 32
                ),
                status="succeeded",
                result={
                    "operation": {
                        "schema_version": 1,
                        "operation_id":
                            "nodeupd_" + "d" * 32,
                        "device_id": DEVICE_ID,
                        "release_id": TAG,
                        "archive_sha256": SHA,
                        "status": "succeeded",
                        "updated_at":
                            now.isoformat(),
                        "previous_release_id":
                            "v0.3.0-beta.24",
                        "error_code": None,
                    }
                },
                expires_at=now,
                completed_at=now,
            )
        )

        db.commit()

        response = client.get(
            (
                f"/api/v1/devices/"
                f"{DEVICE_ID}"
                "/node-updates/check"
                "?channel=beta"
            ),
            headers={
                "Authorization":
                    f"Bearer {admin_token}"
            },
        )

        assert response.status_code == 200

        body = response.json()

        assert body == {
            "current_release_id": TAG,
            "latest_release_id": TAG,
            "latest_version":
                "0.3.0-beta.25",
            "channel": "beta",
            "update_available": False,
        }

    finally:
        db.close()
        engine.dispose()

def test_prepare_rejects_release_already_running(
    tmp_path,
    monkeypatch,
):
    (
        client,
        db,
        engine,
        admin_token,
        _,
    ) = make_client(
        tmp_path,
        monkeypatch,
    )

    try:
        device = db.scalar(
            select(Device).where(
                Device.device_id == DEVICE_ID
            )
        )

        now = datetime.now(UTC)

        db.add(
            DeviceCommand(
                command_id="cmd_" + "e" * 32,
                device_id=device.id,
                command_type="agent.update.apply",
                payload={},
                idempotency_key=(
                    "node-update-apply:"
                    "nodeupd_" + "f" * 32
                ),
                status="succeeded",
                result={
                    "operation": {
                        "schema_version": 1,
                        "operation_id":
                            "nodeupd_" + "f" * 32,
                        "device_id": DEVICE_ID,
                        "release_id": TAG,
                        "archive_sha256": SHA,
                        "status": "succeeded",
                        "updated_at":
                            now.isoformat(),
                        "previous_release_id":
                            "v0.3.0-beta.24",
                        "error_code": None,
                    }
                },
                expires_at=now,
                completed_at=now,
            )
        )

        db.commit()

        monkeypatch.setattr(
            (
                "backend.routes.node_updates."
                "download_published_node_archive"
            ),
            lambda *_args, **_kwargs:
                pytest.fail(
                    "same release must not be downloaded"
                ),
        )

        response = client.post(
            (
                f"/api/v1/devices/"
                f"{DEVICE_ID}"
                "/node-updates/prepare"
            ),
            headers={
                "Authorization":
                    f"Bearer {admin_token}"
            },
            json={
                "channel": "beta",
            },
        )

        assert response.status_code == 409

        commands = list(
            db.scalars(
                select(DeviceCommand)
            )
        )

        assert len(commands) == 1
        assert (
            commands[0].command_type
            == "agent.update.apply"
        )

    finally:
        db.close()
        engine.dispose()
