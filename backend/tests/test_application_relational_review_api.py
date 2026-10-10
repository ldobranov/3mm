"""Sealed metadata review over real ZIPs/logins, never live SQLite execution.

The fixture represents an installed artifact pin; installing/starting the new
profile is still refused by runtime guards. No grant is fabricated in SQL.
"""

import io
import json
import os
import zipfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.db.application_authority_grant import ApplicationAuthorityGrant as Grant
from backend.db.authority import CoreAuthorityGuard
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.db.module import ModulePackage
from backend.db.session import UserSession
from backend.routes.application_authority import router
from backend.services import application_authority_management as management
from backend.services.application_authority_sources import _read_snapshot
from backend.services.module_packages import validate_module_package
from backend.tests.test_application_authority_management import (
    identity,
)
from backend.tests.test_application_authority_management import (
    installed as managed_installed,
)
from backend.tests.test_application_authority_management import native
from backend.tests.test_application_authority_sources import PRIVATE
from backend.tests.test_application_authority_subjects import (
    installed as source_subject,
)
from backend.tests.test_application_authority_subjects import source_installed
from backend.utils.db_utils import get_db
from three_mm_application_sdk import ApplicationStorage
from three_mm_protocol.tests.test_application_private_files import file_request
from three_mm_protocol.tests.test_application_relational_storage import (
    relational_request,
)

pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="Actual POSIX Core review keys"
)
READ = "storage:relational_read"
WRITE = "storage:relational_write"


def store_package(state, definition):
    manifest = state.validated.manifest.model_dump(mode="json")
    output = io.BytesIO()
    with (
        zipfile.ZipFile(state.archive) as source,
        zipfile.ZipFile(output, "w") as target,
    ):
        target.writestr("manifest.json", json.dumps(manifest))
        target.writestr("application-extension.json", json.dumps(definition))
        artifact = definition["service"]["artifact"]
        target.writestr(artifact, source.read(artifact))
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


@pytest.fixture
def db_app(managed_installed, request, monkeypatch):
    state = managed_installed
    mode, files = getattr(request, "param", ("read_write", False))
    definition = state.validated.application_extension.model_dump(mode="json")
    definition["service"]["sdk_version"] = "1.3"
    definition["storage"]["relational"] = relational_request(mode=mode)
    if files:
        definition["storage"]["private_files"] = file_request(mode="read")
    store_package(state, definition)

    def forbidden(*args, **kwargs):
        pytest.fail("Metadata review opened/migrated application SQLite")

    monkeypatch.setattr(ApplicationStorage, "_connect", forbidden)
    monkeypatch.setattr(ApplicationStorage, "migrate", forbidden)
    return state


@pytest.fixture
def api(db_app):
    state = db_app
    app = FastAPI()
    app.include_router(router)

    def database():
        with Session(state.engine) as db:
            yield db

    app.dependency_overrides[get_db] = database
    with TestClient(app) as client:
        yield state, client, "/api/v1/application-extensions/" + state.validated.manifest.module_id + "/authority"


def request_review(state):
    proof = native(state)
    return {
        "request_id": identity(),
        "native_review_id": proof["native_review_id"],
        "scopes": state.manager.inspect(1)["scopes"],
    }


def decision(plan):
    return {
        "request_id": identity(),
        "expected_revision": plan["revision"],
        "fingerprint": plan["fingerprint"],
    }


