"""Exact delivered relational ZIP, unit refusals and disposable non-root lifecycle.

Internal engine admission below is unit-only. Root cases separately use real
registration/review/helper/Core-UID migration/host transport, never live units.
"""

import base64
import csv
import hashlib
import importlib
import importlib.util
import io
import json
import os
import sqlite3
import subprocess
import sys
import time
import zipfile
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import update

from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.db.module import ModulePackage
from backend.services.module_packages import validate_module_package
from backend.tests.test_application_relational_activation_control import (
    catalog,
    deployed,
    managed_installed,
    original_production,
    prepared,
)
from backend.tests.test_application_relational_activation_control import (
    request as start_request,
)
from backend.tests.test_application_relational_activation_control import (
    source_installed,
    source_subject,
    tmp_path,
)
from backend.tests.test_application_relational_preparation import ROOT_ONLY, identity
from backend.tests.test_application_relational_reactivation_control import review
from backend.tests.test_application_relational_registration import approve, register
from three_mm_application_sdk import (
    ApplicationContext,
    ApplicationStorage,
    OperationContext,
)
from three_mm_application_sdk.scoped_relational import (
    ApplicationRelationalExecutionUnconfirmed,
    ApplicationScopedStorage,
    _TransactionAdmission,
)
from three_mm_runtime import application_lifecycle as locks
from three_mm_runtime import update_helper

ROOT = Path(__file__).parents[2] / "modules/wp4-relational-test"


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def artifact():
    return load("wp4r_builder", "build_test_package.py").build_package()


@pytest.fixture
def delivered(tmp_path):
    payload = artifact()
    validated = validate_module_package(payload)
    wheel = tmp_path / "fixture.whl"
    with zipfile.ZipFile(io.BytesIO(payload)) as package:
        wheel.write_bytes(
            package.read(validated.application_extension.service.artifact)
        )
    sys.path.insert(0, str(wheel))
    try:
        yield validated, importlib.import_module(
            "wp4_relational_test.service"
        ), importlib.import_module("wp4_relational_test.migrations")
    finally:
        sys.path.remove(str(wheel))
        for name in list(sys.modules):
            if name == "wp4_relational_test" or name.startswith("wp4_relational_test."):
                sys.modules.pop(name)


def admin(identifier=None):
    return OperationContext(
        "administrator", "test", user_id=1, idempotency_key=identifier
    )


def service(delivery, data, storage=None):
    _, module, _ = delivery
    return module.create_service(
        ApplicationContext(
            "org.3mm.wp4-relational-test",
            "1.0.0",
            data,
            {},
            storage or ApplicationStorage(data),
        )
    )


def engine(delivery, data, *, admit=True):
    package, _, migrations = delivery
    # Unit-only bootstrap, not an installation/authority acceptance shortcut.
    ApplicationStorage(data).migrate(migrations.get_migrations(), "0001")
    return ApplicationScopedStorage(
        data,
        declaration=package.application_extension.storage.relational,
        schema_revision="0001",
        admit=(
            (
                lambda tid, mode, profile, deadline: _TransactionAdmission(
                    tid, mode, profile, deadline
                )
            )
            if admit
            else None
        ),
    )


@pytest.mark.parametrize("architecture", ["armv6l", "aarch64", "x86_64"])
def test_zip_is_reproducible_headless_bounded_and_record_hashes_are_exact(architecture):
    payload = artifact()
    assert payload == artifact()
    validated = validate_module_package(payload, architecture=architecture)
    app = validated.application_extension
    assert validated.manifest.manifest_version == 2 and app.service.sdk_version == "1.3"
    assert app.storage.relational.max_database_bytes == 1048576
    assert app.storage.private_files is None and not app.storage.contains_personal_data
    assert not (
        app.routes
        or app.jobs
        or app.connectors
        or app.command_bindings
        or app.event_subscriptions
        or app.public_http_routes
    )
    assert not validated.manifest.registrations and validated.compiled_ui is None
    with zipfile.ZipFile(io.BytesIO(payload)) as package:
        wheel_bytes = package.read(app.service.artifact)
    assert hashlib.sha256(wheel_bytes).hexdigest() == app.service.artifact_sha256
    with zipfile.ZipFile(io.BytesIO(wheel_bytes)) as wheel:
        rows = list(
            csv.reader(
                io.StringIO(
                    wheel.read("wp4_relational_test-1.0.0.dist-info/RECORD").decode()
                )
            )
        )
        assert {row[0] for row in rows} == set(wheel.namelist())
        for name, digest, size in rows:
            if not name.endswith("/RECORD"):
                contents = wheel.read(name)
                encoded = (
                    base64.urlsafe_b64encode(hashlib.sha256(contents).digest())
                    .rstrip(b"=")
                    .decode()
                )
                assert digest == "sha256=" + encoded and int(size) == len(contents)


