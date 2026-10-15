"""Inert candidate adoption through real Core seals, never test-only rebinding.

Metadata cases use accepted test callback receipts. The separate Root process
case performs actual start/stop and forward migration on disposable paths only.
"""

import hashlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import zipfile

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.db.application_authority_grant import ApplicationAuthorityAction as Action
from backend.db.application_authority_grant import ApplicationAuthorityGrant as Grant
from backend.db.application_authority_grant import ApplicationNativeReview as Native
from backend.db.audit_log import AuditLog
from backend.db.authority import CoreAuthorityGuard
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.db.module import ModulePackage
from backend.db.session import UserSession
from backend.services import application_authority_management as authority
from backend.services import application_relational_candidate as coordinator
from backend.services.application_authority_sources import (
    resolve_installed_authority_sources,
)
from backend.services.module_packages import validate_module_package
from backend.tests.test_application_relational_activation import (
    checkpoint as start_checkpoint,
)
from backend.tests.test_application_relational_activation import issue as issue_start
from backend.tests.test_application_relational_activation import (
    journal,
    migratable,
    physical,
    prepared,
    prepared_paths,
)
from backend.tests.test_application_relational_activation import (
    receipt as start_receipt,
)
from backend.tests.test_application_relational_activation import (
    start,
    tmp_path,
)
from backend.tests.test_application_relational_activation_recovery import (
    checkpoint as stop_checkpoint,
)
from backend.tests.test_application_relational_activation_recovery import (
    issue as issue_stop,
)
from backend.tests.test_application_relational_activation_recovery import (
    receipt as stop_receipt,
)
from backend.tests.test_application_relational_activation_recovery import (
    recover,
)
from backend.tests.test_application_relational_preparation import (
    ROOT_ONLY,
    SECRET,
    apply,
    identity,
    managed_installed,
    native,
    source_installed,
    source_subject,
    stopped,
)
from backend.tests.test_application_relational_upgrade import issue as issue_upgrade
from backend.tests.test_application_relational_upgrade import run as run_upgrade

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Real Core-owned seals")


def upload(
    state,
    *,
    version="1.1.0",
    revision="0002",
    code=None,
    unsupported=False,
    **definition_changes,
):
    """Upload catalog bytes only; never change the installed binding or grant."""
    manifest = state.validated.manifest.model_dump(mode="json")
    definition = state.validated.application_extension.model_dump(mode="json")
    manifest["version"] = definition["version"] = version
    if unsupported:
        manifest["dependencies"] = {"org.example.dependency": ">=1.0.0"}
    definition["storage"]["schema_revision"] = revision
    definition.update(definition_changes)
    with zipfile.ZipFile(state.archive) as old:
        wheel = old.read(definition["service"]["artifact"])
    if code is not None:
        buffer = io.BytesIO()
        migration_module = definition["storage"]["migration_entrypoint"].split(":")[0]
        service_module = definition["service"]["entrypoint"].split(":")[0]
        with zipfile.ZipFile(buffer, "w") as target:
            parents = set()
            for module in (migration_module, service_module):
                parts = module.split(".")[:-1]
                parents.update(
                    "/".join(parts[:i]) + "/__init__.py"
                    for i in range(1, len(parts) + 1)
                )
            for path in sorted(parents):
                target.writestr(path, "")
            target.writestr(migration_module.replace(".", "/") + ".py", code)
            target.writestr(
                service_module.replace(".", "/") + ".py",
                "raise RuntimeError('FACTORY IMPORTED')",
            )
        wheel = buffer.getvalue()
        definition["service"]["artifact_sha256"] = hashlib.sha256(wheel).hexdigest()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as target:
        target.writestr("manifest.json", json.dumps(manifest))
        target.writestr("application-extension.json", json.dumps(definition))
        target.writestr(definition["service"]["artifact"], wheel)
    validated = validate_module_package(buffer.getvalue())
    archive = state.root / "modules" / (validated.sha256 + ".zip")
    archive.write_bytes(buffer.getvalue())
    with Session(state.engine) as db, db.begin():
        row = ModulePackage(
            module_id=manifest["module_id"],
            version=version,
            manifest=manifest,
            sha256=validated.sha256,
            size_bytes=len(buffer.getvalue()),
            file_path="/not/a/caller/selected/path",
        )
        db.add(row)
        db.flush()
        identifier = row.id
    state.target = identifier, validated, archive
    return state.target


