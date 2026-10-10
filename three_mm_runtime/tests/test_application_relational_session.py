"""Prepared-reader + actual Unix metadata worker; NOT production activation.

The fixture writes lifecycle/DB state explicitly. No preparation coordinator,
package migration import or grant is inferred from this test setup. Root tests
exercise production UID 0; unprivileged CI uses its own disposable owner policy.
"""

import hashlib
import json
import os
import socket
import sqlite3
import tempfile
import time
import uuid
from pathlib import Path

import pytest

from three_mm_application_sdk import ApplicationMigration, ApplicationStorage
from three_mm_application_sdk.relational_receipts import _prepare_receipt_metadata
from three_mm_application_sdk.relational_wire import (
    canonical,
    profile_digest,
    sign_metadata,
)
from three_mm_protocol.application_extension import ApplicationRelationalStorageV1
from three_mm_protocol.tests.test_application_relational_storage import (
    relational_request,
)
from three_mm_runtime import application_relational_session as runtime
from three_mm_runtime.application_transport import sign_message, verify_message

pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="POSIX protected metadata/Unix socket/boot clock"
)
SECRET = b"t" * 32


def make_prepared(
    root,
    metadata,
    *,
    wheel=b"never imported",
    owner="a" * 64,
    generation="b" * 32,
    lineage="c" * 32,
):
    for directory in (
        root.parent,
        root,
        root / "data",
        root / "run",
        root / "releases",
        root / "releases" / metadata["sha256"],
    ):
        directory.mkdir(parents=True, exist_ok=True)
        directory.chmod(0o750)
    (root / "active.json").write_bytes(canonical(metadata))
    (root / "active.json").chmod(0o640)
    (root / "releases" / metadata["sha256"] / "service.whl").write_bytes(wheel)
    (root / "releases" / metadata["sha256"] / "service.whl").chmod(0o440)
    revision = metadata["storage"]["schema_revision"]
    legacy = ApplicationStorage(root / "data")
    legacy.migrate(
        [
            ApplicationMigration(
                revision, lambda db: db.execute("CREATE TABLE example(value INTEGER)")
            )
        ],
        revision,
    )
    with sqlite3.connect(legacy.database_path) as db:
        db.execute("BEGIN IMMEDIATE")
        receipts = _prepare_receipt_metadata(
            db, database_lineage=lineage, schema_revision=revision, secret=SECRET
        )
    db.close()
    record = sign_metadata(
        SECRET,
        "lifecycle",
        {
            "version": 1,
            "instance_id": metadata["instance_id"],
            "lifecycle_id": uuid.uuid4().hex,
            "database_lineage": lineage,
            "owner_sha256": owner,
            "package_sha256": metadata["sha256"],
            "service_sha256": hashlib.sha256(wheel).hexdigest(),
            "configuration_sha256": hashlib.sha256(
                canonical(metadata["configuration"])
            ).hexdigest(),
            "schema_revision": revision,
            "profile_sha256": profile_digest(
                ApplicationRelationalStorageV1.model_validate(
                    metadata["storage"]["relational"]
                ),
                revision,
            ),
            "recovery_generation": generation,
        },
    )
    (root / "relational.json").write_bytes(canonical(record))
    (root / "relational.json").chmod(0o640)
    return record, receipts


@pytest.fixture
def prepared(monkeypatch):
    assert runtime._LIFECYCLE_UID == 0
    monkeypatch.setattr(runtime, "_LIFECYCLE_UID", os.getuid())
    with tempfile.TemporaryDirectory(prefix="3mm-rs-") as directory:
        root = Path(directory) / ("d" * 24)
        metadata = {
            "instance_id": root.name,
            "sha256": "e" * 64,
            "wheel": "service.whl",
            "configuration": {"label": "example"},
            "storage": {"schema_revision": "0001", "relational": relational_request()},
        }
        record, receipts = make_prepared(root, metadata)
        yield root, metadata, record, receipts


def ticket(session, **changes):
    hello = runtime._call_host_metadata(session.path, SECRET)
    now = hello["clock_ms"]
    return sign_metadata(
        SECRET,
        "invocation",
        {
            "version": 1,
            "invocation_id": uuid.uuid4().hex,
            "operation_id": "inspect",
            "instance_id": hello["lifecycle"]["instance_id"],
            "runtime_nonce": hello["runtime_nonce"],
            "boot_id": hello["boot_id"],
            "lifecycle_sha256": hashlib.sha256(
                canonical(hello["lifecycle"])
            ).hexdigest(),
            "binding_sha256": "f" * 64,
            "authority_epoch": "f" * 32,
            "recovery_generation": hello["lifecycle"]["recovery_generation"],
            "started_at_ms": now,
            "deadline_ms": now + 5000,
            **changes,
        },
    )