def test_factory_and_health_have_no_sql_files_or_migration_effects(delivered, tmp_path):
    data = tmp_path / "data"
    instance = service(delivered, data)
    assert instance.handle("health", {}, OperationContext("internal", "test")) == {
        "status": "ready"
    }
    assert not data.exists()
    with pytest.raises(ValueError, match="scoped relational"):
        instance.handle("db_get", {}, admin())
    with pytest.raises(ValueError, match="administrator"):
        instance.handle("db_get", {}, OperationContext("public", "test"))
    assert not data.exists()


def test_scoped_storage_without_admission_is_blocked_and_has_no_fallback(
    delivered, tmp_path
):
    data = tmp_path / "data"
    instance = service(delivered, data, engine(delivered, data, admit=False))
    identifier = "1" * 32
    assert instance.handle("db_get", {}, admin())["status"] == "blocked"
    assert (
        instance.handle(
            "db_put", {"request_id": identifier, "text": "test"}, admin(identifier)
        )["status"]
        == "unconfirmed"
    )
    assert (
        instance.handle("db_record", {"request_id": identifier}, admin())["status"]
        == "blocked"
    )
    with closing(sqlite3.connect(data / "state.sqlite3")) as db:
        assert db.execute("SELECT COUNT(*) FROM probe_writes").fetchone()[0] == 0


def test_owned_sql_records_deduplicate_conflict_and_deny_attach(delivered, tmp_path):
    data = tmp_path / "data"
    instance = service(delivered, data, engine(delivered, data))
    assert instance.handle("db_get", {}, admin())["status"] == "missing"
    identifier = "1" * 32
    payload = {"request_id": identifier, "text": "WP4 relational test"}
    stored = instance.handle("db_put", payload, admin(identifier))
    assert stored["status"] == "stored"
    assert instance.handle("db_put", payload, admin(identifier))["status"] == "replayed"
    assert (
        instance.handle("db_put", {**payload, "text": "changed"}, admin(identifier))[
            "status"
        ]
        == "conflict"
    )
    result = instance.handle("db_get", {}, admin())
    assert result["text"] == payload["text"] and result["write_count"] == 1
    record = instance.handle("db_record", {"request_id": identifier}, admin())
    assert (
        record["sha256"] == stored["sha256"]
        and record["record_kind"] == "application_record_not_core_receipt"
    )
    assert instance.handle("db_boundary", {}, admin()) == {"status": "blocked"}
    assert instance.handle("db_get", {}, admin()) == result


def test_fixture_refuses_more_than_sixteen_business_records(delivered, tmp_path):
    data = tmp_path / "data"
    instance = service(delivered, data, engine(delivered, data))
    for index in range(16):
        identifier = f"{index:032x}"
        assert (
            instance.handle(
                "db_put",
                {"request_id": identifier, "text": str(index)},
                admin(identifier),
            )["status"]
            == "stored"
        )
    identifier = "f" * 32
    assert (
        instance.handle(
            "db_put", {"request_id": identifier, "text": "overflow"}, admin(identifier)
        )["status"]
        == "full"
    )
    assert instance.handle("db_get", {}, admin())["write_count"] == 16