def create(state, client, base):
    response = client.post(
        base + "/reviews",
        json=request_review(state),
        headers={"Authorization": "Bearer " + state.token},
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize(
    "db_app",
    [("read", False), ("read_write", False), ("read_write", True)],
    indirect=True,
)
def test_review_approve_apply_revoke_are_exact_sealed_metadata_not_execution(api):
    state, client, base = api
    headers = {"Authorization": "Bearer " + state.token}
    with state.engine.begin() as db:
        db.execute(update(Installation).values(enabled=False, status="disabled"))
    plan = create(state, client, base)
    scopes = plan["resources"]["relational"]
    definition = state.validated.application_extension
    assert {item["operation"] for item in scopes} == (
        {"read", "write"}
        if definition.storage.relational.mode == "read_write"
        else {"read"}
    )
    for scope in scopes:
        assert scope["declaration"] == definition.storage.relational.model_dump(
            mode="json"
        )
        assert scope["package_artifact_sha256"] == state.validated.sha256
        assert scope["service_artifact_sha256"] == definition.service.artifact_sha256
        assert scope["schema_revision"] == definition.storage.schema_revision
        assert scope["migration_entrypoint"] == definition.storage.migration_entrypoint
        assert scope["owner"]["application_installation_id"] == "1"
    assert PRIVATE not in json.dumps(plan) and state.token not in json.dumps(plan)
    assert str(state.root) not in json.dumps(plan)
    approved = client.post(
        base + "/reviews/" + plan["plan_id"] + "/approve",
        json=decision(plan),
        headers=headers,
    )
    assert approved.status_code == 200, approved.text
    with Session(state.engine) as db:
        assert db.get(Grant, 1) is None  # Approval is not apply/admission/SQL.
    apply_request = decision(approved.json())
    applied = client.post(
        base + "/reviews/" + plan["plan_id"] + "/apply",
        json=apply_request,
        headers=headers,
    )
    assert applied.status_code == 200, applied.text
    replayed = client.post(
        base + "/reviews/" + plan["plan_id"] + "/apply",
        json=apply_request,
        headers=headers,
    )
    assert replayed.status_code == 200
    assert replayed.json() == {**applied.json(), "historical": True, "replayed": True}
    status = client.get(base, headers=headers).json()
    assert status["mode"] == "enforced" and not status["grant_effective"]
    assert status["runtime_blockers"] == ["relational_runtime_unavailable"]
    prepared = state.manager._prepare(1)
    with state.keys.locked() as key, _read_snapshot(state.engine) as db:
        grant = state.manager._require_grant(db, key, 1, prepared, READ)
        assert grant["data"]["subject"]["subject_version"] == 5
    with Session(state.engine) as db:
        with pytest.raises(
            management.AuthorityManagementError, match="relational_runtime_unavailable"
        ):
            with state.manager.native_activation(
                1,
                state.validated.sha256,
                state.configuration,
                management._compose(db, 1, *prepared, state.keys).guard,
            ):
                pytest.fail("Review metadata started application code")
    for scope in (READ, WRITE):
        with Session(state.engine) as db:
            with pytest.raises(ValueError, match="runtime is not implemented"):
                with management.effect_admission(db, 1, scope):
                    pytest.fail("Metadata grant issued SQL authority")
    revoked = client.post(
        base + "/revoke",
        headers=headers,
        json={
            "request_id": identity(),
            "expected_revision": status["grant_record_revision"],
        },
    )
    assert revoked.status_code == 200 and revoked.json()["state"] == "revoked"
    with state.keys.locked() as key, _read_snapshot(state.engine) as db:
        with pytest.raises(management.AuthorityManagementError):
            state.manager._require_grant(db, key, 1, state.manager._prepare(1), READ)


def test_http_keeps_current_admin_native_attestation_and_disabled_adoption_gates(api):
    state, client, base = api
    payload = request_review(state)
    headers = {"Authorization": "Bearer " + state.token}
    assert client.post(base + "/reviews", json=payload).status_code == 401
    assert (
        client.post(
            base + "/reviews",
            json=payload,
            headers={"Authorization": "Bearer " + state.user_token},
        ).status_code
        == 403
    )
    assert (
        client.post(
            base + "/reviews",
            json={**payload, "native_review_id": identity()},
            headers=headers,
        ).status_code
        == 409
    )
    plan = client.post(base + "/reviews", json=payload, headers=headers).json()
    approved = client.post(
        base + "/reviews/" + plan["plan_id"] + "/approve",
        json=decision(plan),
        headers=headers,
    ).json()
    refused = client.post(
        base + "/reviews/" + plan["plan_id"] + "/apply",
        json=decision(approved),
        headers=headers,
    )
    assert (
        refused.status_code == 409
        and refused.json()["detail"]["code"] == "disabled_adoption_required"
    )
    with Session(state.engine) as db:
        assert db.get(Grant, 1) is None
    for scope in (READ, WRITE):
        with Session(state.engine) as db:
            with pytest.raises(ValueError, match="runtime is not implemented"):
                with management.effect_admission(db, 1, scope):
                    pytest.fail("Compatibility lease bypassed DB runtime guard")


def test_no_caller_limits_paths_wildcards_or_partial_db_selection(api):
    state, client, base = api
    headers = {"Authorization": "Bearer " + state.token}
    payload = request_review(state)
    for scopes in (
        [READ],
        [WRITE],
        ["command:pulse", "connector:business_api"],
        payload["scopes"] + [READ],
    ):
        assert (
            client.post(
                base + "/reviews", json={**payload, "scopes": scopes}, headers=headers
            ).status_code
            == 409
        )
    for scope in (
        "storage:relational",
        "storage:relational_*",
        "storage:relational_migrate",
        "storage:relational_write\n",
    ):
        assert (
            client.post(
                base + "/reviews", json={**payload, "scopes": [scope]}, headers=headers
            ).status_code
            == 422
        )
    for extra in (
        {"relational": []},
        {"path": "/var/lib/3mm/core"},
        {"limits": {"max_database_bytes": 1}},
        {"approved": True},
    ):
        assert (
            client.post(
                base + "/reviews", json={**payload, **extra}, headers=headers
            ).status_code
            == 422
        )
    with Session(state.engine) as db:
        assert db.get(Grant, 1) is None


@pytest.mark.parametrize(
    "drift",
    [
        "limit",
        "schema",
        "migration",
        "configuration",
        "recovery",
        "key",
        "session",
        "reboot",
    ],
)
@pytest.mark.parametrize("phase", ["approve", "apply"])
def test_decision_refuses_all_profile_and_authority_drift(
    api, monkeypatch, drift, phase
):
    state, client, base = api
    if phase == "apply":
        with state.engine.begin() as db:
            db.execute(update(Installation).values(enabled=False, status="disabled"))
    plan = create(state, client, base)
    if phase == "apply":
        response = client.post(
            base + "/reviews/" + plan["plan_id"] + "/approve",
            json=decision(plan),
            headers={"Authorization": "Bearer " + state.token},
        )
        assert response.status_code == 200
        plan = response.json()
    if drift in {"limit", "schema", "migration"}:
        definition = state.validated.application_extension.model_dump(mode="json")
        if drift == "limit":
            definition["storage"]["relational"]["max_database_bytes"] *= 2
        else:
            definition["storage"][
                "schema_revision" if drift == "schema" else "migration_entrypoint"
            ] = ("0002" if drift == "schema" else "example_app:other_migrations")
        store_package(state, definition)
    elif drift == "key":
        state.keys.rotate(expected_key_id=state.keys.identity().key_id)
    elif drift == "reboot":
        boot, now = management._clock()
        monkeypatch.setattr(management, "_clock", lambda: (identity(), now))
    else:
        with state.engine.begin() as db:
            if drift == "configuration":
                db.execute(
                    update(Installation).values(
                        configuration={**state.configuration, "PRIVATE_NOTE": "changed"}
                    )
                )
            elif drift == "recovery":
                db.execute(update(CoreAuthorityGuard).values(generation=identity()))
            else:
                db.execute(
                    update(UserSession)
                    .where(UserSession.id == 1)
                    .values(is_active=False)
                )
    response = client.post(
        base + "/reviews/" + plan["plan_id"] + "/" + phase,
        json=decision(plan),
        headers={"Authorization": "Bearer " + state.token},
    )
    assert response.status_code in (401, 403, 409)
    with Session(state.engine) as db:
        assert db.get(Grant, 1) is None
