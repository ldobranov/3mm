"""Real installed identity-read permission review; never peer/proof authority."""

import json
import os
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from backend.db.application_authority_grant import ApplicationAuthorityGrant as Grant
from backend.db.authority import CoreAuthorityGuard
from backend.db.installation_identity import CoreInstallationIdentity
from backend.db.installation_peer import InstallationPeerOutbound
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.services import application_authority_management as management
from backend.services.application_authority_sources import _read_snapshot
from backend.services.application_authority_subjects import resolve_installed_policy_subject
from backend.routes.application_authority import router
from backend.tests.test_application_authority_management import identity, native, decide
from backend.tests.test_application_authority_management import installed as managed_installed
from backend.tests.test_application_authority_subjects import installed as source_subject
from backend.tests.test_application_authority_subjects import source_installed
from backend.tests.test_application_checkpoint_authority import (
    checkpoint_app, store_checkpoint_package,
)
from backend.utils.db_utils import get_db
from three_mm_protocol.tests.test_application_private_files import file_request
from three_mm_protocol.tests.test_application_relational_storage import relational_request


pytestmark = pytest.mark.skipif(os.name != "posix", reason="Real POSIX Core review keys")
READ = "platform:installation.identity.read"
store_identity_package = store_checkpoint_package


@pytest.fixture
def identity_app(checkpoint_app, request):
    """Public identity read only; optional (SDK version, mixed resources)."""
    state = checkpoint_app
    sdk, mixed = getattr(request, "param", ("1.3", False))
    definition = state.validated.application_extension.model_dump(mode="json")
    definition["service"]["sdk_version"] = sdk
    definition["platform_permissions"] = ["installation.identity.read"]
    if not mixed:
        definition["checkpoints"] = []
    else:
        definition["storage"]["private_files"] = file_request(mode="read")
        definition["storage"]["relational"] = relational_request(mode="read_write")
    manifest = state.validated.manifest.model_dump(mode="json")
    manifest["permissions"] = ["data.read", "data.write", "process.spawn", "installation.identity.read"]
    store_identity_package(state, definition, manifest)
    return state


def identity_review(state, proof=None):
    proof = proof or native(state)
    return state.manager.create_review(1, actor_token=state.token, request_id=identity(),
        native_review_id=proof["native_review_id"], scopes=state.manager.inspect(1)["scopes"])


def activate_identity_grant(state):
    with state.engine.begin() as db:
        db.execute(update(Installation).values(enabled=False, status="disabled"))
    proof = native(state)
    decide(state, decide(state, identity_review(state, proof), "approve"), "apply")
    with state.engine.begin() as db:
        db.execute(update(Installation).values(enabled=True, status="active", authority_epoch=identity()))
    return decide(state, decide(state, identity_review(state, proof), "approve"), "apply")


@pytest.mark.parametrize("identity_app", [("1.3", False), ("1.3", True)], indirect=True)
def test_identity_permission_review_has_exact_public_pin_and_separate_decisions(identity_app):
    state = identity_app
    with state.engine.begin() as db:
        db.execute(update(Installation).values(enabled=False, status="disabled"))
    plan = identity_review(state)
    resources = plan["resources"]["identities"]
    assert len(resources) == 1 and READ in plan["scopes"]
    resource = resources[0]
    assert set(resource) == {"owner", "package_artifact_sha256", "operation", "identity"}
    assert resource["operation"] == "installation.identity.read"
    assert resource["owner"]["application_installation_id"] == "1"
    assert resource["identity"]["installation_id"] == resource["owner"]["core_installation_id"]
    assert resource["package_artifact_sha256"] == state.validated.sha256
    assert set(resource["identity"]) == {"identity_version", "algorithm", "installation_id", "key_id", "public_key", "key_generation", "created_at"}
    assert "PRIVATE_MUST_NOT_APPEAR" not in json.dumps(plan) and state.token not in json.dumps(plan)
    approved = decide(state, plan, "approve")
    with Session(state.engine) as db:
        assert db.get(Grant, 1) is None
    applied = decide(state, approved, "apply")
    assert applied["state"] == "applied"
    prepared = state.manager._prepare(1)
    with state.keys.locked() as key, _read_snapshot(state.engine) as db:
        record = state.manager._require_grant(db, key, 1, prepared, READ)
        assert record["data"]["subject"]["subject_version"] == 7
        assert record["data"]["selection"]["selection_version"] == 7
    status = state.manager.inspect(1)
    assert status["mode"] == "enforced" and not status["grant_effective"]
    assert state.manager.revoke(1, actor_token=state.token, request_id=identity(),
        expected_revision=status["grant_record_revision"])["state"] == "revoked"