@pytest.fixture
def candidate(prepared):
    state = prepared
    state.start = issue_start(state, state.source)
    start_checkpoint(state, state.start, "begin")
    start_checkpoint(state, state.start, "finish", receipt=start_receipt(state.start))
    state.stop = issue_stop(state, state.start)
    stop_checkpoint(state, state.stop, "begin")
    stop_checkpoint(state, state.stop, "finish", receipt=stop_receipt(state.stop))
    state.stop_revision = journal(state, state.stop)["revision"]
    upload(state)
    return state


def adopt(state, **changes):
    return coordinator.adopt_relational_version(
        state.manager,
        1,
        **{
            "actor_token": state.token,
            "request_id": identity(),
            "package_id": state.target[0],
            "artifact_sha256": state.target[1].sha256,
            "expected_current_artifact_sha256": state.validated.sha256,
            "source_recovery_id": state.stop["preparation_id"],
            "expected_recovery_revision": state.stop_revision,
            "confirm_adopt_without_execution": True,
            **changes,
        },
    )


def snapshot(state):
    with Session(state.engine) as db:
        row = db.get(Installation, 1)
        return {
            "installation": tuple(
                getattr(row, name)
                for name in (
                    "module_package_id",
                    "previous_package_id",
                    "active_version",
                    "status",
                    "enabled",
                    "instance_id",
                    "authority_incarnation",
                    "authority_epoch",
                    "authority_mode",
                    "socket_path",
                )
            ),
            "configuration": json.dumps(row.configuration, sort_keys=True),
            "grant": db.get(Grant, 1).payload,
            "native": list(db.execute(select(Native.review_id, Native.payload))),
            "journal": list(
                db.execute(select(Action.request_id, Action.payload, Action.seal))
            ),
            "guard": db.get(CoreAuthorityGuard, 1).revision,
        }


def test_candidate_is_inert_preserves_owner_history_and_requires_new_trust(candidate):
    state = candidate
    before = snapshot(state)
    old_stop = journal(state, state.stop)
    result = adopt(state)
    assert result["status"] == "candidate_not_started"
    assert (
        result["active_version"] is None
        and result["permission_approval"] == "not_evaluated"
    )
    assert result["source_preparation_id"] == state.source["preparation_id"]
    after = snapshot(state)
    assert after["configuration"] == before["configuration"]
    assert after["grant"] == before["grant"] and after["native"] == before["native"]
    # Instance/incarnation stay fixed; epoch changes and no active version is invented.
    assert after["installation"][5:7] == before["installation"][5:7]
    assert after["installation"][7] != before["installation"][7]
    assert after["installation"][:5] == (state.target[0], 1, None, "disabled", False)
    current_stop = journal(state, state.stop)
    assert current_stop["data"]["result"] == old_stop["data"]["result"]
    assert current_stop["data"]["receipt"] == old_stop["data"]["receipt"]
    assert current_stop["state"] == old_stop["state"] == "confirmed"
    status = state.manager.inspect(1)
    assert status["artifact_sha256"] == state.target[1].sha256
    assert status["review_available"] and not status["grant_effective"]
    assert not status["native_reviews"]
    unkeyed = resolve_installed_authority_sources(
        state.engine, 1, uploads_root=state.root, core_version="0.3.0"
    )
    assert not unkeyed.sources_resolved and unkeyed.principal is None
    with pytest.raises(authority.AuthorityManagementError):
        state.manager.create_review(
            1,
            actor_token=state.token,
            request_id=identity(),
            native_review_id=state.native_id,
            scopes=status["scopes"],
        )
    state.validated, state.archive = state.target[1:]
    proof = native(state)
    apply(state, proof["native_review_id"])
    assert state.manager.inspect(1)["mode"] == "enforced"
    assert not state.manager.inspect(1)["grant_effective"]


@pytest.mark.parametrize(
    "changes",
    [
        {"confirm_adopt_without_execution": False},
        {"confirm_adopt_without_execution": 1},
        {"package_id": True},
        {"package_id": 2**80},
        {"package_id": 999},
        {"installation_id": True},
        {"installation_id": 2**80},
        {"artifact_sha256": "0" * 64},
        {"expected_current_artifact_sha256": "1" * 64},
        {"expected_recovery_revision": "2" * 32},
        {"source_recovery_id": "3" * 32},
        {"request_id": "bad"},
        {"actor_token": "invalid"},
    ],
)
def test_invalid_candidate_request_is_atomic(candidate, changes):
    before = snapshot(candidate)
    if "installation_id" in changes:
        with pytest.raises(authority.AuthorityManagementError):
            coordinator.adopt_relational_version(
                candidate.manager,
                changes["installation_id"],
                actor_token=candidate.token,
                request_id=identity(),
                package_id=candidate.target[0],
                artifact_sha256=candidate.target[1].sha256,
                expected_current_artifact_sha256=candidate.validated.sha256,
                source_recovery_id=candidate.stop["preparation_id"],
                expected_recovery_revision=candidate.stop_revision,
                confirm_adopt_without_execution=True,
            )
    else:
        with pytest.raises(authority.AuthorityManagementError):
            adopt(candidate, **changes)
    assert snapshot(candidate) == before


