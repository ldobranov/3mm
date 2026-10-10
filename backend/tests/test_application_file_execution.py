"""Sealed current grants + actual target-owned POSIX worker; no live devices."""

import base64
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import uuid
import zipfile

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.db.application_authority_grant import ApplicationAuthorityAction as Action
from backend.db.authority import CoreAuthorityGuard
from backend.db.module import (
    ApplicationExtensionInstallation as Installation,
    ModulePackage,
)
from backend.services import application_files as service
from backend.services import application_authority_management as authority
from backend.services.application_platform import ApplicationPlatformServer
from backend.services.module_packages import validate_module_package
from backend.tests.test_application_authority_management import (
    installed as managed_installed,
    source_subject,
    source_installed,
    native,
    decide,
    identity,
)
from three_mm_application_sdk import (
    ApplicationFileExecutionUnconfirmed,
    ApplicationFileLimits,
    ApplicationFileStorage,
    ApplicationFileStorageError,
    ApplicationPlatformClient,
    ApplicationScopedFileStorage,
)
from three_mm_protocol.tests.test_application_private_files import file_request
from three_mm_runtime.application_file_executor import (
    ApplicationFileExecutor,
    call_file_executor,
)
from three_mm_runtime.application_transport import ApplicationTransportError


pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="Actual POSIX keys, worker and file isolation checks"
)


@pytest.fixture
def file_app(managed_installed, request):
    s = managed_installed
    definition = s.validated.application_extension.model_dump(mode="json")
    definition["service"]["sdk_version"] = "1.3"
    overrides = getattr(request, "param", {})
    if isinstance(overrides, str):
        overrides = {"mode": overrides}
    definition["storage"]["private_files"] = file_request(
        **(
            {
                "mode": "read_write",
                "max_file_bytes": 128,
                "max_total_bytes": 200,
                "max_files": 2,
            }
            | overrides
        )
    )
    manifest = s.validated.manifest.model_dump(mode="json")
    output = io.BytesIO()
    with (
        zipfile.ZipFile(s.archive) as previous,
        zipfile.ZipFile(output, "w") as archive,
    ):
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("application-extension.json", json.dumps(definition))
        artifact = definition["service"]["artifact"]
        archive.writestr(artifact, previous.read(artifact))
    s.validated = validate_module_package(output.getvalue())
    s.archive = s.root / "modules" / (s.validated.sha256 + ".zip")
    s.archive.write_bytes(output.getvalue())
    # Short Unix-socket paths; all files are owned disposable test state.
    with tempfile.TemporaryDirectory(prefix="3mm-files-") as temporary:
        s.runtime = Path(temporary) / ("c" * 24)
        (s.runtime / "run").mkdir(parents=True)
        (s.runtime / "data").mkdir(mode=0o700)
        s.secret = b"s" * 32
        s.metadata = {
            "instance_id": "c" * 24,
            "sha256": s.validated.sha256,
            "storage": definition["storage"],
        }
        with s.engine.begin() as db:
            db.execute(
                update(ModulePackage)
                .where(ModulePackage.id == 1)
                .values(
                    sha256=s.validated.sha256,
                    size_bytes=len(output.getvalue()),
                    manifest=manifest,
                    file_path=str(s.archive),
                )
            )
            db.execute(
                update(Installation)
                .where(Installation.id == 1)
                .values(
                    instance_id=s.metadata["instance_id"],
                    socket_path=str(s.runtime / "run/service.sock"),
                )
            )
        yield s


def grant(s):
    with s.engine.begin() as db:
        db.execute(update(Installation).values(enabled=False, status="disabled"))
    n = native(s)

    def plan():
        return s.manager.create_review(
            1,
            actor_token=s.token,
            request_id=identity(),
            native_review_id=n["native_review_id"],
            scopes=s.manager.inspect(1)["scopes"],
        )

    first = plan()
    assert len(first["resources"]["private_files"]) == (
        2 if s.metadata["storage"]["private_files"]["mode"] == "read_write" else 1
    )
    assert {
        item["owner"]["application_installation_id"]
        for item in first["resources"]["private_files"]
    } == {"1"}
    decide(s, decide(s, first, "approve"), "apply")
    with s.engine.begin() as db:
        db.execute(
            update(Installation).values(
                enabled=True, status="active", authority_epoch=identity()
            )
        )
    decide(s, decide(s, plan(), "approve"), "apply")