@pytest.mark.parametrize("change", ["configuration", "incarnation", "recovery", "review_key", "public_identity", "identity_missing", "identity_corrupt"])
def test_identity_read_grant_never_survives_owner_identity_or_trust_drift(identity_app, change):
    state = identity_app
    activate_identity_grant(state)
    assert state.manager.inspect(1)["grant_effective"]
    if change == "review_key":
        state.keys.rotate(expected_key_id=state.keys.identity().key_id)
    else:
        with state.engine.begin() as db:
            if change == "configuration":
                db.execute(update(Installation).values(configuration={**state.configuration, "PRIVATE_NOTE": "changed"}))
            elif change == "incarnation":
                db.execute(update(Installation).values(authority_incarnation=identity()))
            elif change == "recovery":
                db.execute(update(CoreAuthorityGuard).values(generation=identity()))
            elif change == "public_identity":
                db.execute(update(CoreInstallationIdentity).values(created_at=datetime(2026, 1, 1, tzinfo=UTC)))
            elif change == "identity_missing":
                db.execute(delete(CoreInstallationIdentity))
            else:
                db.execute(update(CoreInstallationIdentity).values(key_id="f" * 64))
    with Session(state.engine) as db, pytest.raises(ValueError):
        with management.effect_admission(db, 1, READ):
            pytest.fail("Changed identity or authority admitted")


@pytest.mark.parametrize("sdk", ["1.1", "1.2"])
def test_legacy_identity_permission_remains_valid_but_cannot_opt_in_implicitly(identity_app, sdk):
    state = identity_app
    definition = state.validated.application_extension.model_dump(mode="json")
    definition["service"]["sdk_version"] = sdk
    store_identity_package(state, definition)
    assert state.validated.application_extension.service.sdk_version == sdk
    status = state.manager.inspect(1)
    assert status["mode"] == "compatibility" and not status["review_available"]
    assert status["review_blockers"] == ["unsupported_authority"]
    assert status["scopes"] == []


@pytest.mark.parametrize("permission", ["installation.identity.prove", "installation.peers.receive", "installation.status.read"])
def test_read_permission_does_not_clear_other_platform_blockers(identity_app, permission):
    state = identity_app
    if permission == "installation.status.read":
        # The migrated schema exists, but identity-read grants no peer consent.
        InstallationPeerOutbound.__table__.create(state.engine)
    definition = state.validated.application_extension.model_dump(mode="json")
    definition["platform_permissions"].append(permission)
    manifest = state.validated.manifest.model_dump(mode="json")
    manifest["permissions"].append(permission)
    store_identity_package(state, definition, manifest)
    result = resolve_installed_policy_subject(state.engine, 1, uploads_root=state.root,
        core_version="0.3.0", review_key_directory=state.key_directory)
    blocker = "peer_authority_unresolved" if permission == "installation.status.read" else "unsupported_scope_family"
    assert result.subject is not None and blocker in result.subject.blockers
    status = state.manager.inspect(1)
    assert not status["review_available"] and not status["grant_effective"]


def test_missing_peer_schema_never_produces_a_partial_identity_status_subject(identity_app):
    state = identity_app
    definition = state.validated.application_extension.model_dump(mode="json")
    definition["platform_permissions"].append("installation.status.read")
    manifest = state.validated.manifest.model_dump(mode="json")
    manifest["permissions"].append("installation.status.read")
    store_identity_package(state, definition, manifest)
    result = resolve_installed_policy_subject(state.engine, 1, uploads_root=state.root,
        core_version="0.3.0", review_key_directory=state.key_directory)
    assert result.subject is None
    assert [issue.reason for issue in result.issues] == ["source_unavailable"]
    status = state.manager.inspect(1)
    assert not status["review_available"] and not status["grant_effective"]


def test_identity_http_review_keeps_actor_checks_and_no_proof_scope(identity_app):
    state = identity_app
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
        payload = {"request_id": identity(), "native_review_id": proof["native_review_id"], "scopes": [READ]}
        headers = {"Authorization": "Bearer " + state.token}
        assert client.post(base + "/reviews", json={**payload, "scopes": ["platform:installation.identity.prove"]}, headers=headers).status_code == 422
        response = client.post(base + "/reviews", json=payload, headers=headers)
        assert response.status_code == 200, response.text
        assert len(response.json()["resources"]["identities"]) == 1
