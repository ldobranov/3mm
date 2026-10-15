"""Closed legacy evidence must not block a separately consented upgraded start.

Disposable Root/non-root processes only. No live VM units, grants or data.
"""

import hashlib
import io
import json
import os
import sqlite3
import zipfile

import pytest
from sqlalchemy.orm import Session

from backend.db.module import ModulePackage
from backend.services import application_authority_management as authority
from backend.services.module_packages import validate_module_package
from backend.tests.test_application_relational_activation import (
    checkpoint as start_checkpoint,
)
from backend.tests.test_application_relational_activation import issue as issue_start
from backend.tests.test_application_relational_activation import (
    journal,
    migratable,
    physical,
    prepared_paths,
    start,
    tmp_path,
)
from backend.tests.test_application_relational_activation_recovery import (
    Crash,
    crash_start,
)
from backend.tests.test_application_relational_activation_recovery import (
    issue as issue_stop,
)
from backend.tests.test_application_relational_activation_recovery import recover
from backend.tests.test_application_relational_candidate import adopt
from backend.tests.test_application_relational_preparation import (
    ROOT_ONLY,
    SECRET,
    apply,
    managed_installed,
    native,
    source_installed,
    source_subject,
    stopped,
)
from backend.tests.test_application_relational_reactivation import (
    issue as issue_restart,
)
from backend.tests.test_application_relational_runtime import invoke
from backend.tests.test_application_relational_upgrade import issue as issue_upgrade
from backend.tests.test_application_relational_upgrade import run as run_upgrade
from three_mm_application_sdk.relational_wire import canonical, sign_metadata
from three_mm_runtime import application_relational_activation_recovery as recovery

pytestmark = [
    pytest.mark.skipif(os.name != "posix", reason="Actual protected POSIX evidence"),
    ROOT_ONLY,
]


def upload_startable_upgrade(state):
    """Catalog fixture only; preserve service code, append upgrade-only schema 0003."""
    manifest = state.validated.manifest.model_dump(mode="json")
    definition = state.validated.application_extension.model_dump(mode="json")
    manifest["version"] = definition["version"] = "1.1.0"
    definition["storage"]["schema_revision"] = "0003"
    migration = definition["storage"]["migration_entrypoint"].split(":")[0]
    migration_path = migration.replace(".", "/") + ".py"
    with zipfile.ZipFile(state.archive) as package:
        original = package.read(definition["service"]["artifact"])
    wheel = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(original)) as source,
        zipfile.ZipFile(wheel, "w") as target,
    ):
        for name in source.namelist():
            payload = source.read(name)
            if name == migration_path:
                payload = b"""import os
from three_mm_application_sdk import ApplicationMigration
def applied(db):
    raise RuntimeError('Applied migration replayed')
def third(db):
    assert os.geteuid() == 1200
    db.execute('ALTER TABLE business ADD COLUMN third INTEGER DEFAULT 3')
def get_migrations():
    return [ApplicationMigration('0001', applied), ApplicationMigration('0002', applied), ApplicationMigration('0003', third)]
"""
            target.writestr(name, payload)
    definition["service"]["artifact_sha256"] = hashlib.sha256(
        wheel.getvalue()
    ).hexdigest()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as package:
        package.writestr("manifest.json", json.dumps(manifest))
        package.writestr("application-extension.json", json.dumps(definition))
        package.writestr(definition["service"]["artifact"], wheel.getvalue())
    blob = output.getvalue()
    validated = validate_module_package(blob)
    archive = state.root / "modules" / (validated.sha256 + ".zip")
    archive.write_bytes(blob)
    with Session(state.engine) as db, db.begin():
        row = ModulePackage(
            module_id=manifest["module_id"],
            version="1.1.0",
            manifest=manifest,
            sha256=validated.sha256,
            size_bytes=len(blob),
            file_path="/catalog-only/not-an-installation-binding",
        )
        db.add(row)
        db.flush()
        identifier = row.id
    state.target = identifier, validated, archive


@pytest.fixture
def upgraded_after_recovered_start(physical):
    state = physical
    old_start = crash_start(state, "begin")
    state.stop = issue_stop(state, old_start)
    recover(state, state.stop)
    state.stop_revision = journal(state, state.stop)["revision"]
    state.source_archive = state.archive
    upload_startable_upgrade(state)
    adopt(state)  # Real inert writer, not an installed-binding SQL edit.
    state.validated, state.archive = state.target[1:]
    state.source_revision = journal(state, state.source)["revision"]
    proof = native(state)
    state.native_id = proof["native_review_id"]
    apply(state, state.native_id)

    class StoppedSupervisor:
        def stop(self, instance):
            state.actual_supervisor.recover_disabled(instance)
            state.actual_supervisor.verify_identity(instance, 1200, 1201, running=False)

    state.supervisor = StoppedSupervisor()
    upgrade = issue_upgrade(state)
    assert run_upgrade(state, upgrade)["outcome"] == "upgraded_not_started"
    apply(state, state.native_id)  # Separate post-upgrade consent before start.
    state.completed_upgrade = upgrade
    state.old_start = old_start
    return state


