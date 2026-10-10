"""Protected preparation -> real non-root host -> signed Core/SDK transport.

Disposable Linux fixtures only. Re-enable is explicit fixture state, NOT proof
of a production first-install/upgrade coordinator or human route acceptance.
"""

import hashlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from backend.config import ApplicationRuntimeSettings
from backend.db.application_authority_grant import ApplicationAuthorityAction as Action
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.db.module import ModulePackage
from backend.services import application_authority_management as authority
from backend.services.application_extensions import (
    ApplicationGatewayError,
    invoke_application,
)
from backend.services.application_platform import ApplicationPlatformServer
from backend.services.module_packages import validate_module_package
from backend.tests.test_application_relational_migrations import (
    migratable,
    migration_ticket,
    run,
)
from backend.tests.test_application_relational_preparation import (
    ROOT_ONLY,
    SECRET,
    apply,
    identity,
    managed_installed,
    native,
    prepared_paths,
    source_installed,
    source_subject,
    stopped,
)
from three_mm_application_sdk import ApplicationPlatformClient
from three_mm_runtime.application_host import _load_service
from three_mm_runtime.application_relational_runtime import PreparedRelationalRuntime
from three_mm_runtime.application_transport import (
    ApplicationServiceClient,
    ApplicationTransportError,
)

pytestmark = [
    pytest.mark.skipif(os.name != "posix", reason="Real POSIX host"),
    ROOT_ONLY,
]


@pytest.fixture
def tmp_path():
    # Short, explicitly disposable paths fit both Unix sockets. All migrations
    # and package factories run in actual UID/GID 1200/1201 subprocesses.
    with tempfile.TemporaryDirectory(prefix="3mm-hr-") as directory:
        yield Path(directory)


SERVICE = """import json, os
from pathlib import Path
from three_mm_application_sdk.scoped_relational import ApplicationRelationalStorageError
from three_mm_application_sdk import ApplicationFileStorageError
class Service:
    def __init__(self, ctx):
        self.ctx = ctx
    def handle(self, op, payload, context):
        if op == 'health':
            return {'status': 'ready'}
        if op == 'health_sql':
            return self.ctx.storage.status()
        if op == 'inspect':
            with self.ctx.storage.read_transaction() as db:
                values = [row[0] for row in db.execute('SELECT value FROM business').fetchall()]
            return {'values': values}
        with self.ctx.storage.transaction() as db:
            if op == 'foreign':
                db.execute("ATTACH DATABASE 'unapproved.sqlite3' AS foreign_db")
            else:
                db.execute('UPDATE business SET value=?', (payload['value'],))
                self.ctx.storage.enqueue_outbox(db, outbox_id=context.idempotency_key,
                    event_type='reference.intent', payload={'value': payload['value']},
                    idempotency_key=context.idempotency_key)
        return {'value': payload.get('value')}
def create_service(ctx):
    assert os.getuid() == os.geteuid() == 1200
    assert os.getgid() == os.getegid() == 1201
    denied = []
    for operation in (ctx.storage.status, lambda: ctx.storage.migrate([], '0002'), ctx.files.list_entries):
        try:
            operation()
        except (ApplicationRelationalStorageError, ApplicationFileStorageError):
            denied.append(True)
    assert denied == [True, True, True]
    Path(ctx.data_dir / 'factory.json').write_text(json.dumps({'uid': os.geteuid(), 'denied': denied}))
    return Service(ctx)
"""