@pytest.mark.parametrize("change", [{"request_id": "invalid"}, {"text": "x" * 257}])
def test_invalid_operation_is_refused_before_any_database_creation(
    delivered, tmp_path, change
):
    data = tmp_path / "absent"
    declaration = delivered[0].application_extension.storage.relational
    instance = service(
        delivered,
        data,
        ApplicationScopedStorage(data, declaration=declaration, schema_revision="0001"),
    )
    with pytest.raises(ValueError):
        instance.handle(
            "db_put",
            {"request_id": "1" * 32, "text": "test", **change},
            admin("1" * 32),
        )
    assert not data.exists()


def test_unconfirmed_signed_completion_does_not_repeat_callback(
    delivered, tmp_path, monkeypatch
):
    from contextlib import contextmanager

    data = tmp_path / "data"
    storage = engine(delivered, data)
    original = storage.transaction
    calls = []

    @contextmanager
    def lost():
        calls.append("begin")
        with original() as db:
            yield db
        raise ApplicationRelationalExecutionUnconfirmed("b" * 32)

    monkeypatch.setattr(storage, "transaction", lost)
    identifier = "1" * 32
    result = service(delivered, data, storage).handle(
        "db_put", {"request_id": identifier, "text": "test"}, admin(identifier)
    )
    assert result["status"] == "unconfirmed" and result["transaction_id"] == "b" * 32
    assert calls == ["begin"]
    with closing(sqlite3.connect(data / "state.sqlite3")) as db:
        assert db.execute("SELECT COUNT(*) FROM probe_writes").fetchone()[0] == 1


def test_probe_requires_exact_digest_and_explicit_upload_consent_before_login(
    tmp_path, monkeypatch
):
    probe = load("wp4r_probe", "probe.py")
    archive = tmp_path / "test.zip"
    archive.write_bytes(artifact())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    body, media = probe.upload_body(archive, digest)
    assert archive.read_bytes() in body and media.startswith("multipart/form-data;")
    with pytest.raises(ValueError, match="digest"):
        probe.upload_body(archive, "f" * 64)
    monkeypatch.setattr(
        sys,
        "argv",
        ["probe.py", "upload", "--package", str(archive), "--expected-sha", digest],
    )
    monkeypatch.setattr(
        "builtins.input",
        lambda *a: pytest.fail("Unconfirmed upload prompted credentials"),
    )
    with pytest.raises(SystemExit):
        probe.main()


@pytest.mark.parametrize(
    "action, arguments",
    [
        ("get", []),
        ("put", ["--request-id", "1" * 32, "--text", "test"]),
        ("record", ["--request-id", "1" * 32]),
        ("boundary", []),
    ],
)
def test_probe_sends_only_one_operation_and_never_prints_credentials(
    action, arguments, monkeypatch, capsys
):
    probe = load("wp4r_probe", "probe.py")
    calls = []

    def call(path, payload=None, token=None, **kwargs):
        calls.append((path, payload, token))
        return (
            {"token": "secret-bearer"}
            if path == "/api/user/login"
            else {"status": "test"}
        )

    monkeypatch.setattr(probe, "call", call)
    monkeypatch.setattr("builtins.input", lambda *a: "admin@example.com")
    monkeypatch.setattr(probe.getpass, "getpass", lambda *a: "secret-password")
    monkeypatch.setattr(sys, "argv", ["probe.py", action, *arguments])
    assert probe.main() == 0 and len(calls) == 2
    assert calls[1][0].startswith(probe.APP + "/operations/")
    assert calls[1][2] == "secret-bearer"
    output = capsys.readouterr().out
    assert "secret-password" not in output and "secret-bearer" not in output