def request(
    operation="put", request_id=None, file_id="logo", content=b"data", expected=None
):
    value = {
        "file_request_version": 1,
        "request_id": request_id or identity(),
        "operation": operation,
    }
    if operation != "list":
        value["file_id"] = file_id
    if operation in {"put", "delete"}:
        value["expected_sha256"] = expected
    if operation == "put":
        value["content_base64"] = base64.b64encode(content).decode("ascii")
    return value


def execute(s, value):
    with Session(s.engine) as db:
        return service.execute_private_file(
            db, db.get(Installation, 1), value, transport_secret=s.secret
        )


def status(s, request_id):
    with Session(s.engine) as db:
        return service.file_operation_status(db, db.get(Installation, 1), request_id)


def revoke(s):
    s.manager.revoke(
        1,
        actor_token=s.token,
        request_id=identity(),
        expected_revision=s.manager.inspect(1)["grant_record_revision"],
    )


def test_actual_v4_requires_exact_native_proof_and_explicit_file_selection(file_app):
    s = file_app
    n = native(s)
    assert set(s.manager.inspect(1)["scopes"]) == {
        "command:pulse",
        "connector:business_api",
        "storage:private_files_read",
        "storage:private_files_write",
    }
    with pytest.raises(
        authority.AuthorityManagementError, match="selection_not_allowed"
    ):
        s.manager.create_review(
            1,
            actor_token=s.token,
            request_id=identity(),
            native_review_id=n["native_review_id"],
            scopes=["command:pulse", "connector:business_api"],
        )
    assert not s.manager.inspect(1)["grant_effective"]
    with pytest.raises(service.ApplicationFileAuthorityError):
        execute(s, request())
    assert not (s.runtime / "data/sdk-files").exists()


def test_actual_worker_crud_current_grant_cas_quotas_and_historical_revoke(
    file_app, monkeypatch
):
    s = file_app
    grant(s)
    original = service.call_file_executor

    def unlocked(*args, **kwargs):
        # Runtime I/O must not retain the key lease or SQLite write guard.
        with s.keys.locked(), s.engine.begin() as db:
            db.execute(
                update(CoreAuthorityGuard).values(revision=CoreAuthorityGuard.revision)
            )
        return original(*args, **kwargs)

    monkeypatch.setattr(service, "call_file_executor", unlocked)
    first = request()
    with ApplicationFileExecutor(s.runtime, s.metadata, s.secret):
        result = execute(s, first)
        assert result["receipt"]["outcome"] == "completed" and not result["historical"]
        digest = result["receipt"]["sha256"]
        assert execute(s, first)["historical"]
        assert status(s, first["request_id"])["receipt"] == result["receipt"]
        read = execute(s, request("get"))["file_result"]["file"]
        assert base64.b64decode(read["content_base64"]) == b"data"
        assert execute(s, request("list"))["file_result"]["entries"] == [["logo", 4]]
        assert (
            execute(s, request(content=b"bad", expected=None))["receipt"]["outcome"]
            == "execution_unconfirmed"
        )
        changed = execute(s, request(content=b"new", expected=digest))
        assert changed["receipt"]["outcome"] == "completed"
        assert (
            execute(s, request("delete", expected=changed["receipt"]["sha256"]))[
                "receipt"
            ]["outcome"]
            == "completed"
        )
        assert execute(s, request("get"))["file_result"]["file"] is None
        revoke(s)
        assert execute(s, first)[
            "historical"
        ]  # Receipt, not old content or another write.
        assert "file_result" not in execute(s, first)
        with pytest.raises(service.ApplicationFileAuthorityError):
            execute(s, request())
        with pytest.raises(service.ApplicationFileAuthorityError):
            execute(s, request("get"))
    with Session(s.engine) as db:
        journals = db.scalars(select(Action)).all()
        assert all(
            "content_base64" not in row.payload and str(s.runtime) not in row.payload
            for row in journals
        )


