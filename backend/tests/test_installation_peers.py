from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace
import base64
import copy
import uuid

import backend.database
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from cryptography.fernet import Fernet
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, inspect, select, func
from sqlalchemy.orm import Session

from backend.db.base import Base
from backend.db.device import Device, DeviceHeartbeat, DeviceInventorySnapshot
from backend.db.installation_peer import (
    InstallationPeerInbound,
    InstallationPeerOutbound,
    InstallationPeerAudit,
    InstallationPeerNonce,
)
from backend.db.module import ApplicationExtensionInstallation, ModulePackage
from backend.db.user import User
from backend.routes.installation_peers import router
from backend.services import installation_peers as peers
from backend.services.application_platform import ApplicationPlatformServer
from backend.services.installation_identity import installation_identity
from backend.services.installation_projection import installation_projection
from backend.services.module_packages import validate_module_package, ModulePackageError
from backend.tests.test_module_packages import (
    application_definition,
    application_manifest,
    application_package,
)
from backend.utils.db_utils import get_db
from backend.utils.auth_dep import require_admin, require_user
from backend.utils.device_auth import require_device
from deployment.installation_peer_recovery import quarantine_restored_installation_peers
from three_mm_application_sdk import OperationContext
from three_mm_application_sdk import ApplicationPlatformClient, ApplicationPlatformError
from three_mm_protocol.installation_identity import InstallationProofRequestV1
from three_mm_protocol.installation_peer import (
    PeerEnrollmentCompleteV1,
    PeerRequestV1,
    PEER_PREFIX,
    PEER_SCOPE,
    canonical_json,
    request_bytes,
)

MODULE = "org.3mm.workflow-reference"
ORIGIN = "https://center.test"
NODE = "dev_" + "a" * 32


def peer_package():
    definition = application_definition(
        platform_permissions=[
            "installation.peers.receive",
            "installation.peers.enroll",
            "installation.peers.report",
            "installation.status.read",
        ]
    )
    definition["service"]["sdk_version"] = "1.2"
    definition["peer_receiver"] = {
        "bootstrap_operation_id": "peer_enroll",
        "report_operation_id": "peer_report",
    }
    for operation_id, audience, properties in (
        (
            "peer_enroll",
            "installation_bootstrap",
            {
                "binding_id": {"type": "string"},
                "installation_identity": {"type": "object"},
                "requested_scopes": {"type": "array"},
            },
        ),
        ("peer_report", "installation_peer", {"projection": {"type": "object"}}),
    ):
        definition["operations"].append(
            {
                "operation_id": operation_id,
                "kind": "command",
                "audiences": [audience],
                "idempotency": "required",
                "input_schema": {
                    "type": "object",
                    "properties": properties,
                    "required": list(properties),
                    "additionalProperties": False,
                },
            }
        )
    manifest = application_manifest()
    manifest["permissions"] += definition["platform_permissions"]
    return (
        application_package(definition=definition, manifest_value=manifest),
        definition,
        manifest,
    )