def package(state, mode):
    module = "prepared_reference_" + uuid.uuid4().hex
    wheel = io.BytesIO()
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(module + "/__init__.py", "")
        archive.writestr(module + "/service.py", SERVICE)
        archive.writestr(
            module + "/migrations.py",
            """import os
from pathlib import Path
from three_mm_application_sdk import ApplicationMigration
Path('migration-imported').write_text(str(os.getpid()))
def first(db):
    raise RuntimeError('Existing schema must not be replayed')
def second(db):
    db.execute('ALTER TABLE business ADD COLUMN migrated INTEGER DEFAULT 1')
def get_migrations():
    return [ApplicationMigration('0001', first), ApplicationMigration('0002', second)]
""",
        )
    manifest = state.validated.manifest.model_dump(mode="json")
    definition = state.validated.application_extension.model_dump(mode="json")
    definition["service"].update(
        entrypoint=module + ".service:create_service",
        artifact_sha256=hashlib.sha256(wheel.getvalue()).hexdigest(),
    )
    definition["storage"].update(
        schema_revision="0002",
        migration_entrypoint=module + ".migrations:get_migrations",
    )
    definition["storage"]["relational"]["mode"] = mode
    definition["operations"].extend(
        [
            {
                "operation_id": op,
                "kind": kind,
                "audiences": ["administrator"],
                "idempotency": "required" if kind == "command" else "forbidden",
                "input_schema": {
                    "type": "object",
                    "properties": (
                        {"value": {"type": "string"}} if op == "mutate" else {}
                    ),
                    "required": ["value"] if op == "mutate" else [],
                    "additionalProperties": False,
                },
                "output_schema": {
                    "type": "object",
                    "properties": (
                        {"values": {"type": "array"}}
                        if op == "inspect"
                        else {"value": {"type": "string"}}
                    ),
                    "additionalProperties": False,
                },
            }
            for op, kind in [
                ("mutate", "command"),
                ("inspect", "query"),
                ("foreign", "command"),
            ]
        ]
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("application-extension.json", json.dumps(definition))
        archive.writestr(definition["service"]["artifact"], wheel.getvalue())
    state.validated = validate_module_package(output.getvalue())
    state.archive = state.root / "modules" / (state.validated.sha256 + ".zip")
    state.archive.write_bytes(output.getvalue())
    with state.engine.begin() as db:
        db.execute(
            update(ModulePackage)
            .where(ModulePackage.id == 1)
            .values(
                sha256=state.validated.sha256,
                size_bytes=len(output.getvalue()),
                manifest=manifest,
                file_path=str(state.archive),
            )
        )
    state.native_id = native(state)["native_review_id"]
    apply(state, state.native_id)


@pytest.fixture
def running(migratable, monkeypatch, request):
    state = migratable
    package(state, getattr(request, "param", "read_write"))
    run(
        state, migration_ticket(state)
    )  # Actual reviewed preparation, not hand-written lineage.
    key = state.transport_keys / (state.instance.name + ".key")
    for path in (state.transport_keys, state.runtime, state.runtime / "platform"):
        path.mkdir(exist_ok=True)
        os.chown(path, 0, 1201)
        path.chmod(0o750)
    os.chown(key, 0, 1201)
    # Explicit fixture re-enable; the production activation gate stays blocked.
    with state.engine.begin() as db:
        db.execute(
            update(Installation).values(
                enabled=True,
                status="active",
                authority_epoch=identity(),
                socket_path=str(state.instance / "run/service.sock"),
            )
        )
    apply(state, state.native_id)
    import backend.database

    monkeypatch.setattr(
        backend.database, "SessionLocal", sessionmaker(bind=state.engine)
    )
    state.server = ApplicationPlatformServer(
        state.runtime / "platform/platform.sock", state.transport_keys
    )
    state.server.start()
    os.chown(state.server.socket_path, 0, 1201)
    sdk_root = Path(__file__).resolve().parents[2]
    launch = (
        "import sys; sys.path.insert(0, " + repr(str(sdk_root)) + "); "
        "from three_mm_runtime.application_host import serve; "
        "from pathlib import Path; serve("
        + repr(state.instance.name)
        + ", Path("
        + repr(str(state.runtime))
        + "), Path("
        + repr(str(state.transport_keys))
        + "), 1201)"
    )
    state.process = subprocess.Popen(
        [sys.executable, "-I", "-c", launch],
        user=1200,
        group=1201,
        extra_groups=[],
        start_new_session=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={"PATH": "/usr/bin:/bin"},
        cwd=state.data,
    )
    state.settings = ApplicationRuntimeSettings(
        root=state.runtime,
        key_root=state.transport_keys,
        helper_socket=state.runtime / "helper.sock",
    )
    state.launch = launch
    try:
        deadline = time.monotonic() + 10
        while not (state.instance / "run/service.sock").is_socket():
            if state.process.poll() is not None:
                raise AssertionError(state.process.communicate(timeout=2)[1].decode())
            if time.monotonic() >= deadline:
                raise AssertionError("Non-root host did not become ready")
            time.sleep(0.05)
        yield state
    finally:
        state.process.terminate()
        try:
            state.process.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            state.process.kill()
            state.process.communicate(timeout=3)
        state.server.stop()


def invoke(state, op, payload=None, **changes):
    context = {"audience": "administrator", "correlation_id": identity()}
    if op != "inspect":
        context["idempotency_key"] = identity()
    context.update(changes)
    with Session(state.engine) as db:
        return invoke_application(
            db.get(Installation, 1),
            db.get(ModulePackage, 1),
            state.settings,
            op,
            payload or {},
            context,
            required_audience="administrator",
        )


def test_nonroot_normal_host_signed_dispatch_sql_outbox_receipt(running):
    state = running
    assert json.loads((state.data / "factory.json").read_text()) == {
        "uid": 1200,
        "denied": [True, True, True],
    }
    assert invoke(state, "inspect") == {"values": ["preserved"]}
    assert invoke(state, "mutate", {"value": "normal host"}) == {"value": "normal host"}
    assert invoke(state, "inspect") == {"values": ["normal host"]}
    with sqlite3.connect(state.database) as db:
        assert db.execute("SELECT COUNT(*) FROM three_mm_outbox").fetchone()[0] == 2
        assert (
            db.execute("SELECT COUNT(*) FROM three_mm_relational_commits").fetchone()[0]
            == 1
        )
        assert db.execute(
            "SELECT revision FROM three_mm_schema_migrations ORDER BY rowid"
        ).fetchall() == [("0001",), ("0002",)]
    with state.keys.locked() as key, Session(state.engine) as db:
        records = [
            authority._load(db, key, "action", row, row.request_id)
            for row in db.scalars(select(Action))
        ]
    writes = [
        value
        for value in records
        if value["data"].get("operation") == "relational_transaction"
        and value["data"]["permit"]["mode"] == "write"
    ]
    assert len(writes) == 1 and writes[0]["state"] == "committed"


@pytest.mark.parametrize("running", ["read"], indirect=True)
def test_readonly_real_host_never_promotes_to_write(running):
    assert invoke(running, "inspect") == {"values": ["preserved"]}
    with pytest.raises(ApplicationGatewayError, match="read-only"):
        invoke(running, "mutate", {"value": "forbidden"})
    assert invoke(running, "inspect") == {"values": ["preserved"]}


def test_normal_dispatch_rejects_revoke_before_handler(running):
    state = running
    state.manager.revoke(
        1,
        actor_token=state.token,
        request_id=identity(),
        expected_revision=state.manager.inspect(1)["grant_record_revision"],
    )
    with pytest.raises(ApplicationGatewayError) as error:
        invoke(state, "mutate", {"value": "revoked"})
    assert error.value.phase.value == "not_dispatched"
    with sqlite3.connect(state.database) as db:
        assert db.execute("SELECT value FROM business").fetchall() == [("preserved",)]


def test_real_host_refuses_missing_ticket_and_runtime_sql_escape(running):
    state = running
    client = ApplicationServiceClient(state.instance / "run/service.sock", SECRET, 2)
    with pytest.raises(ApplicationTransportError):
        client.invoke(
            "mutate",
            {"value": "forged"},
            {"audience": "administrator", "idempotency_key": identity()},
        )
    with pytest.raises(ApplicationGatewayError):
        invoke(state, "foreign")
    with pytest.raises(ApplicationGatewayError, match="value limit"):
        invoke(state, "mutate", {"value": "x" * 262145})
    for changes in ({"audience": "operator"}, {"relational_invocation": {}}):
        with pytest.raises(ApplicationGatewayError) as error:
            invoke(state, "mutate", {"value": "forged"}, **changes)
        assert error.value.phase.value == "not_dispatched"
    assert not (state.data / "unapproved.sqlite3").exists()
    assert invoke(state, "inspect") == {"values": ["preserved"]}


@pytest.mark.parametrize(
    "extra",
    [
        {"database_path": "/foreign"},
        {"deadline_ms": 999},
        {"sql": "DROP TABLE business"},
    ],
)
def test_signed_relational_transport_rejects_package_context_fields(running, extra):
    platform = ApplicationPlatformClient(
        running.server.socket_path, running.instance.name, SECRET
    )
    with pytest.raises(RuntimeError, match="metadata is invalid"):
        platform._call(
            "relational.admit", {"transaction_id": identity(), "mode": "read", **extra}
        )


def test_reserved_readiness_has_no_business_or_outbox_read_grant(running):
    state = running
    state.manager.revoke(
        1,
        actor_token=state.token,
        request_id=identity(),
        expected_revision=state.manager.inspect(1)["grant_record_revision"],
    )
    readiness = ApplicationServiceClient(
        state.instance / "run/service.sock", SECRET, 2
    ).invoke("three_mm.platform.status", {}, {"audience": "internal"})
    assert readiness == {
        "revision": "0002",
        "outbox": {},
        "outbox_inspected": False,
        "storage_profile": "relational",
    }
    assert invoke_application_health(state) == {"status": "ready"}


def invoke_application_health(state):
    with Session(state.engine) as db:
        return invoke_application(
            db.get(Installation, 1),
            db.get(ModulePackage, 1),
            state.settings,
            "health",
            {},
            {"audience": "internal", "correlation_id": identity()},
            required_audience="internal",
        )


def test_lost_completion_response_never_replays_committed_sql(running, monkeypatch):
    state = running
    dispatch = state.server._dispatch

    def lose_response(db, installation, request, **kwargs):
        result = dispatch(db, installation, request, **kwargs)
        if request.get("action") == "relational.complete":
            raise OSError("Completion response lost AFTER durable Core commit")
        return result

    monkeypatch.setattr(state.server, "_dispatch", lose_response)
    with pytest.raises(ApplicationGatewayError, match="unconfirmed; do not replay"):
        invoke(state, "mutate", {"value": "committed once"})
    with state.keys.locked() as key, Session(state.engine) as db:
        records = [
            authority._load(db, key, "action", row, row.request_id)
            for row in db.scalars(select(Action))
        ]
    writes = [
        value
        for value in records
        if value["data"].get("operation") == "relational_transaction"
        and value["data"]["permit"]["mode"] == "write"
    ]
    assert len(writes) == 1 and writes[0]["state"] == "committed"
    platform = ApplicationPlatformClient(
        state.server.socket_path, state.instance.name, SECRET
    )
    identifier = writes[0]["data"]["permit"]["transaction_id"]
    assert platform._call("relational.status", {"transaction_id": identifier}) == {
        "transaction_id": identifier,
        "outcome": "committed",
        "historical": True,
    }
    assert invoke(state, "inspect") == {"values": ["committed once"]}
    with sqlite3.connect(state.database) as db:
        assert db.execute("SELECT COUNT(*) FROM three_mm_outbox").fetchone()[0] == 2
        assert (
            db.execute("SELECT COUNT(*) FROM three_mm_relational_commits").fetchone()[0]
            == 1
        )


def test_normal_host_restart_preserves_data_without_migration_import(running):
    state = running
    assert invoke(state, "mutate", {"value": "before restart"}) == {
        "value": "before restart"
    }
    migration_import = (state.data / "migration-imported").read_bytes()
    state.process.terminate()
    state.process.communicate(timeout=3)
    old = state.instance / "run/service.sock"
    old.unlink()
    state.process = subprocess.Popen(
        [sys.executable, "-I", "-c", state.launch],
        user=1200,
        group=1201,
        extra_groups=[],
        start_new_session=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={"PATH": "/usr/bin:/bin"},
        cwd=state.data,
    )
    deadline = time.monotonic() + 10
    while not old.is_socket():
        if state.process.poll() is not None:
            raise AssertionError(state.process.communicate(timeout=2)[1].decode())
        assert time.monotonic() < deadline, "Restart did not become ready"
        time.sleep(0.05)
    assert (state.data / "migration-imported").read_bytes() == migration_import
    assert invoke(state, "inspect") == {"values": ["before restart"]}


def test_prepared_runtime_does_not_import_package_code_as_root(migratable):
    state = migratable
    package(state, "read_write")
    run(state, migration_ticket(state))
    metadata = json.loads((state.instance / "active.json").read_text())
    migration_import = (state.data / "migration-imported").read_bytes()
    with PreparedRelationalRuntime(state.instance, metadata, SECRET) as runtime:
        with pytest.raises(RuntimeError, match="non-root service"):
            _load_service(metadata, state.instance, SECRET, relational_runtime=runtime)
    assert not (state.data / "factory.json").exists()
    assert (state.data / "migration-imported").read_bytes() == migration_import


def test_prepared_runtime_refuses_new_pending_checkpoint(migratable):
    state = migratable
    package(state, "read_write")
    run(state, migration_ticket(state))
    metadata = json.loads((state.instance / "active.json").read_text())
    with PreparedRelationalRuntime(state.instance, metadata, SECRET) as runtime:
        assert runtime.readiness()["revision"] == "0002"
        (state.instance / ".database-test.rollback").mkdir()
        with pytest.raises(ValueError, match="recovery is pending"):
            runtime.readiness()
    with pytest.raises(ValueError, match="recovery is pending"):
        PreparedRelationalRuntime(state.instance, metadata, SECRET)
    assert not (state.data / "factory.json").exists()
