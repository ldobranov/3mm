"""Real installed/reviewed checkpoint grants and CAS, never live VM state."""
from three_mm_platform_wire import COMPATIBILITY_ACTIONS

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import socket
import tempfile
import threading

import pytest
from sqlalchemy import event, select, update
from sqlalchemy.orm import Session, sessionmaker

from backend.db.application_authority_grant import ApplicationAuthorityAction as Action
from backend.db.authority import CoreAuthorityGuard
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.db.module import ApplicationSyncCheckpoint as Checkpoint
from backend.services import application_authority_management as authority
from backend.services.application_checkpoints import _bounded_value, execute_checkpoint
from backend.services.application_platform import ApplicationPlatformServer
from backend.tests.test_application_authority_management import (
    identity,
    installed as managed_installed,
)
from backend.tests.test_application_checkpoint_authority import (
    checkpoint_app as app,
    activate_checkpoint_grant as adopt,
    store_checkpoint_package,
)
from backend.tests.test_application_authority_subjects import (
    installed as source_subject,
)
from backend.tests.test_application_authority_subjects import source_installed
from three_mm_application_sdk import ApplicationPlatformClient, ApplicationPlatformError


posix = pytest.mark.skipif(
    os.name != "posix", reason="Real protected POSIX review keys"
)


def frame(action="checkpoint.get", checkpoint_id="catalog", **changes):
    return {
        "version": 1,
        "request_id": "platform_" + identity(),
        "timestamp": 1,
        "instance_id": "a" * 24,
        "signature": "b" * 64,
        "action": action,
        "checkpoint_id": checkpoint_id,
        **changes,
    }


def call(s, action="checkpoint.get", checkpoint_id="catalog", **changes):
    with Session(s.engine) as db:
        return execute_checkpoint(
            db, db.get(Installation, 1), frame(action, checkpoint_id, **changes)
        )


@posix
def test_exact_grant_read_write_cas_and_metadata_only_machine_audit(app):
    s = app
    adopt(s)
    assert s.manager.inspect(1)["grant_effective"]
    assert call(s) == {"checkpoint_id": "catalog", "revision": 0, "value": {}}
    saved = call(
        s, "checkpoint.put", expected_revision=0, value={"progress": "PRIVATE_PAYLOAD"}
    )
    assert saved["revision"] == 1 and call(s) == saved
    assert call(s, checkpoint_id="cursor")["revision"] == 0
    with pytest.raises(ValueError):
        call(s, "checkpoint.put", checkpoint_id="cursor", expected_revision=0, value={})
    for changes in ({"progress": "PRIVATE_PAYLOAD"}, {"progress": "changed"}):
        with pytest.raises(ValueError):
            call(s, "checkpoint.put", expected_revision=0, value=changes)
    assert call(s) == saved
    with Session(s.engine) as db:
        actions = list(db.scalars(select(Action)))
        writes = [
            json.loads(row.payload)
            for row in actions
            if "checkpoint_put" in row.payload
        ]
        assert len(writes) == 1
        assert writes[0]["data"]["actor"] == ["application", "1"]
        assert "PRIVATE_PAYLOAD" not in json.dumps(writes)


@posix
@pytest.mark.parametrize(
    "mutation",
    [
        "revoke",
        "disable",
        "review_required",
        "configuration",
        "incarnation",
        "recovery",
        "key",
    ],
)
def test_stale_revoked_or_disabled_rights_never_read_or_mutate_saved_data(
    app, mutation
):
    s = app
    adopt(s)
    saved = call(s, "checkpoint.put", expected_revision=0, value={"keep": True})
    if mutation == "revoke":
        s.manager.revoke(
            1,
            actor_token=s.token,
            request_id=identity(),
            expected_revision=s.manager.inspect(1)["grant_record_revision"],
        )
    elif mutation == "key":
        s.keys.rotate(expected_key_id=s.keys.identity().key_id)
    else:
        with s.engine.begin() as db:
            if mutation == "recovery":
                db.execute(update(CoreAuthorityGuard).values(generation=identity()))
            else:
                values = {
                    "disable": {"enabled": False, "status": "disabled"},
                    "review_required": {"authority_mode": "review_required"},
                    "configuration": {
                        "configuration": {**s.configuration, "PRIVATE_NOTE": "changed"}
                    },
                    "incarnation": {"authority_incarnation": identity()},
                }[mutation]
                db.execute(
                    update(Installation).where(Installation.id == 1).values(**values)
                )
    with pytest.raises(ValueError):
        call(s)
    with pytest.raises(ValueError):
        call(s, "checkpoint.put", expected_revision=1, value={"keep": False})
    with Session(s.engine) as db:
        row = db.scalar(select(Checkpoint))
        assert row.value == saved["value"] and row.revision == 1