@pytest.fixture
def pair(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_SETTINGS_MASTER_KEY", Fernet.generate_key().decode())
    blob, definition, manifest = peer_package()
    path = tmp_path / "peer.zip"
    path.write_bytes(blob)
    validated = validate_module_package(blob)
    cores = []
    for name in ("sender", "receiver"):
        database = tmp_path / f"{name}.db"
        engine = create_engine(
            f"sqlite:///{database.as_posix()}", connect_args={"timeout": 20}
        )

        @event.listens_for(engine, "connect")
        def foreign_keys(connection, _record):
            connection.execute("PRAGMA foreign_keys = ON")

        names = {
            "users",
            "sessions",
            "audit_logs",
            "module_packages",
            "application_extension_installations",
            "core_installation_identity",
            "devices",
            "device_heartbeats",
            "device_inventory_snapshots",
        }
        names.update(
            table.name
            for table in Base.metadata.tables.values()
            if table.name.startswith("installation_peer_")
        )
        Base.metadata.create_all(
            engine,
            tables=[
                table for table in Base.metadata.sorted_tables if table.name in names
            ],
        )
        with Session(engine) as db:
            db.add(
                User(
                    id=1,
                    username="fixture-admin",
                    email="fixture@example.invalid",
                    role="admin",
                )
            )
            package = ModulePackage(
                module_id=MODULE,
                version="1.0.0",
                manifest=manifest,
                sha256=validated.sha256,
                size_bytes=len(blob),
                file_path=str(path),
                registrations=[],
            )
            db.add(package)
            db.flush()
            application = ApplicationExtensionInstallation(
                module_id=MODULE,
                module_package_id=package.id,
                instance_id="a" * 24,
                active_version="1.0.0",
                status="active",
                enabled=True,
                socket_path="unused",
            )
            db.add(application)
            db.commit()
            identity = installation_identity(db).identity
        cores.append(
            SimpleNamespace(engine=engine, database=database, identity=identity)
        )
    sender, receiver = cores
    with Session(receiver.engine) as db:
        peers.configure_origin(db, ORIGIN, user_id=1)
    with Session(sender.engine) as db:
        db.add(
            Device(
                device_id=NODE,
                display_name="Selected",
                role="node",
                protocol_version="1.0",
                approved_at=datetime.now(UTC),
            )
        )
        db.commit()
        application = db.scalar(select(ApplicationExtensionInstallation))
        link = peers.create_outbound(
            db,
            application,
            origin=ORIGIN,
            receiver_identity=receiver.identity,
            target_module_id=MODULE,
            consent={
                "summary_fields": ["core_version", "sdk_version"],
                "node_ids": [NODE],
                "node_fields": ["online", "agent_version", "architecture"],
            },
            user_id=1,
        )
        sender.link_id = link["link_id"]
    captured = []
    monkeypatch.setattr(
        peers,
        "invoke_application",
        lambda *args, **kwargs: captured.append((args, kwargs)) or {},
    )
    app = FastAPI()
    app.include_router(router)

    def receiver_db():
        with Session(receiver.engine) as db:
            yield db

    app.dependency_overrides[get_db] = receiver_db
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(id=1)
    client = TestClient(app, base_url=ORIGIN)

    def transport(origin, path, payload):
        assert origin == ORIGIN
        headers = (
            {"Authorization": "ThreeMM-Peer"}
            if path.endswith(("/report", "/rotate"))
            else {}
        )
        response = client.post(path, json=payload, headers=headers)
        if response.status_code >= 300:
            raise peers.InstallationPeerError(response.json()["detail"])
        return response.json()

    monkeypatch.setattr(peers, "peer_http", transport)
    yield SimpleNamespace(
        sender=sender,
        receiver=receiver,
        client=client,
        transport=transport,
        captured=captured,
        definition=definition,
        manifest=manifest,
        package_path=path,
    )
    client.close()
    for core in cores:
        core.engine.dispose()


def sender_call(pair, function, *args, **kwargs):
    with Session(pair.sender.engine) as db:
        application = db.scalar(select(ApplicationExtensionInstallation))
        return function(db, application, pair.sender.link_id, *args, **kwargs)


def activate_pair(pair):
    result = sender_call(pair, peers.enroll_outbound)
    assert result["state"] == "pending"
    with Session(pair.receiver.engine) as db:
        application = db.scalar(select(ApplicationExtensionInstallation))
        row = db.scalar(select(InstallationPeerInbound))
        binding_id = row.binding_id
        peers.approve_inbound(db, application, binding_id, 1, user_id=1)
    result = sender_call(pair, peers.enroll_outbound)
    assert result["state"] == "active"
    return binding_id


def report_request(pair):
    with Session(pair.sender.engine) as db:
        row = db.get(InstallationPeerOutbound, pair.sender.link_id)
        application = db.scalar(select(ApplicationExtensionInstallation))
        projection = installation_projection(db, application, row.link_id)
        request = peers.signed_outbound_request(
            db,
            row,
            PEER_PREFIX + "/report",
            {
                "report_id": "report_" + uuid.uuid4().hex,
                "projection": projection.model_dump(mode="json"),
            },
        )
        db.commit()
        return request


def test_dual_approval_restart_report_and_machine_context(pair):
    binding_id = activate_pair(pair)
    assert pair.sender.identity != pair.receiver.identity
    result = sender_call(pair, peers.report_outbound, "report_" + "a" * 32)
    assert result["status"] == "accepted"
    args, kwargs = pair.captured[-1]
    assert (
        args[3] == "peer_report" and kwargs["required_audience"] == "installation_peer"
    )
    context = OperationContext.from_platform(args[5])
    assert (
        context.user_id is None
        and context.machine.installation_id == pair.sender.identity.installation_id
    )
    assert context.machine.binding_id == binding_id and context.machine.scopes == (
        PEER_SCOPE,
    )
    with Session(pair.receiver.engine) as db:
        audit = list(db.scalars(select(InstallationPeerAudit)))
        assert any(item.actor_kind == "installation" for item in audit)
        assert any(item.actor_kind == "user" for item in audit)
        assert db.scalar(select(func.count()).select_from(InstallationPeerInbound)) == 1


@pytest.mark.parametrize("location", ["start", "complete"])
def test_lost_response_retries_same_durable_enrollment_without_extra_credential(
    pair, location
):
    failed = False

    def lose_response(origin, path, payload):
        nonlocal failed
        result = pair.transport(origin, path, payload)
        if path.endswith("/" + location) and not failed:
            failed = True
            raise peers.InstallationPeerError("fixture response lost")
        return result

    with pytest.raises(peers.InstallationPeerError, match="lost"):
        sender_call(pair, peers.enroll_outbound, transport=lose_response)
    activate_pair(pair)
    with Session(pair.receiver.engine) as db:
        row = db.scalar(select(InstallationPeerInbound))
        assert row.generation == 1
        assert db.scalar(select(func.count()).select_from(InstallationPeerInbound)) == 1


def test_concurrent_completion_is_idempotent_and_revoke_fences_delayed_accept(pair):
    sender_call(pair, peers.enroll_outbound)
    with Session(pair.sender.engine) as db:
        complete = db.get(
            InstallationPeerOutbound, pair.sender.link_id
        ).complete_request
    with Session(pair.receiver.engine) as db:
        binding_id = db.scalar(select(InstallationPeerInbound)).binding_id

    def approve(_):
        with Session(pair.receiver.engine) as db:
            app = db.scalar(select(ApplicationExtensionInstallation))
            return peers.approve_inbound(db, app, binding_id, 1)["credential"]

    with ThreadPoolExecutor(max_workers=3) as workers:
        results = list(workers.map(approve, range(3)))
    assert results[0] == results[1] == results[2]
    with Session(pair.receiver.engine) as db:
        app = db.scalar(select(ApplicationExtensionInstallation))
        peers.revoke_peer(db, app, binding_id, "inbound", user_id=1)
        with pytest.raises(peers.InstallationPeerError):
            peers.approve_inbound(db, app, binding_id, 1)
    assert (
        pair.client.post(
            PEER_PREFIX + "/enrollments/complete", json=complete
        ).status_code
        == 409
    )
    with Session(pair.receiver.engine) as db:
        assert db.get(InstallationPeerInbound, binding_id).state == "revoked"


@pytest.mark.parametrize(
    "failure", ["signature", "origin", "resource", "receiver_key", "expiry"]
)
def test_spoofed_enrollment_never_gains_approval_or_credential(pair, failure):
    with Session(pair.sender.engine) as db:
        row = db.get(InstallationPeerOutbound, pair.sender.link_id)
        start = copy.deepcopy(row.start_request)
    if failure == "signature":
        start["signature"] = base64.b64encode(b"x" * 64).decode()
    else:
        changes = {
            "origin": ("audience", "https://other.test"),
            "resource": ("resource", "peer.other"),
            "receiver_key": ("receiver_key_id", "0" * 64),
            "expiry": (
                "expires_at",
                (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
            ),
        }
        field, value = changes[failure]
        start["receiver_challenge"][field] = value
    assert (
        pair.client.post(PEER_PREFIX + "/enrollments/start", json=start).status_code
        == 409
    )
    with Session(pair.receiver.engine) as db:
        assert db.scalar(select(func.count()).select_from(InstallationPeerInbound)) == 0


def test_expired_sender_challenge_denies_first_completion(pair):
    with Session(pair.sender.engine) as db:
        start = db.get(InstallationPeerOutbound, pair.sender.link_id).start_request
    response = pair.transport(ORIGIN, PEER_PREFIX + "/enrollments/start", start)
    from backend.services.installation_identity import prove_installation_identity

    with Session(pair.sender.engine) as db:
        proof = prove_installation_identity(db, response["sender_challenge"])
    complete = PeerEnrollmentCompleteV1(
        binding_id=response["binding_id"], sender_proof=proof
    )
    with Session(pair.receiver.engine) as db:
        with pytest.raises(ValueError, match="expired"):
            peers.enrollment_complete(
                db,
                complete,
                origin=ORIGIN,
                now=datetime.now(UTC) + timedelta(minutes=3),
            )
        db.rollback()
        assert (
            db.get(InstallationPeerInbound, response["binding_id"]).state
            == "challenged"
        )


def test_nonce_replay_is_rejected_across_sessions_and_signature_path_body_are_bound(
    pair,
):
    activate_pair(pair)
    request = report_request(pair)
    assert (
        pair.transport(ORIGIN, request.path, request.model_dump(mode="json"))["status"]
        == "accepted"
    )
    response = pair.client.post(
        request.path,
        json=request.model_dump(mode="json"),
        headers={"Authorization": "ThreeMM-Peer"},
    )
    assert response.status_code == 409 and "consumed" in response.json()["detail"]
    for path in (PEER_PREFIX + "/rotate", PEER_PREFIX + "/report"):
        changed = report_request(pair).model_dump(mode="json")
        if path.endswith("/report"):
            changed["payload"]["projection"][
                "installation_id"
            ] = pair.receiver.identity.installation_id
        response = pair.client.post(
            path, json=changed, headers={"Authorization": "ThreeMM-Peer"}
        )
        assert response.status_code == 409


def test_rotation_lost_response_retry_and_old_generation_denial(pair):
    activate_pair(pair)
    old_request = report_request(pair)

    def lose_response(origin, path, payload):
        pair.transport(origin, path, payload)
        raise peers.InstallationPeerError("fixture rotation response lost")

    with pytest.raises(peers.InstallationPeerError):
        sender_call(pair, peers.rotate_outbound, transport=lose_response)
    sender_call(pair, peers.rotate_outbound)
    with Session(pair.receiver.engine) as db:
        assert db.scalar(select(InstallationPeerInbound)).generation == 2
    assert (
        pair.client.post(
            old_request.path,
            json=old_request.model_dump(mode="json"),
            headers={"Authorization": "ThreeMM-Peer"},
        ).status_code
        == 409
    )
    assert (
        sender_call(pair, peers.report_outbound, "report_" + "b" * 32)["status"]
        == "accepted"
    )


def test_revoked_rotation_receipt_cannot_restore_trust(pair):
    binding_id = activate_pair(pair)

    def lose_response(origin, path, payload):
        result = pair.transport(origin, path, payload)
        with Session(pair.receiver.engine) as db:
            app = db.scalar(select(ApplicationExtensionInstallation))
            peers.revoke_peer(db, app, binding_id, "inbound", user_id=1)
        raise peers.InstallationPeerError("lost after revoke")

    with pytest.raises(peers.InstallationPeerError):
        sender_call(pair, peers.rotate_outbound, transport=lose_response)
    with pytest.raises(peers.InstallationPeerError):
        sender_call(pair, peers.rotate_outbound)


@pytest.mark.parametrize("phase", ["enroll", "report", "rotate"])
def test_local_withdrawal_wins_delayed_network_response(pair, phase):
    if phase != "enroll":
        activate_pair(pair)

    def withdraw(origin, path, payload):
        result = pair.transport(origin, path, payload)
        with Session(pair.sender.engine) as db:
            app = db.scalar(select(ApplicationExtensionInstallation))
            peers.revoke_peer(db, app, pair.sender.link_id, "outbound", user_id=1)
        return result

    function = {
        "enroll": peers.enroll_outbound,
        "report": peers.report_outbound,
        "rotate": peers.rotate_outbound,
    }[phase]
    args = ["report_" + "c" * 32] if phase == "report" else []
    with pytest.raises(peers.InstallationPeerError):
        sender_call(pair, function, *args, transport=withdraw)
    with Session(pair.sender.engine) as db:
        row = db.get(InstallationPeerOutbound, pair.sender.link_id)
        assert row.state == "revoked" and row.credential is None


def test_consent_projection_unknowns_source_times_selection_and_no_secrets(pair):
    activate_pair(pair)
    with Session(pair.sender.engine) as db:
        device = db.scalar(select(Device).where(Device.device_id == NODE))
        before = datetime.now(UTC) - timedelta(minutes=10)
        db.add(
            DeviceHeartbeat(
                device_id=device.id,
                protocol_version="1.0",
                payload={
                    "sent_at": before.isoformat(),
                    "secret": "fixture-secret-never-export",
                },
                received_at=before,
            )
        )
        db.add(
            DeviceInventorySnapshot(
                device_id=device.id,
                inventory={
                    "architecture": "armv6l",
                    "collected_at": before.isoformat(),
                    "credential": "fixture-secret-never-export",
                    "gpio": {"pin": 17},
                },
                received_at=before,
            )
        )
        db.add(
            Device(
                device_id="dev_" + "f" * 32,
                display_name="Not consented",
                role="node",
                protocol_version="1.0",
                approved_at=before,
            )
        )
        db.commit()
        app = db.scalar(select(ApplicationExtensionInstallation))
        result = installation_projection(db, app, pair.sender.link_id).model_dump(
            mode="json"
        )
        assert result["summary"]["sdk_version"]["value"] == "1.2"
        assert [node["device_id"] for node in result["nodes"]] == [NODE]
        fields = result["nodes"][0]["fields"]
        assert set(fields) == {"online", "agent_version", "architecture"}
        assert fields["online"]["value"] is False
        assert fields["architecture"]["value"] == "armv6l"
        assert fields["architecture"]["received_at"] is not None and fields[
            "architecture"
        ]["revision"].startswith("inventory:")
        assert (
            fields["agent_version"]["status"] == "unknown"
            and fields["agent_version"]["value"] is None
        )
        encoded = canonical_json(result)
        for forbidden in (
            b"credential",
            b"fixture-secret",
            b"gpio",
            b"Not consented",
            b"desired_state",
        ):
            assert forbidden not in encoded


@pytest.mark.parametrize(
    "failure", ["withdrawn", "disabled", "other_module", "unknown_device"]
)
def test_projection_refuses_unconsented_or_disabled_source(pair, failure):
    with Session(pair.sender.engine) as db:
        app = db.scalar(select(ApplicationExtensionInstallation))
        if failure == "unknown_device":
            with pytest.raises(peers.InstallationPeerError, match="registered"):
                peers.create_outbound(
                    db,
                    app,
                    origin=ORIGIN,
                    receiver_identity=pair.receiver.identity,
                    target_module_id=MODULE,
                    consent={
                        "node_ids": ["dev_" + "c" * 32],
                        "node_fields": ["online"],
                    },
                    user_id=1,
                )
            return
        if failure == "withdrawn":
            peers.revoke_peer(db, app, pair.sender.link_id, "outbound", user_id=1)
        elif failure == "disabled":
            app.enabled = False
        else:
            app.module_id = "org.3mm.other"
        db.commit()
        with pytest.raises(ValueError):
            installation_projection(db, app, pair.sender.link_id)


def test_missing_inventory_and_heartbeat_are_unknown_not_fake_offline(pair):
    with Session(pair.sender.engine) as db:
        app = db.scalar(select(ApplicationExtensionInstallation))
        projection = installation_projection(db, app, pair.sender.link_id)
        assert all(
            item.status == "unknown" and item.value is None
            for item in projection.nodes[0].fields.values()
        )


def test_http_and_hostile_forwarded_origin_rejected_and_no_human_agent_auth_reuse(pair):
    with Session(pair.sender.engine) as db:
        start = db.get(InstallationPeerOutbound, pair.sender.link_id).start_request
    for url, headers in (
        ("http://center.test", {}),
        ("http://center.test", {"X-Forwarded-Proto": "https"}),
        ("https://other.test", {}),
    ):
        response = pair.client.post(
            url + PEER_PREFIX + "/enrollments/start", json=start, headers=headers
        )
        assert response.status_code == 403
    for authorization in ("Bearer fixture-admin-token", "Device fixture-agent-token"):
        response = pair.client.post(
            PEER_PREFIX + "/enrollments/start",
            json=start,
            headers={"Authorization": authorization},
        )
        assert response.status_code == 401
    with Session(pair.receiver.engine) as db:
        for dependency in (require_user, require_device):
            with pytest.raises(HTTPException) as error:
                dependency(authorization="ThreeMM-Peer", db=db)
            assert error.value.status_code == 401


def test_permissions_and_package_integrity_gate_before_projection_or_network(
    pair, monkeypatch
):
    calls = []
    monkeypatch.setattr(peers, "peer_http", lambda *_args: calls.append(True))
    with Session(pair.sender.engine) as db:
        app = db.scalar(select(ApplicationExtensionInstallation))
        package = db.get(ModulePackage, app.module_package_id)
        package.sha256 = "0" * 64
        db.commit()
        server = ApplicationPlatformServer(Path("unused"), Path("unused"))
        for action in (
            "installation.status.get",
            "installation.peers.enroll",
            "installation.peers.approve",
        ):
            with pytest.raises(RuntimeError):
                server._dispatch(
                    db, app, {"action": action, "link_id": pair.sender.link_id}
                )
        assert calls == []


def test_uninstall_keeps_revoked_tombstone_and_restore_quarantines_trust(pair):
    binding_id = activate_pair(pair)
    quarantine_restored_installation_peers(pair.sender.database)
    quarantine_restored_installation_peers(pair.receiver.database)
    with Session(pair.sender.engine) as db:
        assert installation_identity(db).identity == pair.sender.identity
        assert db.get(InstallationPeerOutbound, pair.sender.link_id).state == "revoked"
    with Session(pair.receiver.engine) as db:
        assert installation_identity(db).identity == pair.receiver.identity
        assert db.get(InstallationPeerInbound, binding_id).state == "revoked"
        assert db.get(InstallationPeerInbound, binding_id).credential is None
        assert db.scalar(select(func.count()).select_from(InstallationPeerNonce)) == 0
        peers.invalidate_application_peers(db, MODULE)
        db.commit()
        assert db.get(InstallationPeerInbound, binding_id).state == "revoked"


def test_peer_migration_upgrade_downgrade_and_legacy_baseline_exclusion(tmp_path):
    migration = import_module(
        "backend.alembic.versions.526ab1c2d3e4_installation_peers"
    )
    baseline = import_module(
        "backend.alembic.versions.0f1e2d3c4b5a_legacy_schema_baseline"
    )
    engine = create_engine(f"sqlite:///{(tmp_path / 'migration.db').as_posix()}")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE existing_state (value TEXT)")
            connection.exec_driver_sql(
                "INSERT INTO existing_state VALUES ('preserved')"
            )
            original = migration.op
            migration.op = Operations(MigrationContext.configure(connection))
            try:
                migration.upgrade()
                tables = set(inspect(connection).get_table_names())
                assert all(
                    table in tables and table in baseline.POST_BASELINE_TABLES
                    for table in (
                        "installation_peer_origin",
                        "installation_peer_inbound",
                        "installation_peer_outbound",
                        "installation_peer_nonces",
                        "installation_peer_audit",
                    )
                )
                assert (
                    connection.exec_driver_sql(
                        "SELECT value FROM existing_state"
                    ).scalar_one()
                    == "preserved"
                )
                migration.downgrade()
                assert not any(
                    table.startswith("installation_peer_")
                    for table in inspect(connection).get_table_names()
                )
            finally:
                migration.op = original
    finally:
        engine.dispose()


def test_concurrent_proof_completion_consumes_once(pair):
    with Session(pair.sender.engine) as db:
        start = db.get(InstallationPeerOutbound, pair.sender.link_id).start_request
    response = pair.transport(ORIGIN, PEER_PREFIX + "/enrollments/start", start)
    from backend.services.installation_identity import prove_installation_identity

    with Session(pair.sender.engine) as db:
        proof = prove_installation_identity(db, response["sender_challenge"])
    complete = PeerEnrollmentCompleteV1(
        binding_id=response["binding_id"], sender_proof=proof
    )

    def finish(_):
        with Session(pair.receiver.engine) as db:
            return peers.enrollment_complete(db, complete, origin=ORIGIN).model_dump(
                mode="json"
            )

    with ThreadPoolExecutor(max_workers=3) as workers:
        results = list(workers.map(finish, range(3)))
    assert results[0] == results[1] == results[2]
    with Session(pair.receiver.engine) as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(InstallationPeerAudit)
                .where(
                    InstallationPeerAudit.action == "INSTALLATION_PEER_PROOF_ACCEPTED"
                )
            )
            == 1
        )