def test_confirmed_upload_only_uses_catalog_endpoint(tmp_path, monkeypatch, capsys):
    from backend.routes.modules import PackageResponse

    probe = load("wp4r_probe", "probe.py")
    archive = tmp_path / "test.zip"
    archive.write_bytes(artifact())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    calls = []

    def call(path, payload=None, token=None, **kwargs):
        calls.append((path, kwargs))
        if path == "/api/user/login":
            return {"token": "test-bearer"}
        return PackageResponse(
            module_id=probe.MODULE,
            version="1.0.0",
            sha256=digest,
            size_bytes=archive.stat().st_size,
            manifest={},
            registrations=[],
        ).model_dump(mode="json")

    monkeypatch.setattr(probe, "call", call)
    monkeypatch.setattr("builtins.input", lambda *a: "admin@example.com")
    monkeypatch.setattr(probe.getpass, "getpass", lambda *a: "test-password")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "probe.py",
            "upload",
            "--package",
            str(archive),
            "--expected-sha",
            digest,
            "--confirm-catalog-upload-only",
        ],
    )
    assert probe.main() == 0
    assert [item[0] for item in calls] == [
        "/api/user/login",
        "/api/v1/modules/packages",
    ]
    assert archive.read_bytes() in calls[1][1]["raw"]
    result = json.loads(capsys.readouterr().out)
    assert result == {
        "module_id": probe.MODULE,
        "version": "1.0.0",
        "sha256": digest,
        "installation_or_start_requested": False,
        "local_package_id_lookup_required": True,
    }


def test_catalog_accepts_public_package_response_without_internal_id(
    monkeypatch, capsys
):
    from backend.routes.modules import PackageResponse

    probe = load("wp4r_probe", "probe.py")
    calls = []
    package = PackageResponse(
        module_id=probe.MODULE,
        version="1.0.0",
        sha256="a" * 64,
        size_bytes=4350,
        manifest={},
        registrations=[],
    ).model_dump(mode="json")
    assert "id" not in package

    def call(path, payload=None, token=None, **kwargs):
        calls.append((path, payload))
        if path == "/api/user/login":
            return {"token": "secret-bearer"}
        assert path == "/api/v1/modules/packages" and payload is None
        assert token == "secret-bearer"
        return [
            {**package, "module_id": "org.example.unrelated"},
            package,
        ]

    monkeypatch.setattr(probe, "call", call)
    monkeypatch.setattr("builtins.input", lambda *a: "admin@example.com")
    monkeypatch.setattr(probe.getpass, "getpass", lambda *a: "secret-password")
    monkeypatch.setattr(sys, "argv", ["probe.py", "catalog"])
    assert probe.main() == 0
    assert [path for path, _ in calls] == [
        "/api/user/login",
        "/api/v1/modules/packages",
    ]
    output = capsys.readouterr().out
    assert "secret-password" not in output and "secret-bearer" not in output
    assert json.loads(output) == [
        {"module_id": probe.MODULE, "version": "1.0.0", "sha256": "a" * 64}
    ]


@pytest.mark.parametrize(
    "case",
    ["valid", "missing_account", "root_account", "shared_uid", "enabled", "running"],
)
def test_preflight_is_read_only_and_missing_or_running_prerequisites_block(
    case, monkeypatch
):
    probe = load("wp4r_probe", "probe.py")
    accounts = {
        "3mm": SimpleNamespace(pw_uid=997, pw_gid=986),
        "3mm-app": SimpleNamespace(pw_uid=994, pw_gid=985),
    }
    if case == "missing_account":
        del accounts["3mm-app"]
    elif case == "root_account":
        accounts["3mm-app"].pw_uid = 0
    elif case == "shared_uid":
        accounts["3mm-app"].pw_uid = 997
    fields = {
        "LoadState": "loaded",
        "User": "3mm-app",
        "Group": "3mm-app",
        "ActiveState": "active" if case == "running" else "inactive",
        "MainPID": "123" if case == "running" else "0",
        "UnitFileState": "enabled" if case == "enabled" else "disabled",
    }
    calls = []

    def account(name):
        if name not in accounts:
            raise KeyError(name)
        return accounts[name]

    def run(arguments, **kwargs):
        calls.append(arguments)
        output = (
            "active\n" * 4
            if arguments[1] == "is-active"
            else "\n".join(f"{key}={value}" for key, value in fields.items())
        )
        return SimpleNamespace(returncode=0, stdout=output)

    monkeypatch.setattr(probe, "os", SimpleNamespace(name="posix"))
    monkeypatch.setitem(sys.modules, "pwd", SimpleNamespace(getpwnam=account))
    monkeypatch.setattr(
        probe,
        "Path",
        lambda *a: SimpleNamespace(
            is_dir=lambda: True, read_text=lambda **kw: "0.3.0-beta.48\n"
        ),
    )
    monkeypatch.setattr(probe.subprocess, "run", run)
    result = probe.preflight()
    assert result["changes_performed"] is False and result["authority_checked"] is False
    assert result["status"] == (
        "ready_for_catalog_only" if case == "valid" else "blocked"
    )
    assert len(calls) == 2 and [item[1] for item in calls] == ["is-active", "show"]


