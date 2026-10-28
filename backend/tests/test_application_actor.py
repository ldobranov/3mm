from backend.tests.test_application_access import kiosk_enrollment,kiosk_claim
"""CAP02 Core HTTP admission -> actual SDK context, without a device or grants from payload."""
import pytest
from sqlalchemy import delete

from backend.db.module import ApplicationPermissionGrant
from backend.db.association_tables import user_roles, user_groups, group_roles, role_application_grants
from backend.db.role import Role, Group
from backend.services import application_extensions as gateway
from backend.tests.test_application_access import environment, headers
from backend.tests.test_module_packages import application_definition, application_package
from three_mm_application_sdk import OperationContext


@pytest.fixture
def app(monkeypatch, tmp_path):
    definition = application_definition()
    definition["operations"][2]["input_schema"] = {"type": "object", "properties": {
        "user_id": {"type": "integer"},
        "permission_ids": {"type": "array", "items": {"type": "string"}},
        "actor": {"type": "object", "properties": {"kind": {"type": "string"},
            "platform_administrator": {"type": "boolean"}}}}, "additionalProperties": False}
    values = environment(monkeypatch, tmp_path, application_package(definition=definition))
    yield values
    values[0].close(); values[1].close(); values[2].dispose()


def test_platform_admin_needs_an_explicit_business_permission_on_operator_path(app):
    client, db, _, admin, _, installation, package, token, _ = app
    base = f"/api/v1/application-extensions/{package.module_id}"
    body = dict(payload={}, idempotency_key="admin-operator-test")
    assert client.post(base + "/operator/operations/approve", headers=headers(token), json=body).status_code == 403
    access = client.get(base + "/access", headers=headers(token)).json()
    assert access["platform_administrator"] and access["permission_ids"] == []
    assert access["allowed_route_ids"] == []
    # The author's explicitly declared platform-administrator endpoint remains
    # distinct from the business operator endpoint.
    assert client.post(base + "/operations/approve", headers=headers(token), json=body).status_code == 200
    granted = client.post(base + "/permissions/grants", headers=headers(token),
        json=dict(user_id=admin.id, permission_id="records_manage"))
    assert granted.status_code == 201
    assert client.post(base + "/operator/operations/approve", headers=headers(token), json=body).status_code == 200
    assert client.delete(base + f"/permissions/grants/{admin.id}/records_manage", headers=headers(token)).status_code == 200
    assert client.post(base + "/operator/operations/approve", headers=headers(token), json=body).status_code == 403


def test_server_context_keeps_the_real_actor_and_declared_permissions(app, monkeypatch):
    client, db, _, admin, user, installation, package, _, token = app
    for name in ("records_manage", "obsolete_permission"):
        db.add(ApplicationPermissionGrant(application_installation_id=installation.id,
            user_id=user.id, permission_id=name))
    db.commit()
    received = []
    class Recorder:
        def __init__(self, *_args): pass
        def invoke(self, _operation, payload, context):
            received.append((payload, OperationContext.from_platform(context)))
            return {}
    monkeypatch.setattr(gateway, "ApplicationServiceClient", Recorder)
    base = f"/api/v1/application-extensions/{package.module_id}"
    claimed = dict(user_id=admin.id, permission_ids=["all_business_data"],
        actor={"kind": "user", "platform_administrator": True})
    result = client.post(base + "/operator/operations/approve", headers=headers(token),
        json=dict(payload=claimed, idempotency_key="actor-payload-test"))
    assert result.status_code == 200, result.text
    payload, context = received[0]
    assert payload == claimed  # Business input is never trusted identity metadata.
    assert context.actor.user_id == user.id and not context.actor.platform_administrator
    assert context.permission_ids == ("records_manage",)
    assert not context.has_application_permission("all_business_data")
    assert client.get(base + "/access", headers=headers(token)).json()["permission_ids"] == ["records_manage"]