def test_expired_approval_and_request_or_credential_never_dispatch(pair):
    sender_call(pair, peers.enroll_outbound)
    with Session(pair.receiver.engine) as db:
        app = db.scalar(select(ApplicationExtensionInstallation))
        row = db.scalar(select(InstallationPeerInbound))
        with pytest.raises(peers.InstallationPeerError, match="expired"):
            peers.approve_inbound(
                db,
                app,
                row.binding_id,
                1,
                now=datetime.now(UTC) + timedelta(minutes=16),
            )
    activate_pair(pair)
    request = report_request(pair)
    for delta in (timedelta(minutes=3), timedelta(days=2)):
        with Session(pair.receiver.engine) as db:
            before = len(pair.captured)
            with pytest.raises((peers.InstallationPeerError, ValueError)):
                peers.receive_report(
                    db,
                    request,
                    origin=ORIGIN,
                    path=request.path,
                    now=datetime.now(UTC) + delta,
                )
            assert len(pair.captured) == before


def test_report_loss_preserves_snapshot_and_report_id_and_cached_receipt(pair):
    activate_pair(pair)
    report_id = "report_" + "d" * 32
    sent = []

    def lose_response(origin, path, payload):
        sent.append(copy.deepcopy(payload))
        pair.transport(origin, path, payload)
        raise peers.InstallationPeerError("fixture lost report")

    with pytest.raises(peers.InstallationPeerError):
        sender_call(pair, peers.report_outbound, report_id, transport=lose_response)
    with pytest.raises(peers.InstallationPeerError, match="outstanding"):
        sender_call(pair, peers.report_outbound, "report_" + "e" * 32)

    def record(origin, path, payload):
        sent.append(copy.deepcopy(payload))
        return pair.transport(origin, path, payload)

    first = sender_call(pair, peers.report_outbound, report_id, transport=record)
    assert sent[0]["payload"] == sent[1]["payload"]
    assert sent[0]["nonce"] != sent[1]["nonce"]

    def must_not_send(*_args):
        pytest.fail("The latest acknowledged report must return its durable receipt")

    assert (
        sender_call(pair, peers.report_outbound, report_id, transport=must_not_send)
        == first
    )