@pytest.mark.parametrize(
    "lost",
    ["after_write", "before_dispatch", "malformed_reply", "completion_key_rotation"],
)
def test_uncertainty_never_redispatches_even_after_worker_restart(
    file_app, monkeypatch, lost
):
    s = file_app
    grant(s)
    original, dispatches = service.call_file_executor, []

    def unreliable(path, secret, action, payload):
        if action != "execute":
            return original(path, secret, action, payload)
        dispatches.append(payload)
        if lost == "before_dispatch":
            raise TimeoutError()
        result = original(path, secret, action, payload)
        if lost == "after_write":
            raise ApplicationTransportError("ACK lost")
        if lost == "malformed_reply":
            return {"file": None}
        s.keys.rotate(expected_key_id=s.keys.identity().key_id)
        return result

    monkeypatch.setattr(service, "call_file_executor", unreliable)
    value = request()
    with ApplicationFileExecutor(s.runtime, s.metadata, s.secret):
        assert execute(s, value)["receipt"]["outcome"] == "execution_unconfirmed"
    with ApplicationFileExecutor(s.runtime, s.metadata, s.secret):
        if lost == "completion_key_rotation":
            with pytest.raises(service.ApplicationFileAuthorityError):
                execute(s, value)
        else:
            assert execute(s, value)["historical"]
            assert (
                status(s, value["request_id"])["receipt"]["outcome"]
                == "execution_unconfirmed"
            )
    assert len(dispatches) == 1
    item = ApplicationFileStorage(s.runtime / "data").get("logo")
    assert item is None if lost == "before_dispatch" else item.content == b"data"


@pytest.mark.parametrize("when", ["before_admission", "after_admission"])
def test_revoke_linearization_does_not_replay_or_recall_admitted_write(
    file_app, monkeypatch, when
):
    s = file_app
    grant(s)
    original = service.call_file_executor

    def race(path, secret, action, payload):
        if action == ("hello" if when == "before_admission" else "execute"):
            revoke(s)
        return original(path, secret, action, payload)

    monkeypatch.setattr(service, "call_file_executor", race)
    with ApplicationFileExecutor(s.runtime, s.metadata, s.secret):
        if when == "before_admission":
            with pytest.raises(service.ApplicationFileAuthorityError):
                execute(s, request())
            assert not (s.runtime / "data/sdk-files").exists()
        else:
            assert execute(s, request())["receipt"]["outcome"] == "completed"
        with pytest.raises(service.ApplicationFileAuthorityError):
            execute(s, request(file_id="later"))


@pytest.mark.parametrize(
    "change",
    [
        "configuration",
        "incarnation",
        "epoch",
        "recovery",
        "disabled",
        "socket",
        "secret",
    ],
)
def test_current_resource_and_authentication_drift_deny_before_file_io(
    file_app, change
):
    s = file_app
    grant(s)
    with ApplicationFileExecutor(s.runtime, s.metadata, s.secret):
        if change == "secret":
            s.secret = b"x" * 32
        else:
            with s.engine.begin() as db:
                if change == "recovery":
                    db.execute(update(CoreAuthorityGuard).values(generation=identity()))
                else:
                    values = {
                        "configuration": {"configuration": {}},
                        "incarnation": {"authority_incarnation": identity()},
                        "epoch": {"authority_epoch": identity()},
                        "disabled": {"enabled": False, "status": "disabled"},
                        "socket": {"socket_path": "/var/lib/3mm/core/service.sock"},
                    }[change]
                    db.execute(update(Installation).values(**values))
        with pytest.raises(service.ApplicationFileAuthorityError):
            execute(s, request())
    assert not (s.runtime / "data/sdk-files").exists()