@posix
@pytest.mark.parametrize(
    "changes",
    [
        {"owner": "2"},
        {"path": "/foreign"},
        {"expected_revision": 0},
        {"value": {}},
        {"version": True},
        {"installation_id": 2},
    ],
)
def test_scoped_read_rejects_extra_or_coerced_metadata(app, changes):
    adopt(app)
    with pytest.raises(ValueError):
        call(app, **changes)


@posix
@pytest.mark.parametrize(
    "checkpoint_id", ["undeclared", "../catalog", "*", "catalog:read", "A", "a" * 97]
)
def test_undeclared_or_invalid_checkpoint_id_refused(app, checkpoint_id):
    adopt(app)
    with pytest.raises(ValueError):
        call(app, checkpoint_id=checkpoint_id)


@pytest.mark.parametrize(
    "value",
    [
        {"n": float("nan")},
        {"n": float("inf")},
        {"n": 2**53},
        {"bad": "\ud800"},
        {1: "key"},
        {"tuple": (1, 2)},
        {"x": object()},
    ],
)
def test_scoped_values_are_finite_plain_json(value):
    with pytest.raises(ValueError):
        _bounded_value(value, 1024)


def test_value_bounds_are_compact_utf8_bytes_and_bounded_structure():
    value = {"т": "я"}
    size = len(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    _bounded_value(value, size)
    with pytest.raises(ValueError):
        _bounded_value(value, size - 1)
    with pytest.raises(ValueError):
        _bounded_value({"nodes": [None] * 16384}, 262144)
    nested = {}
    for _ in range(17):
        nested = {"nested": nested}
    with pytest.raises(ValueError):
        _bounded_value(nested, 262144)


@posix
def test_oversized_preexisting_value_is_preserved_but_not_exposed(app):
    adopt(app)
    with app.engine.begin() as db:
        db.execute(
            Checkpoint.__table__.insert().values(
                application_installation_id=1,
                checkpoint_id="catalog",
                revision=1,
                value={"large": "x" * 2000},
            )
        )
    with pytest.raises(ValueError):
        call(app)
    with pytest.raises(ValueError):
        call(app, "checkpoint.put", expected_revision=1, value={"large": "x" * 2000})
    with Session(app.engine) as db:
        assert len(db.scalar(select(Checkpoint)).value["large"]) == 2000


@posix
def test_full_machine_journal_rolls_back_checkpoint_and_does_not_prune_history(
    app, monkeypatch
):
    adopt(app)
    with Session(app.engine) as db:
        before = set(db.scalars(select(Action.request_id)))
    monkeypatch.setattr(
        authority, "MAX_CHECKPOINT_ACTIONS_PER_INSTALLATION", len(before)
    )
    with pytest.raises(ValueError):
        call(app, "checkpoint.put", expected_revision=0, value={"not_committed": True})
    with Session(app.engine) as db:
        assert list(db.scalars(select(Checkpoint))) == []
        assert set(db.scalars(select(Action.request_id))) == before


@posix
@pytest.mark.parametrize("expected_revision", [True, False, -1, 1.0, "0", 2**53 - 1])
def test_invalid_scoped_revision_never_creates_checkpoint(app, expected_revision):
    adopt(app)
    with pytest.raises(ValueError):
        call(app, "checkpoint.put", expected_revision=expected_revision, value={})
    assert call(app)["revision"] == 0


@posix
def test_revocation_between_package_preflight_and_admission_wins(app, monkeypatch):
    adopt(app)
    saved = call(app, "checkpoint.put", expected_revision=0, value={"keep": True})
    status = app.manager.inspect(1)
    prepare = app.manager._prepare

    def interleave(installation_id):
        prepared = prepare(installation_id)
        app.manager.revoke(
            1,
            actor_token=app.token,
            request_id=identity(),
            expected_revision=status["grant_record_revision"],
        )
        return prepared

    monkeypatch.setattr(app.manager, "_prepare", interleave)
    with pytest.raises(ValueError):
        call(app, "checkpoint.put", expected_revision=1, value={"keep": False})
    with Session(app.engine) as db:
        row = db.scalar(select(Checkpoint))
        assert row.revision == saved["revision"] and row.value == saved["value"]


@posix
@pytest.mark.parametrize("initial_revision", [0, 1])
def test_actual_two_connection_cas_has_one_winner_and_no_implicit_retry(
    app, initial_revision
):
    adopt(app)
    if initial_revision:
        call(app, "checkpoint.put", expected_revision=0, value={"initial": True})
    start = threading.Barrier(2)
    statements = []

    def observed(connection, cursor, statement, parameters, context, many):
        if statement.lstrip().upper().startswith("UPDATE APPLICATION_SYNC_CHECKPOINTS"):
            statements.append(statement)

    event.listen(app.engine, "before_cursor_execute", observed)

    def writer(index):
        start.wait(timeout=10)
        try:
            return call(
                app,
                "checkpoint.put",
                expected_revision=initial_revision,
                value={"winner": index},
            )
        except ValueError:
            return None

    try:
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(writer, [1, 2]))
    finally:
        event.remove(app.engine, "before_cursor_execute", observed)
    winners = [value for value in results if value is not None]
    assert len(winners) == 1 and call(app) == winners[0]
    assert winners[0]["revision"] == initial_revision + 1
    assert statements and all(
        "application_sync_checkpoints.revision =" in sql for sql in statements
    )