def test_consent_field_withdrawal_filters_before_serialization_and_clears_pending_snapshot(
    pair,
):
    activate_pair(pair)
    sender_call(pair, peers.report_outbound, "report_" + "f" * 32)
    with Session(pair.sender.engine) as db:
        app = db.scalar(select(ApplicationExtensionInstallation))
        row = db.get(InstallationPeerOutbound, pair.sender.link_id)
        assert row.report_projection is not None
        peers.update_consent(
            db, app, row.link_id, {"summary_fields": ["core_version"]}, 1, user_id=1
        )
        projection = installation_projection(db, app, row.link_id)
        assert projection.nodes == () and set(projection.summary) == {"core_version"}
        assert projection.consent_revision == 2
        assert row.report_projection is None and row.report_id is None
        with pytest.raises(peers.InstallationPeerError, match="revision"):
            peers.update_consent(db, app, row.link_id, {}, 1, user_id=1)


def test_delayed_pending_response_cannot_downgrade_active_peer(pair):
    def delayed_response(origin, path, payload):
        pending = pair.transport(origin, path, payload)
        if path.endswith("/complete"):
            with Session(pair.receiver.engine) as db:
                application = db.scalar(select(ApplicationExtensionInstallation))
                peers.approve_inbound(
                    db, application, pending["binding_id"], 1, user_id=1
                )
            assert sender_call(pair, peers.enroll_outbound)["state"] == "active"
        return pending

    with pytest.raises(peers.InstallationPeerError, match="cannot downgrade"):
        sender_call(pair, peers.enroll_outbound, transport=delayed_response)
    with Session(pair.sender.engine) as db:
        row = db.get(InstallationPeerOutbound, pair.sender.link_id)
        assert row.state == "active" and row.credential is not None