def authority_helper(monkeypatch):
    monkeypatch.setitem(sys.modules, "probe", load("wp4r_probe", "probe.py"))
    helper = load("wp4r_authority", "authority_probe.py")
    monkeypatch.setattr("builtins.input", lambda *a: "admin@example.com")
    monkeypatch.setattr(helper.getpass, "getpass", lambda *a: "secret-password")
    return helper


@pytest.mark.parametrize("action", ["review", "approve", "apply", "revoke"])
def test_authority_helper_keeps_each_permission_decision_separate(
    action, monkeypatch, capsys
):
    helper = authority_helper(monkeypatch)
    arguments = ["authority_probe.py", action, "--request-id", "1" * 32]
    if action == "review":
        arguments += ["--native-review-id", "2" * 32, "--expected-sha", "a" * 64]
    else:
        arguments += ["--expected-revision", "3" * 32, "--confirm-reviewed-rights"]
        if action != "revoke":
            arguments += ["--plan-id", "4" * 32, "--fingerprint", "b" * 64]
    calls = []

    def call(path, payload=None, token=None):
        calls.append((path, payload))
        if path == "/api/user/login":
            return {"token": "secret-bearer"}
        if path == helper.APP + "/authority":
            return {
                "artifact_sha256": "a" * 64,
                "review_available": True,
                "scopes": helper.SCOPES,
                "native_reviews": [{"native_review_id": "2" * 32}],
            }
        assert token == "secret-bearer"
        return {"state": "manual_action_only"}

    monkeypatch.setattr(helper, "call", call)
    monkeypatch.setattr(sys, "argv", arguments)
    assert helper.main() == 0
    mutations = [
        item for item in calls if item[0] != "/api/user/login" and item[1] is not None
    ]
    assert len(mutations) == 1
    expected = (
        "reviews"
        if action == "review"
        else "revoke" if action == "revoke" else "reviews/" + "4" * 32 + "/" + action
    )
    assert mutations[0][0] == helper.APP + "/authority/" + expected
    assert mutations[0][1]["request_id"] == "1" * 32
    if action == "review":
        assert mutations[0][1]["scopes"] == helper.SCOPES
    else:
        assert mutations[0][1]["expected_revision"] == "3" * 32
    output = capsys.readouterr().out
    assert "secret-bearer" not in output and "secret-password" not in output


@pytest.mark.parametrize("action", ["review", "approve", "apply", "revoke"])
def test_authority_helper_missing_confirmation_or_pin_refuses_before_login(
    action, monkeypatch
):
    helper = authority_helper(monkeypatch)
    monkeypatch.setattr(
        "builtins.input",
        lambda *a: pytest.fail("Invalid authority action prompted login"),
    )
    monkeypatch.setattr(
        sys, "argv", ["authority_probe.py", action, "--request-id", "1" * 32]
    )
    with pytest.raises(SystemExit):
        helper.main()