def test_readiness_and_real_socket_never_migrate_or_query_business_data(
    prepared, monkeypatch
):
    root, _, record, _ = prepared
    before = (root / "data/state.sqlite3").read_bytes()
    monkeypatch.setattr(
        ApplicationStorage,
        "migrate",
        lambda *_: pytest.fail("Normal startup invoked migrations"),
    )
    with runtime._RelationalHostSession(root, SECRET) as session:
        hello = runtime._call_host_metadata(session.path, SECRET)
        assert hello["lifecycle"] == record and hello["invocation"] is None
        assert session.path.stat().st_mode & 0o777 == 0o660
        current = ticket(session)
        with session.invocation(current, operation_id="inspect"):
            assert (
                runtime._call_host_metadata(session.path, SECRET)["invocation"]
                == current
            )
            assert (
                session._permit_expectations("a" * 32, "write")["database_lineage"]
                == record["database_lineage"]
            )
        assert runtime._call_host_metadata(session.path, SECRET)["invocation"] is None
        with pytest.raises(ValueError, match="consumed"):
            with session.invocation(current, operation_id="inspect"):
                pytest.fail("Replayed invocation")
    assert not (root / "run/relational.sock").exists()
    assert (root / "data/state.sqlite3").read_bytes() == before


@pytest.mark.parametrize(
    "drift",
    [
        "missing_record",
        "missing_db",
        "foreign_owner",
        "record_writable",
        "parent_writable",
        "root_writable",
        "active_writable",
        "record_symlink",
        "record_hardlink",
        "data_symlink",
        "db_symlink",
        "wal_symlink",
        "wheel_changed",
        "configuration",
        "schema",
        "profile",
        "pending_rollback",
        "lineage",
        "receipt_schema",
        "key",
    ],
)
def test_normal_startup_refuses_drift_without_repair_or_import(
    prepared, monkeypatch, drift
):
    root, metadata, record, _ = prepared
    secret = SECRET
    if drift == "missing_record":
        (root / "relational.json").unlink()
    elif drift == "missing_db":
        (root / "data/state.sqlite3").unlink()
    elif drift == "foreign_owner":
        monkeypatch.setattr(runtime, "_LIFECYCLE_UID", os.getuid() + 1)
    elif drift in {
        "record_writable",
        "parent_writable",
        "root_writable",
        "active_writable",
    }:
        target = {
            "record_writable": root / "relational.json",
            "parent_writable": root.parent,
            "root_writable": root,
            "active_writable": root / "active.json",
        }[drift]
        target.chmod(target.stat().st_mode | 0o020)
    elif drift in {"record_symlink", "record_hardlink", "data_symlink", "db_symlink"}:
        target = {
            "record_symlink": root / "relational.json",
            "record_hardlink": root / "relational.json",
            "data_symlink": root / "data",
            "db_symlink": root / "data/state.sqlite3",
        }[drift]
        moved = target.with_name(target.name + "-original")
        target.rename(moved)
        (
            os.link(moved, target)
            if drift == "record_hardlink"
            else target.symlink_to(moved)
        )
    elif drift == "wal_symlink":
        (root / "data/state.sqlite3-wal").unlink(missing_ok=True)
        (root / "data/state.sqlite3-wal").symlink_to(root / "active.json")
    elif drift == "wheel_changed":
        wheel = root / "releases" / metadata["sha256"] / "service.whl"
        wheel.chmod(0o640)
        wheel.write_bytes(b"changed")
    elif drift in {"configuration", "schema", "profile"}:
        if drift == "configuration":
            metadata["configuration"]["label"] = "changed"
        elif drift == "schema":
            metadata["storage"]["schema_revision"] = "0002"
        else:
            metadata["storage"]["relational"]["max_busy_ms"] = 0
        (root / "active.json").write_bytes(canonical(metadata))
    elif drift == "pending_rollback":
        (root / (".activation-" + "a" * 32 + ".rollback")).mkdir()
    elif drift == "lineage":
        record = sign_metadata(
            SECRET, "lifecycle", {**record, "database_lineage": "0" * 32}
        )
        (root / "relational.json").write_bytes(canonical(record))
    elif drift == "receipt_schema":
        with sqlite3.connect(root / "data/state.sqlite3") as db:
            db.execute("DROP TABLE three_mm_relational_commits")
        db.close()
    elif drift == "key":
        secret = b"x" * 32
    # WAL readers may update their own coordination sidecars, not business/SDK data.
    before = {
        path: path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and not path.name.endswith(("-wal", "-shm"))
    }
    with pytest.raises((ValueError, OSError, sqlite3.Error)):
        runtime._RelationalHostSession(root, secret)
    assert not (root / "run/relational.sock").exists()
    assert {
        path: path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and not path.name.endswith(("-wal", "-shm"))
    } == before