def test_signed_sdk_projection_list_and_withdrawal_use_platform_boundary(
    pair, tmp_path, monkeypatch
):
    from backend.tests.test_installation_identity_platform import MemoryConnection

    activate_pair(pair)
    key_root = tmp_path / "platform-keys"
    key_root.mkdir()
    instance_id = "a" * 24
    secret = b"s" * 32
    (key_root / f"{instance_id}.key").write_bytes(secret)
    server = ApplicationPlatformServer(tmp_path / "platform.sock", key_root)
    monkeypatch.setattr(
        backend.database, "SessionLocal", lambda: Session(pair.sender.engine)
    )

    class ClientSocket:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def settimeout(self, _timeout):
            pass

        def connect(self, _path):
            pass

        def sendall(self, message):
            connection = MemoryConnection(message)
            server._handle(connection)
            self.response = connection.response

        def recv(self, _limit):
            result, self.response = self.response, b""
            return result

    monkeypatch.setattr(
        "three_mm_application_sdk.socket.socket", lambda *_args: ClientSocket()
    )
    monkeypatch.setattr("three_mm_application_sdk.socket.AF_UNIX", 1, raising=False)
    client = ApplicationPlatformClient(server.socket_path, instance_id, secret)
    projection = client.get_installation_status(pair.sender.link_id)
    assert projection["installation_id"] == pair.sender.identity.installation_id
    assert list(projection["summary"]) == ["core_version", "sdk_version"]
    assert client.list_installation_peers()["outbound"][0]["state"] == "active"
    assert (
        client.revoke_installation_peer(pair.sender.link_id, direction="outbound")[
            "state"
        ]
        == "revoked"
    )
    with pytest.raises(ApplicationPlatformError, match="withdrawn"):
        client.get_installation_status(pair.sender.link_id)


def test_same_installation_id_different_key_requires_explicit_review(pair):
    activate_pair(pair)
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    import hashlib
    from three_mm_protocol.installation_peer import (
        PeerEnrollmentStartV1,
        enrollment_start_bytes,
    )

    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    with Session(pair.sender.engine) as db:
        value = copy.deepcopy(
            db.get(InstallationPeerOutbound, pair.sender.link_id).start_request
        )
    value["sender"]["public_key"] = base64.b64encode(public).decode()
    value["sender"]["key_id"] = hashlib.sha256(public).hexdigest()
    value["receiver_challenge"]["receiver_key_id"] = value["sender"]["key_id"]
    start = PeerEnrollmentStartV1.model_validate(value)
    start = start.model_copy(
        update={
            "signature": base64.b64encode(
                key.sign(enrollment_start_bytes(start))
            ).decode()
        }
    )
    response = pair.client.post(
        PEER_PREFIX + "/enrollments/start", json=start.model_dump(mode="json")
    )
    assert (
        response.status_code == 409
        and "another key binding" in response.json()["detail"]
    )
