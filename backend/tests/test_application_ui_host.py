from backend.tests.test_application_access import kiosk_enrollment,kiosk_claim
"""Public UI contract uses the real actor/audience gateway, not client claims."""

import pytest

from backend.db.module import ApplicationPermissionGrant
from backend.services import application_extensions as gateway
from backend.tests.test_application_access import environment, headers
from backend.tests.test_module_packages import (
    application_definition,
    application_package,
)


@pytest.fixture(params=["public", "kiosk", "operator", "administrator"])
def setup(request, monkeypatch, tmp_path):
    audience = request.param
    definition = application_definition()
    route = definition["routes"][1]
    route.update(
        audience=audience, layout="kiosk" if audience == "kiosk" else "application"
    )
    if audience != "operator":
        route["required_permissions"] = []
    definition["operations"][2]["audiences"] = [audience]
    values = environment(
        monkeypatch, tmp_path, application_package(definition=definition)
    )
    client, db, engine, _, user, installation, package, admin_token, token = values
    base = f"/api/v1/application-extensions/{package.module_id}"
    db.add(
        ApplicationPermissionGrant(
            application_installation_id=installation.id,
            user_id=user.id,
            permission_id="records_manage",
        )
    )
    db.commit()
    if audience == "kiosk":
        code = client.post(
            base + "/kiosk/enrollments",
            headers=headers(admin_token),
            json=kiosk_enrollment('Host fixture'),
        ).json()["code"]
        token = client.post(
            base + "/kiosk/enrollments/claim", json=kiosk_claim(code)
        ).json()["access_token"]
    elif audience == "administrator":
        token = admin_token
    auth = {} if audience == "public" else headers(token)
    calls = []

    class Recorder:
        def __init__(self, *_args):
            pass

        def invoke(self, operation_id, payload, context):
            calls.append((operation_id, payload, context))
            return {}

    monkeypatch.setattr(gateway, "ApplicationServiceClient", Recorder)
    binding = {
        "host_version": 1,
        "entrypoint_id": "operations",
        "artifact_sha256": package.sha256,
    }
    yield values, base, audience, auth, binding, calls
    client.close()
    db.close()
    engine.dispose()


def info_url(base, binding):
    return base + "/ui-host/operations?artifact_sha256=" + binding["artifact_sha256"]


def operation_url(base, audience):
    segment = "" if audience == "administrator" else "/" + audience
    return base + segment + "/operations/approve"


def test_info_and_dispatch_bind_actual_package_entrypoint_and_audience(setup):
    values, base, audience, auth, binding, calls = setup
    response = values[0].get(info_url(base, binding), headers=auth)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    data = response.json()
    assert data["audience"] == audience
    assert data["artifact_sha256"] == binding["artifact_sha256"]
    assert data["features"] == {
        "operations": True,
        "resource_authority": "separate",
        "browser_isolation": False,
        "presentation_version": 1,
        "administration_reads": [],
        "administration_actions": [],
    }
    assert {op["operation_id"] for op in data["operations"]} == (
        {"register", "approve"} if audience == "kiosk" else {"approve"}
    )
    assert (
        not {"token", "configuration", "permissions", "user_id", "socket_path"}
        & data.keys()
    )
    result = values[0].post(
        operation_url(base, audience),
        headers=auth,
        json={
            "payload": {},
            "idempotency_key": "ui-host-test-1",
            "ui_context": binding,
        },
    )
    assert result.status_code == 200
    assert len(calls) == 1
    assert calls[0][2]["audience"] == audience
    assert "ui_context" not in calls[0][2]


def test_current_actor_api_uses_the_route_audience_and_never_exposes_credentials(setup):
    values, base, audience, auth, binding, calls = setup
    url = base + '/ui-host/operations/access?artifact_sha256=' + binding['artifact_sha256']
    response = values[0].get(url, headers=auth)
    assert response.status_code == 200, response.text
    data = response.json()
    assert response.headers['cache-control'] == 'no-store'
    assert data['audience'] == audience and data['service_authority'] == 'separate'
    assert data['admission_required'] is True and data['delegated_operation_ids'] == []
    actor = data['actor']
    if audience in {'operator', 'administrator'}:
        user = values[3] if audience == 'administrator' else values[4]
        assert actor['user_id'] == user.id and actor['subject_id'] == user.subject_id
        assert actor['platform_administrator'] == (audience == 'administrator')
    else:
        assert actor['kind'] == ('anonymous' if audience == 'public' else 'kiosk')
        assert actor['user_id'] is None and actor['subject_id'] is None
        assert data['permission_ids'] == []
    assert not {'token','jti','sid','configuration','socket_path'} & actor.keys()
    assert not calls


@pytest.mark.parametrize("change", ["artifact", "entrypoint", "version", "extra"])
def test_stale_forged_or_open_binding_never_dispatches(setup, change):
    values, base, audience, auth, binding, calls = setup
    changed = dict(binding)
    if change == "artifact":
        changed["artifact_sha256"] = "f" * 64
    elif change == "entrypoint":
        changed["entrypoint_id"] = "missing"
    elif change == "version":
        changed["host_version"] = True
    else:
        changed["user_id"] = 1
    assert values[0].post(
        operation_url(base, audience),
        headers=auth,
        json={
            "payload": {},
            "idempotency_key": "ui-host-test-2",
            "ui_context": changed,
        },
    ).status_code in {403, 409, 422}
    assert calls == []


def test_disable_between_info_and_invoke_refuses_without_service_call(setup):
    values, base, audience, auth, binding, calls = setup
    client, db, _, _, _, installation, *_ = values
    assert client.get(info_url(base, binding), headers=auth).status_code == 200
    installation.enabled = False
    db.commit()
    assert client.get(info_url(base, binding), headers=auth).status_code in {401, 409}
    assert client.post(
        operation_url(base, audience),
        headers=auth,
        json={
            "payload": {},
            "idempotency_key": "ui-host-test-3",
            "ui_context": binding,
        },
    ).status_code in {401, 409}
    assert calls == []


def test_route_context_cannot_promote_audience_even_for_admin(setup):
    values, base, audience, auth, binding, calls = setup
    if audience == "administrator":
        target = base + "/operator/operations/approve"
    else:
        target = base + "/operations/approve"
    assert (
        values[0]
        .post(
            target,
            headers=headers(values[7]),
            json={
                "payload": {},
                "idempotency_key": "ui-host-test-4",
                "ui_context": binding,
            },
        )
        .status_code
        == 403
    )
    assert calls == []


def test_revoke_between_snapshot_and_dispatch(setup):
    values, base, audience, auth, binding, calls = setup
    if audience == "public":
        # Public operations intentionally remain public, not user grants.
        return
    client, db, _, _, user, installation, _, admin_token, _ = values
    assert client.get(info_url(base, binding), headers=auth).status_code == 200
    if audience == "operator":
        client.delete(
            base + f"/permissions/grants/{user.id}/records_manage",
            headers=headers(admin_token),
        )
    elif audience == "administrator":
        values[3].role = "user"
        db.commit()
    else:
        terminal = client.get(
            base + "/kiosk/terminals", headers=headers(admin_token)
        ).json()["items"][0]
        client.delete(
            base + "/kiosk/terminals/" + terminal["terminal_id"],
            headers=headers(admin_token),
        )
    assert client.get(info_url(base, binding), headers=auth).status_code in {401, 403}
    assert client.post(
        operation_url(base, audience),
        headers=auth,
        json={
            "payload": {},
            "idempotency_key": "ui-host-test-5",
            "ui_context": binding,
        },
    ).status_code in {401, 403}
    assert calls == []
