"""Inert registration from absence, real sealed review and Core-UID preparation."""

import hashlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import zipfile

import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from backend.db.application_authority_grant import ApplicationAuthorityAction as Action
from backend.db.application_authority_grant import ApplicationAuthorityGrant as Grant
from backend.db.application_authority_grant import ApplicationNativeReview as Native
from backend.db.audit_log import AuditLog
from backend.db.authority import CoreAuthorityGuard
from backend.db.module import ApplicationConnectorBinding
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.db.module import ApplicationSecretReference, ModulePackage
from backend.db.session import UserSession
from backend.services import application_authority_management as authority
from backend.services import application_relational_registration as registration
from backend.services.application_authority_keys import AuthorityReviewKeyError
from backend.services.application_authority_sources import (
    resolve_installed_authority_sources,
)
from backend.services.module_packages import validate_module_package
from backend.tests.test_application_relational_installation import ROOT_ONLY, identity
from backend.tests.test_application_relational_migrations import script
from backend.tests.test_application_relational_preparation import (
    managed_installed,
    source_installed,
    source_subject,
)
from backend.tests.test_application_relational_production import production, request
from three_mm_application_sdk import ApplicationStorage
from three_mm_protocol.tests.test_application_relational_storage import (
    relational_request,
)
from three_mm_runtime import application_lifecycle as locks
from three_mm_runtime import update_helper

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Real Core-owned keys")


@pytest.fixture
def fresh(managed_installed):
    state = managed_installed
    # Reuse catalog/Core/login fixtures, but remove the old installation BEFORE
    # the tested flow. There are no native reviews/grants/Actions to infer.
    with state.engine.begin() as db:
        db.execute(delete(ApplicationConnectorBinding))
        db.execute(delete(ApplicationSecretReference))
        db.execute(delete(Installation))
    manifest = state.validated.manifest.model_dump(mode="json")
    manifest.update(
        configuration_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        configuration_defaults={},
        permissions=["data.read", "data.write", "process.spawn"],
        capabilities={"provides": [], "consumes": []},
    )
    definition = state.validated.application_extension.model_dump(mode="json")
    definition.update(command_bindings=[], connectors=[])
    definition["service"]["sdk_version"] = "1.3"
    definition["storage"].update(
        relational=relational_request(), schema_revision="0002"
    )
    wheel = io.BytesIO()
    with zipfile.ZipFile(wheel, "w") as target:
        target.writestr("workflow_reference/__init__.py", "")
        target.writestr("workflow_reference/migrations.py", script())
        target.writestr(
            "workflow_reference/service.py", "raise RuntimeError('FACTORY IMPORTED')"
        )
    definition["service"]["artifact_sha256"] = hashlib.sha256(
        wheel.getvalue()
    ).hexdigest()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as target:
        target.writestr("manifest.json", json.dumps(manifest))
        target.writestr("application-extension.json", json.dumps(definition))
        target.writestr(definition["service"]["artifact"], wheel.getvalue())
    state.validated = validate_module_package(output.getvalue())
    state.archive = state.root / "modules" / (state.validated.sha256 + ".zip")
    state.archive.write_bytes(output.getvalue())
    state.configuration = {}
    with state.engine.begin() as db:
        db.execute(
            update(ModulePackage)
            .where(ModulePackage.id == 1)
            .values(
                sha256=state.validated.sha256,
                manifest=manifest,
                size_bytes=len(output.getvalue()),
            )
        )
    return state


def register(state, **changes):
    return registration.register_relational_package(
        state.manager,
        **{
            "package_id": 1,
            "artifact_sha256": state.validated.sha256,
            "configuration": {},
            "actor_token": state.token,
            "request_id": identity(),
            "confirm_register_without_start": True,
            **changes,
        },
    )


def approve(state, identifier):
    proof = state.manager.record_native_review(
        identifier,
        actor_token=state.token,
        request_id=identity(),
        artifact_sha256=state.validated.sha256,
        review_document_sha256="b" * 64,
        native_code_review_completed=True,
        accepts_native_host_risk=True,
    )
    plan = state.manager.create_review(
        identifier,
        actor_token=state.token,
        request_id=identity(),
        native_review_id=proof["native_review_id"],
        scopes=state.manager.inspect(identifier)["scopes"],
    )
    for decision in ("approve", "apply"):
        result = state.manager.decide(
            identifier,
            actor_token=state.token,
            request_id=identity(),
            plan_id=plan["plan_id"],
            expected_revision=plan["revision"],
            fingerprint=plan["fingerprint"],
            decision=decision,
        )
        plan = {**plan, **result}
    return plan