def test_recovered_legacy_marker_survives_real_adoption_upgrade_and_nonroot_start(
    upgraded_after_recovered_start,
):
    state = upgraded_after_recovered_start
    marker = state.helper_state / f"relational-activation-{state.instance.name}.json"
    stop = next(state.helper_state.glob("relational-start-recovery-*.json"))
    # Older Root-only 0600 proofs can retain the Core group; it grants no access.
    os.chown(stop, 0, 1202)
    before = {p: p.read_bytes() for p in (marker, stop)}
    old_action = journal(state, state.old_start)
    key = state.transport_keys / (state.instance.name + ".key")
    ticket = issue_start(state, state.completed_upgrade)
    assert start(state, ticket)["outcome"] == "active_review_required"
    assert state.actual_supervisor.starts == 1
    assert journal(state, state.old_start) == old_action
    assert all(path.read_bytes() == payload for path, payload in before.items())
    assert key.read_bytes() == SECRET
    assert journal(state, ticket)["state"] == "activated"
    apply(state, state.native_id)  # Fresh runtime grant, not migration/start consent.
    assert invoke(state, "inspect") == {"values": ["preserved"]}
    with sqlite3.connect(state.database.as_uri() + "?mode=ro", uri=True) as db:
        assert db.execute("SELECT value,third FROM business").fetchall() == [
            ("preserved", 3)
        ]
        assert db.execute(
            "SELECT revision FROM three_mm_schema_migrations ORDER BY rowid"
        ).fetchall() == [("0001",), ("0002",), ("0003",)]
        assert db.execute("SELECT COUNT(*) FROM three_mm_outbox").fetchone() == (1,)
    assert not list(state.instance.glob(".database-*.rollback"))
    with pytest.raises((authority.AuthorityManagementError, RuntimeError, ValueError)):
        start(state, ticket)
    assert state.actual_supervisor.starts == 1


@pytest.mark.parametrize("phase", ["issue", "begin", "finish"])
def test_new_start_recovery_ignores_only_verified_closed_foreign_legacy_evidence(
    upgraded_after_recovered_start, phase
):
    state = upgraded_after_recovered_start
    legacy = state.helper_state / f"relational-activation-{state.instance.name}.json"
    before = legacy.read_bytes()
    ticket = issue_start(state, state.completed_upgrade)
    if phase != "issue":

        def crash(current, at, **kw):
            result = start_checkpoint(state, current, at, **kw)
            if at == phase:
                raise Crash()
            return result

        with pytest.raises(Crash):
            start(state, ticket, checkpoint=crash)
    starts = state.actual_supervisor.starts
    stopped_ticket = issue_stop(state, ticket)
    assert recover(state, stopped_ticket)["outcome"] == "stopped_review_required"
    assert state.actual_supervisor.starts == starts
    assert state.actual_supervisor.process is None
    assert legacy.read_bytes() == before
    if phase == "issue":
        # Exact live failure path: a consumed preflight refusal is not retried.
        # Fresh stop -> separate rights -> fresh reactivation -> runtime rights.
        apply(state, state.native_id)
        restart = issue_restart(state, stopped_ticket)
        assert start(state, restart)["outcome"] == "active_review_required"
        apply(state, state.native_id)
        assert invoke(state, "inspect") == {"values": ["preserved"]}
        assert legacy.read_bytes() == before


@pytest.fixture
def legacy_evidence(tmp_path, request):
    instance = "a" * 24
    old_id, recovery_id = "b" * 32, "c" * 32
    witness = {
        "version": 1,
        "activation_id": old_id,
        "ticket_sha256": "d" * 64,
        "prepared_lifecycle_sha256": "e" * 64,
        "phase": getattr(request, "param", "activation_unconfirmed"),
    }
    if witness["phase"] == "active_review_required":
        witness["receipt"] = sign_metadata(
            SECRET,
            "activation_result",
            {
                "version": 1,
                "preparation_id": old_id,
                "lifecycle_sha256": "e" * 64,
                "outcome": "active_review_required",
            },
        )
    digest = hashlib.sha256(
        canonical({"location": "pending", "evidence": witness})
    ).hexdigest()
    receipt = sign_metadata(
        SECRET,
        "activation_recovery_result",
        {
            "version": 1,
            "preparation_id": recovery_id,
            "ticket_sha256": "f" * 64,
            "source_activation_id": old_id,
            "lifecycle_sha256": "e" * 64,
            "witness_sha256": digest,
            "outcome": "stopped_review_required",
        },
    )
    proof = {
        "version": 1,
        "recovery_id": recovery_id,
        "source_activation_id": old_id,
        "ticket_sha256": "f" * 64,
        "witness_sha256": digest,
        "phase": "stopped_review_required",
        "receipt": receipt,
    }
    marker = tmp_path / f"relational-activation-{instance}.json"
    path = tmp_path / f"relational-start-recovery-{instance}-{recovery_id}.json"
    for file, value in ((marker, witness), (path, proof)):
        file.write_bytes(canonical(value))
        file.chmod(0o600)
    return tmp_path, instance, marker, path, proof


