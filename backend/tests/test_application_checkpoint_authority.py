"""Real package/key/login checkpoint authority; no VM or application execution."""

import io
import json
import os
import zipfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.db.application_authority_grant import ApplicationAuthorityAction as Action
from backend.db.application_authority_grant import ApplicationAuthorityGrant as Grant
from backend.db.authority import CoreAuthorityGuard
from backend.db.module import ApplicationExtensionInstallation as Installation, ModulePackage
from backend.db.session import UserSession
from backend.routes.application_authority import router
from backend.services import application_authority_management as management
from backend.services.application_authority_sources import _read_snapshot
from backend.services.module_packages import validate_module_package
from backend.tests.test_application_authority_management import identity, native, decide
from backend.tests.test_application_authority_management import installed as managed_installed
from backend.tests.test_application_authority_sources import PRIVATE
from backend.tests.test_application_authority_subjects import installed as source_subject
from backend.tests.test_application_authority_subjects import source_installed
from backend.utils.db_utils import get_db
from three_mm_protocol.tests.test_application_private_files import file_request
from three_mm_protocol.tests.test_application_relational_storage import relational_request


pytestmark = pytest.mark.skipif(os.name != "posix", reason="Real POSIX Core key ownership and locking")
READ = "checkpoint:catalog:read"
WRITE = "checkpoint:catalog:write"
CURSOR = "checkpoint:cursor:read"


def store_checkpoint_package(state, definition, manifest=None):
    """Replace only this isolated fixture's real installed ZIP/catalog pin."""
    manifest = manifest or state.validated.manifest.model_dump(mode="json")
    output = io.BytesIO()
    with zipfile.ZipFile(state.archive) as source, zipfile.ZipFile(output, "w") as target:
        target.writestr("manifest.json", json.dumps(manifest))
        target.writestr("application-extension.json", json.dumps(definition))
        artifact = definition["service"]["artifact"]
        target.writestr(artifact, source.read(artifact))
    state.validated = validate_module_package(output.getvalue())
    state.archive = state.root / "modules" / (state.validated.sha256 + ".zip")
    state.archive.write_bytes(output.getvalue())
    with state.engine.begin() as db:
        db.execute(update(ModulePackage).where(ModulePackage.id == 1).values(
            sha256=state.validated.sha256, size_bytes=len(output.getvalue()),
            manifest=manifest, file_path=str(state.archive)))


@pytest.fixture
def checkpoint_app(managed_installed, request):
    """Headless checkpoints-only package, real fixture DB/key/current admin login.

    Tests may parametrize ``(files, relational)`` to add the existing storage
    families. No production paths, keys, logins or services are consulted.
    """
    state = managed_installed
    files, relational = getattr(request, "param", (False, False))
    definition = state.validated.application_extension.model_dump(mode="json")
    definition["service"]["sdk_version"] = "1.3"
    definition.update(command_bindings=[], connectors=[], checkpoints=[
        {"contract_version": 1, "checkpoint_id": "catalog", "mode": "read_write", "max_value_bytes": 1024},
        {"contract_version": 1, "checkpoint_id": "cursor", "mode": "read", "max_value_bytes": 1024},
    ])
    if files:
        definition["storage"]["private_files"] = file_request(mode="read")
    if relational:
        definition["storage"]["relational"] = relational_request(mode="read_write")
    manifest = state.validated.manifest.model_dump(mode="json")
    manifest.update(permissions=["data.read", "data.write", "process.spawn"],
        capabilities={"provides": [], "consumes": []})
    store_checkpoint_package(state, definition, manifest)
    return state


def checkpoint_review(state, native_review=None):
    native_review = native_review or native(state)
    return state.manager.create_review(1, actor_token=state.token, request_id=identity(),
        native_review_id=native_review["native_review_id"], scopes=state.manager.inspect(1)["scopes"])


def activate_checkpoint_grant(state):
    """Same-artifact fixture lifecycle with a fresh post-start permission review."""
    with state.engine.begin() as db:
        db.execute(update(Installation).where(Installation.id == 1).values(enabled=False, status="disabled"))
    proof = native(state)
    decide(state, decide(state, checkpoint_review(state, proof), "approve"), "apply")
    with state.engine.begin() as db:
        db.execute(update(Installation).where(Installation.id == 1).values(
            enabled=True, status="active", authority_epoch=identity()))
    return decide(state, decide(state, checkpoint_review(state, proof), "approve"), "apply")