def test_registration_has_no_execution_native_review_grants_or_fake_active_version(
    fresh, monkeypatch
):
    state = fresh
    monkeypatch.setattr(
        ApplicationStorage,
        "migrate",
        lambda *a: pytest.fail("Registration migrated SQLite"),
    )
    result = register(state)
    identifier = result["installation_id"]
    assert (
        result["status"] == "registered_not_started"
        and result["active_version"] is None
    )
    with Session(state.engine) as db:
        row = db.get(Installation, identifier)
        assert (
            row.active_version,
            row.status,
            row.enabled,
            row.authority_mode,
            row.socket_path,
        ) == (None, "disabled", False, "review_required", "pending")
        assert row.activated_at is None and row.health_checked_at is None
        assert db.scalar(select(func.count()).select_from(Grant)) == 0
        assert db.scalar(select(func.count()).select_from(Native)) == 0
        assert db.scalar(select(func.count()).select_from(Action)) == 2
    status = state.manager.inspect(identifier)
    assert status["review_available"] and not status["grant_effective"]
    approve(state, identifier)
    status = state.manager.inspect(identifier)
    assert status["mode"] == "enforced" and status["grant_state"] == "active"
    assert not status["grant_effective"] and not status["installation_enabled"]
    with Session(state.engine) as db:
        assert db.get(Installation, identifier).active_version is None


@pytest.mark.parametrize(
    "changes",
    [
        {"confirm_register_without_start": False},
        {"confirm_register_without_start": 1},
        {"package_id": True},
        {"package_id": 999},
        {"artifact_sha256": "f" * 64},
        {"configuration": {"UNDECLARED": "private"}},
        {"configuration": []},
    ],
)
def test_invalid_request_never_creates_installation_or_journal(fresh, changes):
    with pytest.raises(authority.AuthorityManagementError):
        register(fresh, **changes)
    with Session(fresh.engine) as db:
        assert db.scalar(select(func.count()).select_from(Installation)) == 0
        assert db.scalar(select(func.count()).select_from(Action)) == 0


@pytest.mark.parametrize("actor", ["user", "invalid", "revoked"])
def test_current_real_local_admin_is_required_before_artifact_io(
    fresh, actor, monkeypatch
):
    token = (
        fresh.user_token
        if actor == "user"
        else "invalid" if actor == "invalid" else fresh.token
    )
    if actor == "revoked":
        with fresh.engine.begin() as db:
            db.execute(
                update(UserSession).where(UserSession.id == 1).values(is_active=False)
            )
    monkeypatch.setattr(
        registration,
        "_read_baseline",
        lambda *a: pytest.fail("Invalid actor reached ZIP"),
    )
    with pytest.raises(authority.AuthorityManagementError):
        register(fresh, actor_token=token)


def test_unknown_completion_can_only_return_historical_receipt_not_reregister(fresh):
    request_id = identity()
    first = register(fresh, request_id=request_id)
    with Session(fresh.engine) as db:
        guard = db.get(CoreAuthorityGuard, 1).revision
    second = register(fresh, request_id=request_id)
    assert second == {**first, "historical": True, "replayed": True}
    with Session(fresh.engine) as db:
        assert db.get(CoreAuthorityGuard, 1).revision == guard
    with pytest.raises(
        authority.AuthorityManagementError, match="existing_installation"
    ):
        register(fresh)
    with pytest.raises(authority.AuthorityManagementError):
        register(fresh, request_id=request_id, actor_token=fresh.user_token)


@pytest.mark.parametrize(
    "status", ["staged", "failed", "recovery_required", "disabled"]
)
def test_ordinary_never_active_records_remain_unreviewable(fresh, status):
    with Session(fresh.engine) as db, db.begin():
        row = Installation(
            module_id=fresh.validated.manifest.module_id,
            module_package_id=1,
            instance_id="a" * 24,
            status=status,
            enabled=False,
            socket_path="pending",
            configuration={},
        )
        db.add(row)
        db.flush()
        identifier = row.id
    with pytest.raises(authority.AuthorityManagementError):
        fresh.manager.inspect(identifier)
    with pytest.raises(
        authority.AuthorityManagementError, match="existing_installation"
    ):
        register(fresh)