@pytest.mark.parametrize(
    "problem",
    [
        "missing",
        "unconfirmed",
        "signature",
        "witness_digest",
        "lifecycle",
        "source",
        "ticket",
        "filename",
        "mode",
        "owner",
        "symlink",
        "hardlink",
        "oversize",
        "duplicate",
        "marker_drift",
        "key",
        "budget",
        "outer_id",
        "outer_digest",
        "extra_field",
    ],
)
def test_unverified_legacy_stop_never_unblocks_start(legacy_evidence, problem):
    root, instance, marker, path, proof = legacy_evidence
    secret = SECRET
    if problem == "missing":
        path.unlink()
    elif problem == "key":
        secret = b"x" * 32
    elif problem == "budget":
        for n in range(33):
            extra = root / f"relational-start-recovery-{instance}-{n:032x}.json"
            extra.write_bytes(canonical(proof))
            extra.chmod(0o600)
    elif problem == "mode":
        path.chmod(0o640)
    elif problem == "owner":
        os.chown(path, 1200, 1201)
    elif problem == "symlink":
        target = root / "elsewhere"
        path.rename(target)
        path.symlink_to(target)
    elif problem == "hardlink":
        os.link(path, root / "linked")
    elif problem == "oversize":
        path.write_bytes(b" " * 8193)
    elif problem == "duplicate":
        path.write_bytes(b'{"version":1,"version":1}')
    elif problem == "marker_drift":
        value = json.loads(marker.read_bytes())
        value["ticket_sha256"] = "0" * 64
        marker.write_bytes(canonical(value))
    elif problem == "filename":
        path.rename(root / f"relational-start-recovery-{instance}-{'0' * 32}.json")
    elif problem in {"outer_id", "outer_digest", "extra_field"}:
        proof[
            {
                "outer_id": "recovery_id",
                "outer_digest": "witness_sha256",
                "extra_field": "unexpected",
            }[problem]
        ] = "0" * (32 if problem == "outer_id" else 64)
        path.write_bytes(canonical(proof))
    else:
        if problem == "unconfirmed":
            proof["phase"] = "stopped_unconfirmed"
        else:
            field = {
                "signature": "signature",
                "witness_digest": "witness_sha256",
                "lifecycle": "lifecycle_sha256",
                "source": "source_activation_id",
                "ticket": "ticket_sha256",
            }[problem]
            proof["receipt"][field] = "0" * (32 if problem == "source" else 64)
            if problem != "signature":
                proof["receipt"] = sign_metadata(
                    SECRET, "activation_recovery_result", proof["receipt"]
                )
        path.write_bytes(canonical(proof))
    with pytest.raises(ValueError):
        recovery._confirmed_legacy_witness(root, instance, secret)


@pytest.mark.parametrize(
    "legacy_evidence",
    ["activation_unconfirmed", "active_review_required"],
    indirect=True,
)
def test_only_closed_legacy_proof_selects_distinct_path_and_preserves_evidence(
    legacy_evidence,
):
    root, instance, marker, path, proof = legacy_evidence
    before = {p: p.read_bytes() for p in (marker, path)}
    identifier = "1" * 32
    assert recovery._confirmed_legacy_witness(root, instance, SECRET) == "b" * 32
    selected = recovery._activation_marker(root, instance, identifier, SECRET)
    assert (
        selected.name == f"relational-activation-{instance}-{identifier}.pending.json"
    )
    assert not selected.exists()
    assert all(p.read_bytes() == data for p, data in before.items())
    assert recovery._activation_marker(root, instance, "b" * 32, SECRET) == marker
    own = root / f"relational-activation-{instance}-{'b' * 32}.pending.json"
    own.write_bytes(b"must not overwrite or conflate")
    own.chmod(0o600)
    with pytest.raises(ValueError, match="Conflicting"):
        recovery._activation_marker(root, instance, "b" * 32, SECRET)


def test_unclosed_legacy_marker_blocks_even_a_recorded_new_recovery(legacy_evidence):
    root, instance, marker, path, proof = legacy_evidence
    path.unlink()
    ticket = {
        "instance_id": instance,
        "source_activation_id": "1" * 32,
        "action": "reconcile_prepared_start",
        "source_state": "recorded",
    }
    with pytest.raises(ValueError, match="confirmed recovery"):
        recovery._witness(root, ticket, SECRET)