@pytest.mark.parametrize("who", ["user", "revoked"])
def test_authentication_precedes_uploaded_artifact_io(candidate, who, monkeypatch):
    token = candidate.user_token if who == "user" else candidate.token
    if who == "revoked":
        with candidate.engine.begin() as db:
            db.execute(update(UserSession).values(is_active=False))
    monkeypatch.setattr(
        coordinator, "_read_baseline", lambda *a: pytest.fail("Invalid actor read ZIP")
    )
    with pytest.raises(authority.AuthorityManagementError):
        adopt(candidate, actor_token=token)


@pytest.mark.parametrize(
    "problem",
    [
        "seal",
        "epoch",
        "enabled",
        "mode",
        "incarnation",
        "generation",
        "configuration",
        "stop_unconfirmed",
        "reserved",
        "bytes",
        "link",
        "configuration_schema",
        "same_schema",
        "unsupported",
    ],
)
def test_changed_candidate_or_stop_evidence_never_switches_binding(candidate, problem):
    state = candidate
    if problem in {"bytes", "link"}:
        if problem == "bytes":
            state.target[2].write_bytes(b"changed")
        else:
            saved = state.target[2].with_suffix(".saved")
            state.target[2].rename(saved)
            state.target[2].symlink_to(saved)
    elif problem in {"configuration_schema", "same_schema", "unsupported"}:
        # New uploaded versions; still never change the installation in the fixture.
        if problem == "same_schema":
            upload(state, version="1.2.0", revision=state.source["schema_revision"])
        elif problem == "unsupported":
            upload(state, version="1.2.0", unsupported=True)
        else:
            with state.engine.begin() as db:
                db.execute(
                    update(Installation).values(configuration={"UNDECLARED": "private"})
                )
    elif problem in {"stop_unconfirmed", "reserved"}:
        with state.keys.locked() as key, Session(state.engine) as db, db.begin():
            row = db.get(Action, state.stop["preparation_id"])
            value = authority._load(db, key, "action", row, row.request_id)
            if problem == "stop_unconfirmed":
                value["state"] = "execution_unconfirmed"
            else:
                value["data"]["reactivation_id"] = identity()
            authority._save(db, key, "action", row, value)
    else:
        with state.engine.begin() as db:
            if problem == "seal":
                db.execute(
                    update(Action)
                    .where(Action.request_id == state.stop["preparation_id"])
                    .values(seal="0" * 64)
                )
            elif problem == "generation":
                db.execute(update(CoreAuthorityGuard).values(generation=identity()))
            else:
                db.execute(
                    update(Installation).values(
                        **{
                            "epoch": {"authority_epoch": identity()},
                            "enabled": {"status": "active", "enabled": True},
                            "mode": {"authority_mode": "compatibility"},
                            "incarnation": {"authority_incarnation": identity()},
                            "configuration": {
                                "configuration": {
                                    **state.configuration,
                                    "PRIVATE_NOTE": "changed",
                                }
                            },
                        }[problem]
                    )
                )
    before = snapshot(state)
    with pytest.raises(authority.AuthorityManagementError):
        adopt(state)
    assert snapshot(state) == before


def test_lost_reply_is_only_historical_receipt_and_cannot_select_other_candidate(
    candidate,
):
    state = candidate
    request_id = identity()
    first = adopt(state, request_id=request_id)
    before = snapshot(state)
    assert adopt(state, request_id=request_id) == {
        **first,
        "historical": True,
        "replayed": True,
    }
    assert snapshot(state) == before
    upload(state, version="1.2.0")
    with pytest.raises(authority.AuthorityManagementError):
        adopt(state, request_id=request_id)
    assert snapshot(state) == before


def test_failed_provenance_write_rolls_back_all_metadata(candidate, monkeypatch):
    state = candidate
    before = snapshot(state)
    original = authority._save

    def fail(db, key, kind, row, value):
        if (
            value["state"] == "recorded"
            and value["data"].get("operation") == coordinator.OPERATION
        ):
            raise OSError("Cannot commit action")
        return original(db, key, kind, row, value)

    monkeypatch.setattr(authority, "_save", fail)
    with pytest.raises(authority.AuthorityManagementError):
        adopt(state)
    assert snapshot(state) == before


