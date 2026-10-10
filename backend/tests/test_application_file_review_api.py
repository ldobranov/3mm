"""Existing admin HTTP review, real file declarations/keys/sessions, no live data."""

import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.db.application_authority_grant import ApplicationAuthorityGrant as Grant
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.db.session import UserSession
from backend.routes.application_authority import router
from backend.services.application_files import ApplicationFileAuthorityError
from backend.tests.test_application_authority_sources import PRIVATE
from backend.tests.test_application_file_execution import (
    execute,
    file_app,
    identity,
    managed_installed,
    native,
)
from backend.tests.test_application_file_execution import request as file_request
from backend.tests.test_application_file_execution import (
    source_installed,
    source_subject,
)
from backend.utils.db_utils import get_db
from three_mm_runtime.application_file_executor import ApplicationFileExecutor

pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="Actual POSIX authority keys"
)


@pytest.fixture
def api(file_app):
    s = file_app
    app = FastAPI()
    app.include_router(router)

    def database():
        with Session(s.engine) as db:
            yield db

    app.dependency_overrides[get_db] = database
    with TestClient(app) as client:
        yield s, client, "/api/v1/application-extensions/" + s.validated.manifest.module_id + "/authority"


def review_request(s):
    proof = native(s)
    return {
        "request_id": identity(),
        "native_review_id": proof["native_review_id"],
        "scopes": s.manager.inspect(1)["scopes"],
    }


def decision_request(plan):
    return {
        "request_id": identity(),
        "expected_revision": plan["revision"],
        "fingerprint": plan["fingerprint"],
    }


@pytest.mark.parametrize("file_app", ["read", "read_write"], indirect=True)
def test_http_file_review_approve_apply_and_revoke_exact_rights(api):
    s, client, base = api
    headers = {"Authorization": "Bearer " + s.token}
    with s.engine.begin() as db:
        db.execute(update(Installation).values(enabled=False, status="disabled"))
    payload = review_request(s)
    response = client.post(base + "/reviews", json=payload, headers=headers)
    assert response.status_code == 200, response.text
    plan = response.json()
    resources = plan["resources"]["private_files"]
    expected = (
        {"read", "write"}
        if s.metadata["storage"]["private_files"]["mode"] == "read_write"
        else {"read"}
    )
    assert {item["operation"] for item in resources} == expected
    for item in resources:
        assert item["declaration"] == s.metadata["storage"]["private_files"]
        assert item["owner"]["application_installation_id"] == "1"
        assert item["owner"]["module_id"] == s.validated.manifest.module_id
        assert item["package_artifact_sha256"] == s.validated.sha256
    assert (
        PRIVATE not in response.text
        and str(s.runtime) not in response.text
        and s.token not in response.text
    )
    assert not s.manager.inspect(1)["grant_effective"]
    approved = client.post(
        base + "/reviews/" + plan["plan_id"] + "/approve",
        json=decision_request(plan),
        headers=headers,
    )
    assert approved.status_code == 200, approved.text
    with Session(s.engine) as db:
        assert not db.scalars(select(Grant)).all()  # Approval alone grants nothing.
    applied = client.post(
        base + "/reviews/" + plan["plan_id"] + "/apply",
        json=decision_request(approved.json()),
        headers=headers,
    )
    assert applied.status_code == 200, applied.text
    current = client.get(base, headers=headers).json()
    assert current["mode"] == "enforced" and current["grant_state"] == "active"
    assert not current["grant_effective"]  # Stopped applications cannot execute.
    revoked = client.post(
        base + "/revoke",
        json={
            "request_id": identity(),
            "expected_revision": current["grant_record_revision"],
        },
        headers=headers,
    )
    assert revoked.status_code == 200 and revoked.json()["state"] == "revoked"
    with ApplicationFileExecutor(s.runtime, s.metadata, s.secret):
        with pytest.raises(ApplicationFileAuthorityError):
            execute(s, file_request("get"))
    assert not (s.runtime / "data/sdk-files").exists()


def test_file_review_keeps_authentication_native_proof_and_adoption_gates(api):
    s, client, base = api
    headers = {"Authorization": "Bearer " + s.token}
    payload = review_request(s)
    assert client.post(base + "/reviews", json=payload).status_code == 401
    assert (
        client.post(
            base + "/reviews",
            json=payload,
            headers={"Authorization": "Bearer " + s.user_token},
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
        json=decision_request(plan),
        headers=headers,
    ).json()
    response = client.post(
        base + "/reviews/" + plan["plan_id"] + "/apply",
        json=decision_request(approved),
        headers=headers,
    )
    assert (
        response.status_code == 409
        and response.json()["detail"]["code"] == "disabled_adoption_required"
    )
    with Session(s.engine) as db:
        assert not db.scalars(select(Grant)).all()


def test_http_file_review_refuses_wildcards_injected_resources_and_incomplete_selection(
    api,
):
    s, client, base = api
    headers = {"Authorization": "Bearer " + s.token}
    payload = review_request(s)
    for scope in (
        "storage:*",
        "storage:private_files",
        "storage:private_files_delete",
        "storage:other_read",
        "storage:private_files_write\n",
    ):
        response = client.post(
            base + "/reviews", json={**payload, "scopes": [scope]}, headers=headers
        )
        assert response.status_code == 422
    for extra in (
        {"resources": {"private_files": []}},
        {"mode": "read_write"},
        {"path": "/var/lib/3mm/core"},
        {"isolation_proven": True},
    ):
        assert (
            client.post(
                base + "/reviews", json={**payload, **extra}, headers=headers
            ).status_code
            == 422
        )
    for scopes in (
        [
            scope
            for scope in payload["scopes"]
            if scope != "storage:private_files_write"
        ],
        payload["scopes"] + ["storage:private_files_write"],
    ):
        assert (
            client.post(
                base + "/reviews", json={**payload, "scopes": scopes}, headers=headers
            ).status_code
            == 409
        )
    assert not (s.runtime / "data/sdk-files").exists()


@pytest.mark.parametrize("drift", ["configuration", "session"])
def test_http_file_approval_refuses_changed_configuration_or_revoked_session(
    api, drift
):
    s, client, base = api
    headers = {"Authorization": "Bearer " + s.token}
    plan = client.post(
        base + "/reviews", json=review_request(s), headers=headers
    ).json()
    with s.engine.begin() as db:
        if drift == "configuration":
            db.execute(update(Installation).values(configuration={}))
        else:
            db.execute(
                update(UserSession).where(UserSession.id == 1).values(is_active=False)
            )
    response = client.post(
        base + "/reviews/" + plan["plan_id"] + "/approve",
        json=decision_request(plan),
        headers=headers,
    )
    assert response.status_code in (401, 403, 409)
    with Session(s.engine) as db:
        assert not db.scalars(select(Grant)).all()