@pytest.mark.parametrize("checkpoint_app", [(False, False), (True, False), (True, True)], indirect=True)
def test_installed_checkpoint_review_exact_bindings_approval_apply_and_revoke(checkpoint_app):
    state = checkpoint_app
    with state.engine.begin() as db:
        db.execute(update(Installation).values(enabled=False, status="disabled"))
    plan = checkpoint_review(state)
    assert {READ, WRITE, CURSOR} <= set(plan["scopes"])
    resources = plan["resources"]["checkpoints"]
    assert len(resources) == 3
    assert {item["declaration"]["checkpoint_id"] for item in resources} == {"catalog", "cursor"}
    for resource in resources:
        assert set(resource) == {"declaration", "owner", "package_artifact_sha256", "operation"}
        assert resource["owner"]["application_installation_id"] == "1"
        assert resource["package_artifact_sha256"] == state.validated.sha256
        assert resource["declaration"]["max_value_bytes"] == 1024
    assert PRIVATE not in json.dumps(plan) and state.token not in json.dumps(plan)
    assert str(state.root) not in json.dumps(plan)
    approved = decide(state, plan, "approve")
    with Session(state.engine) as db:
        assert db.get(Grant, 1) is None
    applied = decide(state, approved, "apply")
    assert applied["state"] == "applied"
    prepared = state.manager._prepare(1)
    with state.keys.locked() as key, _read_snapshot(state.engine) as db:
        grant = state.manager._require_grant(db, key, 1, prepared, READ)
        assert grant["data"]["subject"]["subject_version"] == 6
        assert grant["data"]["selection"]["selection_version"] == 6
    status = state.manager.inspect(1)
    assert not status["grant_effective"]  # Apply did not start the application.
    assert state.manager.revoke(1, actor_token=state.token, request_id=identity(),
        expected_revision=status["grant_record_revision"])["state"] == "revoked"


@pytest.mark.parametrize("change", ["configuration", "recovery", "key", "artifact"])
def test_live_checkpoint_grant_is_not_effective_after_binding_or_trust_drift(checkpoint_app, change):
    state = checkpoint_app
    activate_checkpoint_grant(state)
    assert state.manager.inspect(1)["grant_effective"]
    if change == "key":
        state.keys.rotate(expected_key_id=state.keys.identity().key_id)
    elif change == "artifact":
        definition = state.validated.application_extension.model_dump(mode="json")
        definition["checkpoints"][0]["max_value_bytes"] = 2048
        store_checkpoint_package(state, definition)
    else:
        with state.engine.begin() as db:
            if change == "configuration":
                db.execute(update(Installation).values(configuration={**state.configuration, "PRIVATE_NOTE": "changed"}))
            else:
                db.execute(update(CoreAuthorityGuard).values(generation=identity()))
    assert not state.manager.inspect(1)["grant_effective"]
    with Session(state.engine) as db, pytest.raises(ValueError):
        with management.effect_admission(db, 1, READ):
            pytest.fail("Stale checkpoint grant admitted")


def test_checkpoint_audit_callback_is_machine_only_redacted_exact_and_transactional(checkpoint_app):
    state = checkpoint_app
    activate_checkpoint_grant(state)
    with Session(state.engine) as db:
        before = set(db.scalars(select(Action.request_id)))
    with Session(state.engine) as db:
        with management.effect_admission(db, 1, WRITE) as admission:
            with pytest.raises(ValueError, match="metadata"):
                admission.record_checkpoint_write("foreign", 0, 1)
    with Session(state.engine) as db:
        assert set(db.scalars(select(Action.request_id))) == before
    with Session(state.engine) as db:
        with management.effect_admission(db, 1, WRITE) as admission:
            admission.record_checkpoint_write("catalog", 0, 1)
            db.commit()
            admission()
    with state.keys.locked() as key, Session(state.engine) as db:
        records = [row for row in db.scalars(select(Action)) if row.request_id not in before]
        assert len(records) == 1
        row = records[0]
        record = management._load(db, key, "action", row, row.request_id)
        assert record["state"] == "completed"
        assert record["data"] == {
            "operation": "checkpoint_put", "actor": ["application", "1"],
            "principal": {"core_installation_id": "inst_" + "5" * 32,
                "application_installation_id": "1", "incarnation": record["data"]["principal"]["incarnation"],
                "module_id": state.validated.manifest.module_id},
            "scope": WRITE, "package_artifact_sha256": state.validated.sha256,
            "checkpoint_id": "catalog", "expected_revision": 0, "revision": 1,
        }
        assert PRIVATE not in row.payload and state.token not in row.payload