@pytest.mark.parametrize(
    "drift",
    ["seal", "configuration", "incarnation", "instance", "key", "compatibility"],
)
def test_provenance_is_exact_and_unsigned_pointer_or_old_key_is_not_authority(
    fresh, drift
):
    result = register(fresh)
    identifier = result["installation_id"]
    with Session(fresh.engine) as db, db.begin():
        if drift == "seal":
            db.get(Action, result["registration_id"]).seal = "0" * 64
        elif drift == "configuration":
            db.get(Installation, identifier).configuration = {"UNDECLARED": "private"}
        elif drift == "incarnation":
            db.get(Installation, identifier).authority_incarnation = identity()
        elif drift == "instance":
            db.get(Installation, identifier).instance_id = "f" * 24
        elif drift == "compatibility":
            db.get(Installation, identifier).authority_mode = "compatibility"
    if drift == "key":
        fresh.keys.rotate(expected_key_id=fresh.keys.identity().key_id)
    try:
        status = fresh.manager.inspect(identifier)
    except (authority.AuthorityManagementError, AuthorityReviewKeyError, ValueError):
        pass
    else:
        # Status may describe a blocked installation; it must expose no
        # reviewable subject, scopes, native trust or effective permissions.
        assert not status["review_available"] and not status["grant_effective"]
        assert not status["scopes"] and not status["native_reviews"]
        assert status["review_blockers"]
    with pytest.raises(
        (authority.AuthorityManagementError, AuthorityReviewKeyError, ValueError)
    ):
        fresh.manager.record_native_review(
            identifier,
            actor_token=fresh.token,
            request_id=identity(),
            artifact_sha256=fresh.validated.sha256,
            review_document_sha256="b" * 64,
            native_code_review_completed=True,
            accepts_native_host_risk=True,
        )


@pytest.mark.parametrize("problem", ["bytes", "symlink", "key"])
def test_missing_or_changed_trusted_sources_never_create_provenance(fresh, problem):
    if problem == "bytes":
        fresh.archive.write_bytes(b"not the uploaded ZIP")
    elif problem == "symlink":
        saved = fresh.archive.with_suffix(".saved")
        fresh.archive.rename(saved)
        fresh.archive.symlink_to(saved)
    else:
        from backend.services.application_authority_keys import KEY_NAME

        (fresh.key_directory / KEY_NAME).rename(fresh.key_directory / "saved-key")
    with pytest.raises(authority.AuthorityManagementError):
        register(fresh)
    with Session(fresh.engine) as db:
        assert db.scalar(select(func.count()).select_from(Installation)) == 0
        assert db.scalar(select(func.count()).select_from(Action)) == 0


def test_duplicate_request_id_cannot_select_a_different_uploaded_package(fresh):
    request_id = identity()
    register(fresh, request_id=request_id)
    with Session(fresh.engine) as db, db.begin():
        db.get(ModulePackage, 1).id = 2
    with pytest.raises(authority.AuthorityManagementError, match="request_conflict"):
        register(fresh, package_id=2, request_id=request_id)


def test_unsupported_platform_declaration_rolls_back_inert_registration(fresh):
    definition = fresh.validated.application_extension.model_dump(mode="json")
    # Public identity reads now have a scoped adapter; signing/proof still does not.
    definition["platform_permissions"] = ["installation.identity.prove"]
    manifest = fresh.validated.manifest.model_dump(mode="json")
    manifest["permissions"].append("installation.identity.prove")
    output = io.BytesIO()
    with zipfile.ZipFile(fresh.archive) as old, zipfile.ZipFile(output, "w") as target:
        target.writestr("manifest.json", json.dumps(manifest))
        target.writestr("application-extension.json", json.dumps(definition))
        target.writestr(
            definition["service"]["artifact"],
            old.read(definition["service"]["artifact"]),
        )
    fresh.validated = validate_module_package(output.getvalue())
    fresh.archive = fresh.root / "modules" / (fresh.validated.sha256 + ".zip")
    fresh.archive.write_bytes(output.getvalue())
    with fresh.engine.begin() as db:
        db.execute(
            update(ModulePackage).values(
                sha256=fresh.validated.sha256, size_bytes=len(output.getvalue())
            )
        )
    with pytest.raises(
        authority.AuthorityManagementError, match="unsupported_authority"
    ):
        register(fresh)
    with Session(fresh.engine) as db:
        assert db.scalar(select(func.count()).select_from(Installation)) == 0
        assert db.scalar(select(func.count()).select_from(Action)) == 0