@pytest.mark.parametrize("drift", ["artifact", "scopes", "native_review", "key"])
def test_authority_helper_declines_unavailable_or_changed_resources_before_review_write(
    drift, monkeypatch
):
    helper = authority_helper(monkeypatch)
    calls = []
    status = {
        "artifact_sha256": "a" * 64,
        "review_available": True,
        "scopes": helper.SCOPES,
        "native_reviews": [{"native_review_id": "2" * 32}],
    }
    if drift == "artifact":
        status["artifact_sha256"] = "c" * 64
    elif drift == "scopes":
        status["scopes"] = ["storage:private_files_read"]
    elif drift == "native_review":
        status["native_reviews"] = []
    else:
        status["review_available"] = False

    def call(path, payload=None, token=None):
        calls.append(path)
        return {"token": "test-bearer"} if path == "/api/user/login" else status

    monkeypatch.setattr(helper, "call", call)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "authority_probe.py",
            "review",
            "--request-id",
            "1" * 32,
            "--native-review-id",
            "2" * 32,
            "--expected-sha",
            "a" * 64,
        ],
    )
    assert helper.main() == 1 and calls == [
        "/api/user/login",
        helper.APP + "/authority",
    ]


def test_authority_helper_uncertain_apply_does_not_retry_or_create_another_action(
    monkeypatch, capsys
):
    helper = authority_helper(monkeypatch)
    calls = []

    def call(path, payload=None, token=None):
        calls.append(path)
        if path == "/api/user/login":
            return {"token": "secret-bearer"}
        raise TimeoutError("lost acknowledgement")

    monkeypatch.setattr(helper, "call", call)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "authority_probe.py",
            "apply",
            "--request-id",
            "1" * 32,
            "--plan-id",
            "2" * 32,
            "--expected-revision",
            "3" * 32,
            "--fingerprint",
            "a" * 64,
            "--confirm-reviewed-rights",
        ],
    )
    assert helper.main() == 1 and len(calls) == 2
    output = capsys.readouterr()
    assert "No retry" in output.err and "secret-bearer" not in output.out + output.err


@pytest.fixture
def initial(catalog, tmp_path, monkeypatch):
    state = catalog
    payload = artifact()
    state.validated = validate_module_package(payload)
    state.archive = state.root / "modules" / (state.validated.sha256 + ".zip")
    state.archive.write_bytes(payload)
    state.configuration = {}
    with state.engine.begin() as db:
        db.execute(
            update(ModulePackage).values(
                module_id=state.validated.manifest.module_id,
                version="1.0.0",
                sha256=state.validated.sha256,
                manifest=state.validated.manifest.model_dump(mode="json"),
                size_bytes=len(payload),
                file_path=str(state.archive),
            )
        )
    assert register(state)["active_version"] is None
    approve(state, 1)
    tmp_path.chmod(0o755)
    state.runtime, state.transport_keys, state.helper_state = [
        tmp_path / name for name in ("runtime", "keys", "helper-state")
    ]
    for path in (state.runtime, state.transport_keys, state.helper_state):
        path.mkdir(mode=0o750)
    for path in (state.runtime, state.transport_keys):
        os.chown(path, 0, 1201)
    with state.engine.connect() as db:
        instance = db.exec_driver_sql(
            "SELECT instance_id FROM application_extension_installations WHERE id=1"
        ).scalar_one()
    state.instance = state.runtime / instance
    # Preparation and activation bind the same isolated SDK endpoint.
    monkeypatch.setenv("THREE_MM_PLATFORM_RUNTIME_SOCKET", str(state.runtime / "platform/platform.sock"))
    state.database = state.instance / "data/state.sqlite3"
    state.data = state.database.parent
    state.key_path = state.transport_keys / (instance + ".key")
    state.calls = []
    state.expected_grant = state.manager.inspect(1)["grant_record_revision"]
    monkeypatch.setattr(locks, "RELEASE_MUTATION_LOCK", tmp_path / "release.lock")
    return state