@pytest.mark.parametrize("metadata", [
    ("foreign", 0, 1), ("catalog", True, 2), ("catalog", 0, True),
    ("catalog", -1, 0), ("catalog", 0, 2), ("catalog", 2**53 - 1, 2**53),
])
def test_audit_callback_rejects_nonexact_or_unbounded_revisions_without_a_record(checkpoint_app, metadata):
    state = checkpoint_app
    activate_checkpoint_grant(state)
    with Session(state.engine) as db:
        before = set(db.scalars(select(Action.request_id)))
    with Session(state.engine) as db, pytest.raises(ValueError):
        with management.effect_admission(db, 1, WRITE) as admission:
            admission.record_checkpoint_write(*metadata)
            db.commit()
    with Session(state.engine) as db:
        assert set(db.scalars(select(Action.request_id))) == before


def test_audit_rollback_duplicate_and_full_journal_never_prune_existing_evidence(checkpoint_app, monkeypatch):
    state = checkpoint_app
    activate_checkpoint_grant(state)
    with Session(state.engine) as db:
        before = {row.request_id: row.payload for row in db.scalars(select(Action))}
    with Session(state.engine) as db, pytest.raises(ValueError):
        with management.effect_admission(db, 1, WRITE) as admission:
            admission.record_checkpoint_write("catalog", 0, 1)
            admission.record_checkpoint_write("catalog", 0, 1)
            db.commit()
    monkeypatch.setattr(management, "MAX_CHECKPOINT_ACTIONS_PER_INSTALLATION", len(before))
    with Session(state.engine) as db, pytest.raises(ValueError):
        with management.effect_admission(db, 1, WRITE) as admission:
            admission.record_checkpoint_write("catalog", 0, 1)
            db.commit()
    with Session(state.engine) as db:
        assert {row.request_id: row.payload for row in db.scalars(select(Action))} == before


def test_full_audit_journal_rolls_back_actual_checkpoint_mutation_and_preserves_data(checkpoint_app, monkeypatch):
    from backend.services.application_checkpoints import execute_checkpoint

    state = checkpoint_app
    activate_checkpoint_grant(state)

    def execute(action, **fields):
        request = {
            "version": 1, "request_id": "platform_" + identity(), "timestamp": 1,
            "instance_id": "a" * 24, "signature": "b" * 64,
            "action": action, "checkpoint_id": "catalog", **fields,
        }
        with Session(state.engine) as db:
            return execute_checkpoint(db, db.get(Installation, 1), request)

    saved = execute("checkpoint.put", expected_revision=0, value={"keep": True})
    with Session(state.engine) as db:
        evidence = {row.request_id: row.payload for row in db.scalars(select(Action))}
    monkeypatch.setattr(management, "MAX_CHECKPOINT_ACTIONS_PER_INSTALLATION", len(evidence))
    with pytest.raises(ValueError):
        execute("checkpoint.put", expected_revision=1, value={"keep": False})
    assert execute("checkpoint.get") == saved
    with Session(state.engine) as db:
        assert {row.request_id: row.payload for row in db.scalars(select(Action))} == evidence


def test_checkpoint_api_keeps_current_administrator_and_separate_decisions(checkpoint_app):
    state = checkpoint_app
    app = FastAPI()
    app.include_router(router)

    def database():
        with Session(state.engine) as db:
            yield db

    app.dependency_overrides[get_db] = database
    base = "/api/v1/application-extensions/" + state.validated.manifest.module_id + "/authority"
    with TestClient(app) as client:
        assert client.get(base).status_code == 401
        assert client.get(base, headers={"Authorization": "Bearer " + state.user_token}).status_code == 403
        proof = native(state)
        payload = {"request_id": identity(), "native_review_id": proof["native_review_id"],
            "scopes": [READ, WRITE, CURSOR]}
        headers = {"Authorization": "Bearer " + state.token}
        assert client.post(base + "/reviews", json={**payload, "owner": "foreign"}, headers=headers).status_code == 422
        assert client.post(base + "/reviews", json={**payload, "scopes": ["checkpoint:*:read"]}, headers=headers).status_code == 422
        response = client.post(base + "/reviews", json=payload, headers=headers)
        assert response.status_code == 200, response.text
        plan = response.json()
        assert len(plan["resources"]["checkpoints"]) == 3
        with state.engine.begin() as db:
            db.execute(update(UserSession).where(UserSession.id == 1).values(is_active=False))
        assert client.post(base + "/reviews/" + plan["plan_id"] + "/approve", headers=headers,
            json={"request_id": identity(), "expected_revision": plan["revision"], "fingerprint": plan["fingerprint"]}).status_code == 401
    with Session(state.engine) as db:
        assert db.get(Grant, 1) is None