@posix
def test_dispatcher_opt_in_get_and_put_use_adapter_but_unrelated_platform_stays_denied(
    app,
):
    adopt(app)
    with Session(app.engine) as db:
        server = ApplicationPlatformServer(None, None, allowed_actions=COMPATIBILITY_ACTIONS)
        app_row = db.get(Installation, 1)
        assert server._dispatch(db, app_row, frame())["revision"] == 0
        assert (
            server._dispatch(
                db,
                db.get(Installation, 1),
                frame("checkpoint.put", expected_revision=0, value={"ok": True}),
            )["revision"]
            == 1
        )
        with pytest.raises(ValueError, match="no supported resource grant"):
            server._dispatch(
                db, db.get(Installation, 1), frame("installation.identity.prove")
            )


@posix
def test_missing_sentinel_is_not_stored_content_for_one_byte_limit(app):
    definition = app.validated.application_extension.model_dump(mode="json")
    definition["checkpoints"][0]["max_value_bytes"] = 1
    store_checkpoint_package(app, definition)
    adopt(app)
    assert call(app) == {"checkpoint_id": "catalog", "revision": 0, "value": {}}
    with pytest.raises(ValueError):
        call(app, "checkpoint.put", expected_revision=0, value={})


@posix
def test_actual_signed_sdk_socket_and_lost_response_do_not_repeat_a_write(
    app, monkeypatch
):
    import backend.database

    adopt(app)
    monkeypatch.setattr(backend.database, "SessionLocal", sessionmaker(bind=app.engine))
    secret = b"x" * 32

    class DropReply:
        def __init__(self, connection):
            self.connection = connection

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.connection.close()

        def settimeout(self, seconds):
            self.connection.settimeout(seconds)

        def recv(self, size):
            return self.connection.recv(size)

        def sendall(self, data):
            pass  # A committed reply is deliberately lost, not a server retry.

    class Server(ApplicationPlatformServer):
        drop = False

        def _handle(self, connection):
            return super()._handle(DropReply(connection) if self.drop else connection)

    with tempfile.TemporaryDirectory(prefix="cp-", dir="/tmp") as directory:
        root = Path(directory)
        (root / ("a" * 24 + ".key")).write_bytes(secret)
        server = Server(root / "p.sock", root, group="missing-test-group")
        server.start()
        client = ApplicationPlatformClient(server.socket_path, "a" * 24, secret)
        try:
            assert client.get_checkpoint("catalog")["revision"] == 0
            server.drop = True
            with pytest.raises(ApplicationPlatformError, match="response is invalid"):
                client.put_checkpoint("catalog", {"once": True}, expected_revision=0)
            server.drop = False
            assert client.get_checkpoint("catalog") == {
                "checkpoint_id": "catalog",
                "revision": 1,
                "value": {"once": True},
            }
            with pytest.raises(ApplicationPlatformError):
                client.put_checkpoint("catalog", {"once": True}, expected_revision=0)
            forged = ApplicationPlatformClient(server.socket_path, "a" * 24, b"y" * 32)
            with pytest.raises(ApplicationPlatformError):
                forged.get_checkpoint("catalog")
            assert client.get_checkpoint("catalog")["revision"] == 1
        finally:
            server.stop()