@pytest.mark.parametrize("drift", ["actor", "catalog", "configuration", "epoch", "key"])
def test_authoritative_transaction_rechecks_after_artifact_read(
    candidate, monkeypatch, drift
):
    state = candidate
    read = coordinator._read_baseline

    def changed(*args, **kwargs):
        package = read(*args, **kwargs)
        if drift == "key":
            state.keys.rotate(expected_key_id=state.keys.identity().key_id)
        else:
            with state.engine.begin() as db:
                if drift == "actor":
                    db.execute(update(UserSession).values(is_active=False))
                elif drift == "catalog":
                    db.execute(
                        update(ModulePackage)
                        .where(ModulePackage.id == state.target[0])
                        .values(version="99.0.0")
                    )
                elif drift == "configuration":
                    db.execute(
                        update(Installation).values(
                            configuration={"UNDECLARED": "changed"}
                        )
                    )
                else:
                    db.execute(update(Installation).values(authority_epoch=identity()))
        state.after_drift = snapshot(state)
        return package

    monkeypatch.setattr(coordinator, "_read_baseline", changed)
    with pytest.raises(authority.AuthorityManagementError):
        adopt(state)
    assert snapshot(state) == state.after_drift


@pytest.mark.parametrize(
    "problem", ["older_version", "same_base_build", "wrong_module", "budget"]
)
def test_local_candidate_gates_are_enforced_not_only_version_helper(
    candidate, problem, monkeypatch
):
    state = candidate
    if problem == "older_version":
        upload(state, version="0.9.0")
    elif problem == "same_base_build":
        upload(state, version="1.0.0+new-build")
    elif problem == "wrong_module":
        with state.engine.begin() as db:
            db.execute(
                update(ModulePackage)
                .where(ModulePackage.id == state.target[0])
                .values(module_id="org.example.foreign")
            )
    else:
        monkeypatch.setattr(coordinator, "MAX_PREPARATION_ACTIONS", 1)
    before = snapshot(state)
    with pytest.raises(authority.AuthorityManagementError):
        adopt(state)
    assert snapshot(state) == before


@pytest.mark.parametrize("problem", ["key", "binding", "previous_package"])
def test_inert_candidate_provenance_is_not_unsigned_authority(candidate, problem):
    state = candidate
    result = adopt(state)
    if problem == "key":
        state.keys.rotate(expected_key_id=state.keys.identity().key_id)
    else:
        with state.engine.begin() as db:
            if problem == "binding":
                db.execute(
                    update(Action)
                    .where(Action.request_id == result["registration_id"])
                    .values(seal="0" * 64)
                )
            else:
                db.execute(update(Installation).values(previous_package_id=None))
    with pytest.raises((authority.AuthorityManagementError, ValueError)):
        state.manager.record_native_review(
            1,
            actor_token=state.token,
            request_id=identity(),
            artifact_sha256=state.target[1].sha256,
            review_document_sha256="b" * 64,
            native_code_review_completed=True,
            accepts_native_host_risk=True,
        )


@pytest.mark.parametrize(
    "old,new,allowed",
    [
        ("1.0.0", "1.1.0", True),
        ("1.0.0", "0.9.9", False),
        ("1.0.0", "1.0.0+other", False),
        ("1.0.0", "1.0.0-beta.9", False),
        ("1.1.0-beta.2", "1.1.0-beta.10", True),
        ("1.1.0-rc.1", "1.1.0", True),
    ],
)
def test_version_order_excludes_downgrades_and_build_only_switches(old, new, allowed):
    assert (coordinator._version_key(new) > coordinator._version_key(old)) is allowed


def test_cli_adopts_without_helper_and_does_not_log_token(candidate):
    state = candidate
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "backend.services.application_authority_admin",
            "adopt-relational-version",
            "--installation-id",
            "1",
            "--package-id",
            str(state.target[0]),
            "--artifact-sha256",
            state.target[1].sha256,
            "--expected-current-artifact-sha256",
            state.validated.sha256,
            "--source-recovery-id",
            state.stop["preparation_id"],
            "--expected-recovery-revision",
            state.stop_revision,
            "--request-id",
            identity(),
            "--confirm-adopt-without-execution",
        ],
        input=state.token.encode() + b"\n",
        capture_output=True,
        timeout=25,
        start_new_session=True,
        env=dict(
            os.environ,
            DATABASE_URL=str(state.engine.url),
            UPLOADS_DIR=str(state.root),
            THREE_MM_AUTHORITY_REVIEW_KEY_DIR=str(state.key_directory),
            THREE_MM_APPLICATION_HELPER_SOCKET="/not-used.sock",
        ),
    )
    assert result.returncode == 0, result.stderr.decode()
    assert json.loads(result.stdout)["status"] == "candidate_not_started"
    assert state.token.encode() not in result.stdout + result.stderr
    with Session(state.engine) as db:
        audit = db.scalars(
            select(AuditLog).where(
                AuditLog.action == "APPLICATION_AUTHORITY_RELATIONAL_CANDIDATE_ADOPTION"
            )
        ).one()
        assert state.token not in json.dumps(audit.changes)
        assert "configuration" not in audit.changes