def test_sealed_journal_rejects_conflict_corruption_and_fresh_incarnation(file_app):
    s = file_app
    grant(s)
    value = request()
    with ApplicationFileExecutor(s.runtime, s.metadata, s.secret):
        execute(s, value)
        with pytest.raises(service.ApplicationFileAuthorityError):
            execute(s, {**value, "file_id": "foreign"})
        with s.engine.begin() as db:
            db.execute(update(Installation).values(authority_incarnation=identity()))
        with pytest.raises(service.ApplicationFileAuthorityError):
            status(s, value["request_id"])
        with s.engine.begin() as db:
            db.execute(
                update(Action)
                .where(Action.request_id == value["request_id"])
                .values(payload="{}")
            )
        with pytest.raises(service.ApplicationFileAuthorityError):
            execute(s, value)
    assert ApplicationFileStorage(s.runtime / "data").get("logo").content == b"data"


@pytest.mark.parametrize(
    "file_app,content",
    [
        ({}, b"signed"),
        (
            {"max_file_bytes": 1024 * 1024, "max_total_bytes": 2 * 1024 * 1024},
            b"x" * (1024 * 1024),
        ),
    ],
    indirect=["file_app"],
    ids=["small-file", "one-mib-file"],
)
def test_signed_sdk_gateway_and_separate_worker_do_not_deadlock(
    file_app, monkeypatch, content
):
    s = file_app
    grant(s)
    import backend.database

    monkeypatch.setattr(backend.database, "SessionLocal", lambda: Session(s.engine))
    keys = s.runtime.parent / "keys"
    keys.mkdir()
    (keys / (s.metadata["instance_id"] + ".key")).write_bytes(s.secret)
    gateway = ApplicationPlatformServer(s.runtime.parent / "platform.sock", keys)
    gateway.start()
    declaration = s.metadata["storage"]["private_files"]
    files = ApplicationScopedFileStorage(
        s.runtime / "data",
        limits=ApplicationFileLimits(
            declaration["max_file_bytes"],
            declaration["max_total_bytes"],
            declaration["max_files"],
        ),
        platform=ApplicationPlatformClient(
            gateway.socket_path, s.metadata["instance_id"], s.secret
        ),
    )
    try:
        with ApplicationFileExecutor(s.runtime, s.metadata, s.secret):
            item = files.put("logo", content, expected_sha256=None)
            assert files.get("logo") == item and files.list_entries() == [
                ("logo", len(content))
            ]
            identifier = identity()
            files.put("next", b"x", expected_sha256=None, request_id=identifier)
            assert (
                files.operation_status(identifier)["receipt"]["outcome"] == "completed"
            )
            files.delete("logo", expected_sha256=item.sha256)
            revoke(s)
            with pytest.raises(ApplicationFileExecutionUnconfirmed):
                files.put("denied", b"x", expected_sha256=None)
            with pytest.raises(ApplicationFileStorageError):
                files.get("next")
    finally:
        gateway.stop()


@pytest.mark.parametrize("file_app", ["read"], indirect=True)
def test_read_grant_does_not_authorize_direct_platform_write(file_app):
    s = file_app
    grant(s)
    assert "storage:private_files_write" not in s.manager.inspect(1)["scopes"]
    with ApplicationFileExecutor(s.runtime, s.metadata, s.secret):
        assert execute(s, request("get"))["file_result"]["file"] is None
        assert execute(s, request("list"))["file_result"]["entries"] == []
        for value in (request(), request("delete", expected="a" * 64)):
            with pytest.raises(service.ApplicationFileAuthorityError):
                execute(s, value)
    assert not (s.runtime / "data/sdk-files").exists()


def test_mutation_receipt_capacity_does_not_evict_unknown_work(file_app, monkeypatch):
    s = file_app
    grant(s)
    monkeypatch.setattr(service, "MAX_FILE_ACTIONS_PER_INSTALLATION", 0)
    with ApplicationFileExecutor(s.runtime, s.metadata, s.secret):
        with pytest.raises(service.ApplicationFileAuthorityError):
            execute(s, request())
    assert not (s.runtime / "data/sdk-files").exists()