def test_revocation_after_dispatch_withholds_the_result_without_replaying(app, monkeypatch):
    client, db, _, _, user, installation, package, _, token = app
    db.add(ApplicationPermissionGrant(application_installation_id=installation.id,
        user_id=user.id, permission_id="records_manage")); db.commit()
    calls = []
    class RevokingService:
        def __init__(self, *_args): pass
        def invoke(self, _operation, _payload, context):
            calls.append(OperationContext.from_platform(context))
            db.execute(delete(ApplicationPermissionGrant)); db.commit()
            return {}
    monkeypatch.setattr(gateway, "ApplicationServiceClient", RevokingService)
    url = f"/api/v1/application-extensions/{package.module_id}/operator/operations/approve"
    body = dict(payload={}, idempotency_key="actor-revocation-test")
    result = client.post(url, headers=headers(token), json=body)
    assert result.status_code == 409 and "unconfirmed" in result.text
    assert len(calls) == 1 and calls[0].has_application_permission("records_manage")
    assert client.post(url, headers=headers(token), json=body).status_code == 403
    assert len(calls) == 1


@pytest.mark.parametrize("via_group", [False, True])
def test_role_membership_is_current_and_does_not_promote_the_user(app, via_group):
    client, db, _, _, user, installation, package, _, token = app
    role = Role(name="Business administrator")
    db.add(role); db.commit()
    if via_group:
        group = Group(name="Business team"); db.add(group); db.commit()
        db.execute(user_groups.insert().values(user_id=user.id, group_id=group.id))
        db.execute(group_roles.insert().values(group_id=group.id, role_id=role.id))
    else:
        db.execute(user_roles.insert().values(user_id=user.id, role_id=role.id))
    db.execute(role_application_grants.insert().values(role_id=role.id,
        installation_id=installation.id, permission_id="records_manage")); db.commit()
    base = f"/api/v1/application-extensions/{package.module_id}"
    access = client.get(base + "/access", headers=headers(token)).json()
    assert access["permission_ids"] == ["records_manage"] and not access["platform_administrator"]
    body = dict(payload={}, idempotency_key="role-membership-test")
    assert client.post(base + "/operator/operations/approve", headers=headers(token), json=body).status_code == 200
    assert client.post(base + "/operations/approve", headers=headers(token), json=body).status_code == 403
    if via_group:
        db.execute(user_groups.delete().where(user_groups.c.user_id == user.id))
    else:
        db.execute(user_roles.delete().where(user_roles.c.user_id == user.id))
    db.commit()
    assert client.get(base + "/access", headers=headers(token)).json()["permission_ids"] == []
    assert client.post(base + "/operator/operations/approve", headers=headers(token), json=body).status_code == 403


@pytest.mark.parametrize("audience", ["public", "kiosk"])
def test_public_and_kiosk_dispatch_have_no_borrowed_user_identity(monkeypatch, tmp_path, audience):
    definition = application_definition()
    definition["operations"][1]["audiences"] = ["public", "kiosk"]
    definition["operations"][1]["input_schema"] = {"type": "object",
        "properties": {"user_id": {"type": "integer"}}, "additionalProperties": False}
    values = environment(monkeypatch, tmp_path, application_package(definition=definition))
    client, db, engine, admin, _, _, package, token, _ = values
    received = []
    class Recorder:
        def __init__(self, *_args): pass
        def invoke(self, _operation, _payload, context):
            received.append(OperationContext.from_platform(context)); return {}
    monkeypatch.setattr(gateway, "ApplicationServiceClient", Recorder)
    base = f"/api/v1/application-extensions/{package.module_id}"
    try:
        terminal = None
        if audience == "kiosk":
            code = client.post(base + "/kiosk/enrollments", headers=headers(token), json=kiosk_enrollment('Actor test')).json()["code"]
            claimed = client.post(base + "/kiosk/enrollments/claim", json=kiosk_claim(code)).json()
            terminal, token = claimed["terminal_id"], claimed["access_token"]
        result = client.post(base + f"/{audience}/operations/register", headers=headers(token),
            json=dict(payload={"user_id": admin.id}, idempotency_key="nonhuman-actor-test"))
        assert result.status_code == 200, result.text
        context = received[0]
        assert context.actor.kind == ("anonymous" if audience == "public" else "kiosk")
        assert context.actor.user_id is None and context.actor.terminal_id == terminal
        assert context.permission_ids == () and not context.actor.platform_administrator
    finally:
        client.close(); db.close(); engine.dispose()