@ROOT_ONLY
@pytest.mark.parametrize("outcome", ["success", "database_detached", "publication"])
def test_real_nonroot_start_stop_adoption_review_and_upgrade_without_binding_seed(
    physical,
    monkeypatch,
    outcome,
):
    state = physical
    state.start = issue_start(state, state.source)
    start(state, state.start)
    state.stop = issue_stop(state, state.start)
    recover(state, state.stop)
    state.stop_revision = journal(state, state.stop)["revision"]
    state.source_revision = journal(state, state.source)["revision"]
    state.source_archive = state.archive
    before = {
        path: path.read_bytes()
        for path in (
            state.instance / "active.json",
            state.instance / "relational.json",
            state.transport_keys / (state.instance.name + ".key"),
        )
    }
    upload(
        state,
        revision="0003",
        code="""import os
from three_mm_application_sdk import ApplicationMigration
def applied(db):
    raise RuntimeError('Applied prefix replayed')
def third(db):
    assert os.geteuid() == 1200
    db.execute('ALTER TABLE business ADD COLUMN third INTEGER DEFAULT 3')
def get_migrations():
    return [ApplicationMigration('0001', applied), ApplicationMigration('0002', applied), ApplicationMigration('0003', third)]
""",
    )
    adopt(state)
    assert all(path.read_bytes() == value for path, value in before.items())
    state.validated, state.archive = state.target[1:]
    # No new code trust was fabricated by upload/adoption.
    with pytest.raises(authority.AuthorityManagementError):
        issue_upgrade(state)
    proof = native(state)
    apply(state, proof["native_review_id"])

    class StoppedProcessSupervisor:
        def stop(self, instance):
            state.actual_supervisor.recover_disabled(instance)
            state.actual_supervisor.verify_identity(instance, 1200, 1201, running=False)

    state.supervisor = StoppedProcessSupervisor()
    if outcome != "success":
        from backend.tests import (
            test_application_relational_upgrade_restore as restore_cases,
        )

        restore_cases.partial(state, monkeypatch, point=outcome)
        ticket = restore_cases.issue(state)
        monkeypatch.setattr(
            restore_cases.upgrade_helper,
            "run_prepared_upgrade_migrations",
            lambda *a, **kw: pytest.fail("Restore replayed migration"),
        )
        result = restore_cases.rollback_cases.run(state, ticket)
        assert result["outcome"] == "restored_not_started"
        assert journal(state, state.failed)["state"] == "execution_unconfirmed"
        assert journal(state, ticket)["state"] == "confirmed"
        assert all(path.read_bytes() == value for path, value in before.items())
        with sqlite3.connect(state.database) as db:
            assert db.execute("SELECT value FROM business").fetchall() == [
                ("preserved",)
            ]
            assert db.execute(
                "SELECT revision FROM three_mm_schema_migrations ORDER BY rowid"
            ).fetchall() == [("0001",), ("0002",)]
        assert not list(state.instance.glob(".database-*.rollback"))
        assert (
            state.actual_supervisor.process is None
            and state.actual_supervisor.starts == 1
        )
        assert not state.manager.inspect(1)["grant_effective"]
        return
    ticket = issue_upgrade(state)
    result = run_upgrade(state, ticket)
    assert result["outcome"] == "upgraded_not_started"
    with sqlite3.connect(state.database) as db:
        assert db.execute("SELECT value,third FROM business").fetchall() == [
            ("preserved", 3)
        ]
        assert db.execute(
            "SELECT revision FROM three_mm_schema_migrations ORDER BY rowid"
        ).fetchall() == [("0001",), ("0002",), ("0003",)]
        assert db.execute("SELECT COUNT(*) FROM three_mm_outbox").fetchone() == (1,)
    assert before[state.transport_keys / (state.instance.name + ".key")] == SECRET
    assert (
        state.actual_supervisor.process is None and state.actual_supervisor.starts == 1
    )
    assert not state.manager.inspect(1)["grant_effective"]