@ROOT_ONLY
def test_exact_delivered_zip_real_registration_preparation_and_nonroot_start(prepared):
    state = prepared
    with closing(sqlite3.connect(state.database)) as db:
        assert db.execute(
            "SELECT revision FROM three_mm_schema_migrations"
        ).fetchall() == [("0001",)]
        assert db.execute("SELECT COUNT(*) FROM probe_writes").fetchone()[0] == 0
    assert state.database.stat().st_uid == 1200
    request = start_request(state)
    result = update_helper._handle_request(
        request, relational_peer_uid=1202, **state.arguments
    )
    assert result.get("status") == "active_review_required", (result, state.frames)
    assert state.supervisor.starts == 1
    state.supervisor.verify_identity(state.instance.name, 1200, 1201, running=True)
    assert (state.instance / "run/service.sock").is_socket()
    with closing(sqlite3.connect(state.database)) as db:
        assert db.execute("SELECT COUNT(*) FROM probe_writes").fetchone()[0] == 0
    current = review(state)
    assert current["mode"] == "enforced" and current["grant_state"] == "active"
    assert current["installation_status"] == "active"
    # Observe the real protected key and signed host as Core, not as root or
    # with the parent test process's unrelated runtime configuration.
    current = core_status(state)
    assert current["grant_effective"] is True
    assert not current.get("runtime_blockers")


def core_status(state):
    """Actual Core UID read-only status with the installed transport key root."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json; from backend.database import engine; "
            "from backend.services.application_authority_management import configured_manager; "
            "print(json.dumps(configured_manager(engine).inspect(1)))",
        ],
        capture_output=True,
        timeout=30,
        user=1202,
        group=1203,
        extra_groups=(1201,),
        env=dict(
            state.environment, THREE_MM_APPLICATION_KEY_ROOT=str(state.transport_keys)
        ),
    )
    assert result.returncode == 0, result.stderr.decode()
    assert state.token.encode() not in result.stdout + result.stderr
    return json.loads(result.stdout)


def core_call(state, operation, payload=None, request_id=None):
    """Actual Core UID dispatch, not a root-issued permit or HTTP auth proof."""
    script = """
import json, sys, uuid
from sqlalchemy.orm import Session
from backend.database import engine
from backend.db.module import ApplicationExtensionInstallation, ModulePackage
from backend.config import get_settings
from backend.services.application_extensions import invoke_application, ApplicationGatewayError
frame = json.load(sys.stdin)
context = {'audience': 'administrator', 'correlation_id': uuid.uuid4().hex, 'user_id': 1}
if frame['request_id'] is not None:
    context['idempotency_key'] = frame['request_id']
try:
    with Session(engine) as db:
        result = invoke_application(db.get(ApplicationExtensionInstallation, 1),
            db.get(ModulePackage, 1), get_settings().applications, frame['operation'],
            frame['payload'], context, required_audience='administrator')
except ApplicationGatewayError as error:
    # Diagnostics only: no retry or change to the gateway response/assertions.
    # Arbitrary exception text can contain payloads, so expose fixed categories.
    known = {'Relational authority or transaction metadata unavailable',
        'Application extension service is unavailable',
        'Application service message has expired',
        'Application service signature is invalid',
        'Application transport key is unavailable'}
    print(json.dumps({'gateway_diagnostic': {
        'category': str(error) if str(error) in known else 'redacted_gateway_error',
        'phase': error.phase.value,
        'cause_type': type(error.__cause__).__name__}}), file=sys.stderr)
    result = {'gateway_blocked': True}
print(json.dumps(result))
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        input=json.dumps(
            {"operation": operation, "payload": payload or {}, "request_id": request_id}
        ).encode(),
        capture_output=True,
        timeout=30,
        user=1202,
        group=1203,
        extra_groups=(1201,),
        env=dict(
            state.environment, THREE_MM_APPLICATION_KEY_ROOT=str(state.transport_keys)
        ),
    )
    assert result.returncode == 0, result.stderr.decode()
    state.gateway_diagnostic = None
    for line in result.stderr.decode().splitlines():
        if line.startswith('{"gateway_diagnostic":'):
            state.gateway_diagnostic = json.loads(line)["gateway_diagnostic"]
    return json.loads(result.stdout)