def test_registration_write_is_atomic_and_does_not_put_configuration_or_token_in_audit(
    fresh, monkeypatch
):
    original = authority._save

    def failed(db, key, kind, row, value):
        if value["state"] == "recorded":
            raise OSError("lost metadata write")
        return original(db, key, kind, row, value)

    with monkeypatch.context() as patch:
        patch.setattr(authority, "_save", failed)
        with pytest.raises(authority.AuthorityManagementError):
            register(fresh)
    with Session(fresh.engine) as db:
        assert db.scalar(select(func.count()).select_from(Installation)) == 0
        assert db.scalar(select(func.count()).select_from(Action)) == 0
    result = register(fresh)
    with Session(fresh.engine) as db:
        audit = db.scalars(
            select(AuditLog).where(AuditLog.action == "APPLICATION_RELATIONAL_REGISTER")
        ).one()
        assert fresh.token not in json.dumps(audit.changes)
        assert audit.changes["installation_id"] == result["installation_id"]


def test_readonly_source_adapter_without_key_cannot_promote_registration(fresh):
    result = register(fresh)
    source = resolve_installed_authority_sources(
        fresh.engine,
        result["installation_id"],
        uploads_root=fresh.root,
        core_version="0.3.0",
    )
    assert not source.sources_resolved and source.principal is None


def test_keyed_readonly_subject_accepts_exact_registration_without_approving(fresh):
    from backend.services.application_authority_subjects import (
        resolve_installed_policy_subject,
    )

    result = register(fresh)
    subject = resolve_installed_policy_subject(
        fresh.engine,
        result["installation_id"],
        uploads_root=fresh.root,
        core_version="0.3.0",
        review_key_directory=fresh.key_directory,
    )
    assert subject.subject is not None, subject
    assert subject.subject.relational and not subject.reviewable
    assert subject.permission_approval == "not_evaluated"


def test_local_admin_cli_registers_without_helper_or_runtime(fresh):
    environment = dict(
        os.environ,
        DATABASE_URL=str(fresh.engine.url),
        UPLOADS_DIR=str(fresh.root),
        THREE_MM_AUTHORITY_REVIEW_KEY_DIR=str(fresh.key_directory),
        THREE_MM_APPLICATION_HELPER_SOCKET="/nonexistent-unused-helper.sock",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "backend.services.application_authority_admin",
            "register-relational",
            "--package-id",
            "1",
            "--artifact-sha256",
            fresh.validated.sha256,
            "--request-id",
            identity(),
            "--confirm-register-without-start",
        ],
        input=fresh.token.encode() + b"\n",
        capture_output=True,
        env=environment,
        start_new_session=True,
        timeout=25,
    )
    assert result.returncode == 0, result.stderr.decode()
    assert json.loads(result.stdout)["status"] == "registered_not_started"
    assert fresh.token.encode() not in result.stdout + result.stderr


@pytest.fixture
def initial(fresh, tmp_path, monkeypatch):
    state = fresh
    result = register(state)
    assert result["installation_id"] == 1
    approve(state, 1)
    for directory in (tmp_path, tmp_path.parent, tmp_path.parent.parent):
        directory.chmod(0o755)
    state.runtime, state.transport_keys, state.helper_state = (
        tmp_path / "runtime",
        tmp_path / "transport-keys",
        tmp_path / "helper-state",
    )
    for path in (state.runtime, state.transport_keys, state.helper_state):
        path.mkdir(mode=0o750)
    if os.geteuid() == 0:
        os.chown(state.runtime, 0, 1201)
    with Session(state.engine) as db:
        state.instance = state.runtime / db.get(Installation, 1).instance_id
    state.database = state.instance / "data" / "state.sqlite3"
    state.key_path = state.transport_keys / (state.instance.name + ".key")
    state.calls = []
    state.expected_grant = state.manager.inspect(1)["grant_record_revision"]
    monkeypatch.setattr(locks, "RELEASE_MUTATION_LOCK", tmp_path / "release.lock")
    return state


@ROOT_ONLY
def test_from_absence_through_real_review_and_core_uid_helper_to_prepared_db(
    production,
):
    state = production
    result = update_helper._handle_request(
        request(state), relational_peer_uid=1202, **state.arguments
    )
    assert result["ok"] is True, result
    assert result["status"] == "prepared_not_started"
    with sqlite3.connect(state.database) as db:
        assert db.execute(
            "SELECT revision FROM three_mm_schema_migrations"
        ).fetchall() == [("0001",), ("0002",)]
    with Session(state.engine) as db:
        row = db.get(Installation, 1)
        assert (
            row.active_version is None and not row.enabled and row.status == "disabled"
        )