@pytest.mark.parametrize(
    "changes",
    [
        {"runtime_nonce": "0" * 32},
        {"database_lineage": "0" * 32},
        {"boot_id": "00000000-0000-0000-0000-000000000000"},
        {"lifecycle_sha256": "0" * 64},
        {"recovery_generation": "0" * 32},
        {"version": True},
        {"started_at_ms": True},
        {"deadline_ms": 0},
        {"deadline_ms": 9007199254740990},
        {"maintenance": True},
    ],
)
def test_foreign_expired_or_extended_tickets_cannot_set_context(prepared, changes):
    with runtime._RelationalHostSession(prepared[0], SECRET) as session:
        with pytest.raises(ValueError):
            with session.invocation(ticket(session, **changes), operation_id="inspect"):
                pytest.fail("Bad ticket accepted")
        assert runtime._call_host_metadata(session.path, SECRET)["invocation"] is None


def test_restart_and_full_bounded_ticket_set_never_replay(prepared, monkeypatch):
    with runtime._RelationalHostSession(prepared[0], SECRET) as first:
        previous = ticket(first)
        with first.invocation(previous, operation_id="inspect"):
            pass
        monkeypatch.setattr(runtime, "MAX_INVOCATIONS", 1)
        with pytest.raises(ValueError, match="capacity"):
            with first.invocation(ticket(first), operation_id="inspect"):
                pass
    with runtime._RelationalHostSession(prepared[0], SECRET) as second:
        with pytest.raises(ValueError, match="stale"):
            with second.invocation(previous, operation_id="inspect"):
                pass


def test_ticket_is_bound_to_actual_handler_and_expiry_allows_only_metadata(
    prepared, monkeypatch
):
    with runtime._RelationalHostSession(prepared[0], SECRET) as session:
        current = ticket(session)
        with pytest.raises(ValueError):
            with session.invocation(current, operation_id="other"):
                pass
        with session.invocation(current, operation_id="inspect"):
            original = runtime._clock
            monkeypatch.setattr(
                runtime, "_clock", lambda: (original()[0], current["deadline_ms"])
            )
            assert (
                runtime._call_host_metadata(session.path, SECRET)["invocation"]
                == current
            )
            with pytest.raises(ValueError, match="No active"):
                session._permit_expectations("a" * 32, "write")


def test_prepared_state_does_not_bypass_production_host_gate(prepared, monkeypatch):
    from three_mm_runtime import application_host

    root, metadata, _, _ = prepared
    monkeypatch.setattr(
        application_host.importlib,
        "import_module",
        lambda *_: pytest.fail("Prepared metadata imported package code"),
    )
    with pytest.raises(RuntimeError, match="runtime is not implemented"):
        application_host._load_service(metadata, root, SECRET)


@pytest.mark.parametrize(
    "wire_request",
    [
        {"action": "begin", "payload": {"deadline_ms": 9999999}},
        {"action": "context", "payload": {"authority_epoch": "a" * 32}},
        {"action": "context", "payload": {}, "host_context": {}},
        {"action": "context", "payload": {}, "version": True},
    ],
)
def test_socket_has_no_context_setter_or_sql_endpoint(prepared, wire_request):
    with (
        runtime._RelationalHostSession(prepared[0], SECRET) as session,
        socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection,
    ):
        connection.settimeout(2)
        connection.connect(str(session.path))
        identifier = uuid.uuid4().hex
        runtime._send(
            connection,
            sign_message(
                {
                    "version": 1,
                    "request_id": identifier,
                    "timestamp": int(time.time()),
                    **wire_request,
                },
                SECRET,
            ),
        )
        reply = verify_message(
            runtime._read(connection), SECRET, expected_request_id=identifier
        )
        assert reply["ok"] is False and "result" not in reply
        assert runtime._call_host_metadata(session.path, SECRET)["invocation"] is None


@pytest.mark.parametrize(
    "payload",
    [
        b'{"version":1,"version":1}',
        b'{"clock_ms":NaN}',
        b"x" * (runtime.MAX_METADATA_BYTES + 1),
    ],
)
def test_metadata_decode_is_closed_and_bounded(payload):
    with pytest.raises(ValueError):
        runtime._decode(payload)