@ROOT_ONLY
def test_exact_zip_core_uid_signed_sdk_sql_deduplication_and_revocation(prepared):
    state = prepared
    platform = state.runtime / "platform"
    platform.mkdir(mode=0o750)
    os.chown(platform, 1202, 1201)
    server_script = """
import sys
from pathlib import Path
from backend.services.application_platform import ApplicationPlatformServer
from three_mm_platform_wire import COMPATIBILITY_ACTIONS
server = ApplicationPlatformServer(Path(sys.argv[1]), Path(sys.argv[2]), group='', allowed_actions=COMPATIBILITY_ACTIONS)
server.start()
try:
    sys.stdin.buffer.read()
finally:
    server.stop()
"""
    socket_path = platform / "platform.sock"
    server = subprocess.Popen(
        [
            sys.executable,
            "-c",
            server_script,
            str(socket_path),
            str(state.transport_keys),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        user=1202,
        group=1203,
        extra_groups=(1201,),
        env=state.environment,
    )
    try:
        deadline = time.monotonic() + 10
        while not socket_path.is_socket():
            assert server.poll() is None, server.communicate(timeout=2)[1].decode()
            assert time.monotonic() < deadline
            time.sleep(0.05)
        # Disposable socket group only. No new OS accounts/live permission changes.
        os.chown(socket_path, 1202, 1201)
        result = update_helper._handle_request(
            start_request(state), relational_peer_uid=1202, **state.arguments
        )
        assert result.get("status") == "active_review_required", (result, state.frames)
        assert core_call(state, "db_get")["gateway_blocked"] is True
        reviewed = review(state)
        assert reviewed["mode"] == "enforced" and reviewed["grant_state"] == "active"
        assert core_status(state)["grant_effective"] is True
        initial_read = core_call(state, "db_get")
        assert initial_read.get("status") == "missing", (
            initial_read,
            state.gateway_diagnostic,
        )
        identifier = identity()
        payload = {"request_id": identifier, "text": "signed SDK VM fixture"}
        assert core_call(state, "db_put", payload, identifier)["status"] == "stored"
        assert core_call(state, "db_put", payload, identifier)["status"] == "replayed"
        assert (
            core_call(state, "db_put", {**payload, "text": "changed"}, identifier)[
                "status"
            ]
            == "conflict"
        )
        assert (
            core_call(state, "db_record", {"request_id": identifier})["status"]
            == "found"
        )
        assert core_call(state, "db_boundary") == {"status": "blocked"}
        assert core_call(state, "db_get")["write_count"] == 1
        with closing(sqlite3.connect(state.database)) as db:
            assert (
                db.execute(
                    "SELECT COUNT(*) FROM three_mm_relational_commits"
                ).fetchone()[0]
                == 3
            )
            assert db.execute("SELECT COUNT(*) FROM probe_writes").fetchone()[0] == 1
        revoke_script = """
import sys, uuid
from backend.database import engine
from backend.services.application_authority_management import configured_manager
manager = configured_manager(engine)
manager.revoke(1, actor_token=sys.stdin.buffer.readline().decode().strip(),
    request_id=uuid.uuid4().hex, expected_revision=manager.inspect(1)['grant_record_revision'])
"""
        revoked = subprocess.run(
            [sys.executable, "-c", revoke_script],
            input=state.token.encode() + b"\n",
            capture_output=True,
            timeout=30,
            user=1202,
            group=1203,
            extra_groups=(),
            env=state.environment,
        )
        assert (
            revoked.returncode == 0
            and state.token.encode() not in revoked.stdout + revoked.stderr
        )
        assert core_status(state)["grant_effective"] is False
        assert core_call(state, "db_get") == {"gateway_blocked": True}
        denied = identity()
        assert core_call(
            state, "db_put", {"request_id": denied, "text": "denied"}, denied
        ) == {"gateway_blocked": True}
        with closing(sqlite3.connect(state.database)) as db:
            assert db.execute("SELECT COUNT(*) FROM probe_writes").fetchone()[0] == 1
            assert (
                db.execute(
                    "SELECT COUNT(*) FROM three_mm_relational_commits"
                ).fetchone()[0]
                == 3
            )
    finally:
        state.supervisor.recover_disabled(state.instance.name)
        try:
            server.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.communicate(timeout=3)
