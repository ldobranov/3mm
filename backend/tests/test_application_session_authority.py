"""Real M20 sealed review/apply/revoke and live logins; no installed services."""

import asyncio
import json
import os
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from backend.db.application_authority_grant import ApplicationAuthorityGrant as Grant
from backend.db.association_tables import role_application_grants, user_roles
from backend.db.authority import CoreAuthorityGuard
from backend.db.base import Base
from backend.db.device import (
    Device,
    DeviceCapabilityHealth,
    DeviceCapabilityProvider,
    DeviceCredential,
    DeviceHeartbeat,
    DevicePlatformState,
    DeviceRuntimeFeatures,
)
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.db.module import ApplicationPermissionGrant
from backend.db.role import Role
from backend.db.session import UserSession
from backend.db.user import User
from backend.routes.application_authority import router
from backend.services.application_authority_management import (
    AuthorityManagementError,
    effect_admission,
)
from backend.services.application_session_authority import (
    M20SessionAuthority,
    SessionAuthorityError,
)
from backend.services.device_capability_registry import capability_catalog
from backend.tests.test_application_authority_management import (
    decide,
    identity,
)
from backend.tests.test_application_authority_management import (
    installed as managed_installed,
)
from backend.tests.test_application_authority_management import (
    native,
)
from backend.tests.test_application_authority_sources import DEVICE
from backend.tests.test_application_authority_subjects import (
    installed as source_subject,
)
from backend.tests.test_application_authority_subjects import (
    source_installed,
)
from backend.tests.test_application_checkpoint_authority import (
    checkpoint_app,
    store_checkpoint_package,
)
from backend.utils.db_utils import get_db
from backend.utils.jwt_utils import create_access_token
from three_mm_protocol.interactive_session import SessionOpenRequestV1
from three_mm_runtime.session_output import SessionOutputError, pump_session_output

pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="Real POSIX Core review keys"
)
CAPABILITY = "org.example.console"
PROVIDER = "org.example.provider"
SCOPE = "session:console:open"
SESSION = "ses_" + "c" * 32


@pytest.fixture
def session_app(checkpoint_app, request):
    state = checkpoint_app
    mode = getattr(request, "param", "write")
    definition = state.validated.application_extension.model_dump(mode="json")
    definition.update(
        checkpoints=[],
        permissions=[
            {
                "permission_id": "session_use",
                "label": {"en": "Use console"},
                "description": {"en": "Use this application's exact reviewed session"},
            }
        ],
        session_bindings=[
            {
                "contract_version": 1,
                "binding_id": "console",
                "target_device_config_key": "TARGET_DEVICE_ID",
                "provider_id": PROVIDER,
                "capability_id": CAPABILITY,
                "access_mode": mode,
                "control_actions": ["resize"] if mode == "write" else [],
                "required_permission": "session_use",
                "options": {"columns": 80, "rows": 24},
            }
        ],
    )
    manifest = state.validated.manifest.model_dump(mode="json")
    manifest["permissions"].append("sessions.open")
    manifest["capabilities"]["consumes"] = [CAPABILITY]
    store_checkpoint_package(state, definition, manifest)
    Base.metadata.create_all(
        state.engine,
        tables=[
            Base.metadata.tables[name]
            for name in (
                "roles",
                "groups",
                "user_roles",
                "user_groups",
                "group_roles",
                "role_application_grants",
                "application_permission_grants",
            )
        ],
    )
    with Session(state.engine) as db, db.begin():
        provider = db.get(DeviceCapabilityProvider, 1)
        provider.capabilities = [
            {
                "capability_id": CAPABILITY,
                "metadata": {
                    "interactive_session_contract": json.dumps(
                        {
                            "contract_version": 1,
                            "access_modes": ["read", "write"],
                            "control_actions": ["resize"],
                        }
                    ),
                },
            }
        ]
        provider.configured_capability_ids = [CAPABILITY]
        runtime = db.get(DeviceRuntimeFeatures, 1)
        runtime.declaration = {
            **runtime.declaration,
            "features": [*runtime.declaration["features"], "interactive_sessions.v1"],
        }
        db.flush()
        digest = capability_catalog(db, db.get(Device, 1))[0].declaration_digest
        health = db.scalar(select(DeviceCapabilityHealth))
        health.report = {
            "declaration_digest": digest,
            "capabilities": [{"capability_id": CAPABILITY, "healthy": True}],
        }
        db.add(
            ApplicationPermissionGrant(
                application_installation_id=1,
                user_id=2,
                permission_id="session_use",
                granted_by=1,
            )
        )
    state.session_authority = M20SessionAuthority(state.manager)
    state.request = SessionOpenRequestV1(
        request_id="console_1",
        device_id=DEVICE,
        provider_id=PROVIDER,
        capability_id=CAPABILITY,
        access_mode=mode,
        options={"columns": 80, "rows": 24},
    )
    return state


def review(state, proof=None, scopes=None):
    proof = proof or native(state)
    return state.manager.create_review(
        1,
        actor_token=state.token,
        request_id=identity(),
        native_review_id=proof["native_review_id"],
        scopes=[SCOPE] if scopes is None else scopes,
    )


def activate(state, scopes=None):
    with state.engine.begin() as db:
        db.execute(update(Installation).values(enabled=False, status="disabled"))
    proof = native(state)
    decide(state, decide(state, review(state, proof, scopes), "approve"), "apply")
    with state.engine.begin() as db:
        db.execute(
            update(Installation).values(
                enabled=True, status="active", authority_epoch=identity()
            )
        )
    return decide(
        state, decide(state, review(state, proof, scopes), "approve"), "apply"
    )


def admit(state, **changes):
    return state.session_authority.admit(
        **{
            "installation_id": 1,
            "binding_id": "console",
            "session_id": SESSION,
            "authorization": "Bearer " + state.user_token,
            "request": state.request,
            **changes,
        }
    )


def check(state, bound, **changes):
    return state.session_authority.check(
        bound,
        **{
            "authorization": "Bearer " + state.user_token,
            "request": state.request,
            "session_id": SESSION,
            "operation": "output",
            **changes,
        },
    )


def test_real_review_is_explicit_and_neither_native_nor_approve_grants_a_session(
    session_app,
):
    state = session_app
    with state.engine.begin() as db:
        db.execute(update(Installation).values(enabled=False, status="disabled"))
    proof = native(state)
    with pytest.raises(SessionAuthorityError):
        admit(state)
    plan = review(state, proof)
    assert plan["scopes"] == [SCOPE]
    assert len(plan["resources"]["sessions"]) == 1
    resource = plan["resources"]["sessions"][0]
    assert resource["target_device_id"] == DEVICE
    assert resource["owner"]["application_installation_id"] == "1"
    assert resource["package_artifact_sha256"] == state.validated.sha256
    assert resource["declaration"]["required_permission"] == "session_use"
    approved = decide(state, plan, "approve")
    with Session(state.engine) as db:
        assert db.get(Grant, 1) is None
    with pytest.raises(SessionAuthorityError):
        admit(state)
    assert decide(state, approved, "apply")["state"] == "applied"
    with pytest.raises(SessionAuthorityError):
        admit(state)  # Apply did not enable the stopped application.
    activate(state)
    bound = admit(state)
    assert check(state, bound) is None
    assert bound.user_id == 2 and bound.login_session_id == 2
    # Permission proof is not evidence of a connected/isolated runtime.
    status = state.manager.inspect(1)
    assert status["runtime_blockers"] == ["session_runtime_not_connected"]
    assert not status["grant_effective"]
    assert state.token not in repr(bound) and state.user_token not in repr(bound)


def test_compatibility_and_empty_selection_never_allow_a_session(session_app):
    with pytest.raises(SessionAuthorityError):
        admit(session_app)
    with Session(session_app.engine) as db, pytest.raises(ValueError):
        with effect_admission(db, 1, SCOPE):
            pytest.fail("Generic/compatibility lease admitted a session")
    activate(session_app, scopes=[])
    with pytest.raises(SessionAuthorityError):
        admit(session_app)


@pytest.mark.parametrize(
    "change",
    [
        "service",
        "human",
        "login",
        "blocked",
        "token_version",
        "key",
        "recovery",
        "incarnation",
        "configuration",
        "instance",
        "disabled",
        "device",
        "credential",
        "control",
        "provider",
        "runtime",
        "offline",
        "health",
        "login_expired",
        "seal",
        "native",
    ],
)
def test_live_session_loses_access_after_real_authority_drift(session_app, change):
    state = session_app
    activate(state)
    bound = admit(state)
    if change == "service":
        state.manager.revoke(
            1,
            actor_token=state.token,
            request_id=identity(),
            expected_revision=state.manager.inspect(1)["grant_record_revision"],
        )
    elif change == "key":
        state.keys.rotate(expected_key_id=state.keys.identity().key_id)
    elif change == "native":
        proof = state.manager.inspect(1)["native_reviews"][0]
        state.manager.revoke_native_review(
            1,
            actor_token=state.token,
            request_id=identity(),
            native_review_id=proof["native_review_id"],
            expected_revision=proof["revision"],
        )
    else:
        with state.engine.begin() as db:
            if change == "human":
                db.execute(delete(ApplicationPermissionGrant))
            elif change == "login":
                db.execute(
                    update(UserSession)
                    .where(UserSession.id == 2)
                    .values(is_active=False)
                )
            elif change == "login_expired":
                db.execute(
                    update(UserSession)
                    .where(UserSession.id == 2)
                    .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
                )
            elif change == "seal":
                db.execute(update(Grant).values(seal="0" * 64))
            elif change == "blocked":
                db.execute(update(User).where(User.id == 2).values(is_blocked=True))
            elif change == "token_version":
                db.execute(update(User).where(User.id == 2).values(token_version=1))
            elif change == "recovery":
                db.execute(update(CoreAuthorityGuard).values(generation=identity()))
            elif change == "incarnation":
                db.execute(
                    update(Installation).values(authority_incarnation=identity())
                )
            elif change == "configuration":
                db.execute(
                    update(Installation).values(
                        configuration={**state.configuration, "PRIVATE_NOTE": "changed"}
                    )
                )
            elif change == "instance":
                db.execute(update(Installation).values(instance_id="f" * 24))
            elif change == "disabled":
                db.execute(
                    update(Installation).values(enabled=False, status="disabled")
                )
            elif change == "device":
                db.execute(update(Device).values(revoked_at=datetime.now(UTC)))
            elif change == "credential":
                db.execute(
                    update(DeviceCredential).values(revoked_at=datetime.now(UTC))
                )
            elif change == "control":
                db.execute(
                    update(DevicePlatformState).values(control_generation=identity())
                )
            elif change == "provider":
                db.execute(update(DeviceCapabilityProvider).values(revision=9))
            elif change == "runtime":
                db.execute(update(DeviceRuntimeFeatures).values(revision=8))
            elif change == "offline":
                db.execute(delete(DeviceHeartbeat))
            else:
                db.execute(
                    update(DeviceCapabilityHealth).values(
                        expires_at=datetime.now(UTC) - timedelta(seconds=1)
                    )
                )
    with pytest.raises(SessionAuthorityError):
        check(state, bound)


@pytest.mark.parametrize(
    "changes",
    [
        {"device_id": "dev_" + "f" * 32},
        {"provider_id": "org.example.foreign"},
        {"capability_id": "org.example.other"},
        {"access_mode": "read"},
        {"options": {"columns": 80.0, "rows": 24}},
        {"options": {"command": "/bin/sh"}},
        {"options": {"columns": {80}, "rows": 24}},
    ],
)
def test_caller_cannot_widen_a_reviewed_target_mode_or_options(session_app, changes):
    activate(session_app)
    request = session_app.request.model_copy(update=changes)
    with pytest.raises(SessionAuthorityError):
        admit(session_app, request=request)


def test_no_cross_user_session_or_implicit_admin_bypass(session_app):
    state = session_app
    activate(state)
    bound = admit(state)
    with pytest.raises(SessionAuthorityError):
        check(state, bound, session_id="ses_" + "d" * 32)
    with pytest.raises(SessionAuthorityError):
        check(state, bound, authorization="Bearer " + state.token)
    with pytest.raises(SessionAuthorityError):
        admit(state, authorization="Bearer " + state.token)
    # Even after the other human has an explicit grant, the old session stays owned.
    with Session(state.engine) as db, db.begin():
        db.add(
            ApplicationPermissionGrant(
                application_installation_id=1,
                user_id=1,
                permission_id="session_use",
                granted_by=1,
            )
        )
    assert admit(state, authorization="Bearer " + state.token).user_id == 1
    with pytest.raises(SessionAuthorityError):
        check(state, bound, authorization="Bearer " + state.token)


@pytest.mark.parametrize(
    "claims",
    [
        {},
        {"sid": True},
        {"sid": 999},
        {"sid": 1},
        {"sid": 2, "token_type": "application_kiosk"},
    ],
)
def test_untracked_foreign_and_machine_logins_are_refused(session_app, claims):
    activate(session_app)
    token = create_access_token("2", {"token_version": 0, **claims})
    with pytest.raises(SessionAuthorityError):
        admit(session_app, authorization="Bearer " + token)


@pytest.mark.parametrize("session_app", ["read"], indirect=True)
def test_read_session_is_not_input_or_control_authority(session_app):
    activate(session_app)
    bound = admit(session_app)
    check(session_app, bound)
    for operation, action in (
        ("input", None),
        ("control", "resize"),
        ("terminate_foreign", None),
    ):
        with pytest.raises(SessionAuthorityError):
            check(session_app, bound, operation=operation, control_action=action)


def test_reapproval_does_not_resurrect_an_old_session_binding(session_app):
    state = session_app
    activate(state)
    bound = admit(state)
    state.manager.revoke(
        1,
        actor_token=state.token,
        request_id=identity(),
        expected_revision=state.manager.inspect(1)["grant_record_revision"],
    )
    decide(state, decide(state, review(state), "approve"), "apply")
    assert admit(state).grant_revision != bound.grant_revision
    with pytest.raises(SessionAuthorityError):
        check(state, bound)


def test_live_role_grants_are_independent_from_service_and_token_role_claim(
    session_app,
):
    state = session_app
    activate(state)
    with state.engine.begin() as db:
        db.execute(delete(ApplicationPermissionGrant))
    with pytest.raises(SessionAuthorityError):
        admit(state)  # Spoofed role=admin in the signed fixture token is not enough.
    with Session(state.engine) as db, db.begin():
        db.add(Role(id=1, name="Console operators"))
        db.flush()
        db.execute(user_roles.insert().values(user_id=2, role_id=1))
        db.execute(
            role_application_grants.insert().values(
                role_id=1, installation_id=1, permission_id="session_use"
            )
        )
    bound = admit(state)
    assert check(state, bound) is None
    with state.engine.begin() as db:
        db.execute(delete(user_roles))
    with pytest.raises(SessionAuthorityError):
        check(state, bound)


@pytest.mark.parametrize(
    "change",
    ["missing_contract", "wrong_provider", "unsupported_mode", "missing_runtime"],
)
def test_incomplete_provider_evidence_cannot_become_a_reviewed_session(
    session_app, change
):
    state = session_app
    with Session(state.engine) as db, db.begin():
        if change == "missing_runtime":
            runtime = db.get(DeviceRuntimeFeatures, 1)
            runtime.declaration = {
                **runtime.declaration,
                "features": [
                    value
                    for value in runtime.declaration["features"]
                    if value != "interactive_sessions.v1"
                ],
            }
        else:
            provider = db.get(DeviceCapabilityProvider, 1)
            declarations = json.loads(json.dumps(provider.capabilities))
            if change == "missing_contract":
                declarations[0]["metadata"] = {}
            elif change == "unsupported_mode":
                declarations[0]["metadata"]["interactive_session_contract"] = (
                    json.dumps(
                        {
                            "contract_version": 1,
                            "access_modes": ["read"],
                            "control_actions": ["resize"],
                        }
                    )
                )
            else:
                provider.provider_id = "org.example.foreign"
            provider.capabilities = declarations
    with pytest.raises(AuthorityManagementError):
        native(state)
    with pytest.raises(SessionAuthorityError):
        admit(state)


def test_real_human_revocation_closes_idle_provider_without_output(session_app):
    state = session_app
    activate(state)
    bound = admit(state)

    async def scenario():
        class Provider:
            closed = 0

            async def read_output(self, session_id):
                await asyncio.Event().wait()

            async def close(self, session_id, reason):
                assert session_id == SESSION
                self.closed += 1

        provider = Provider()

        async def no_send(_):
            pytest.fail("Revoked idle session disclosed output")

        pump = asyncio.create_task(
            pump_session_output(
                provider,
                SESSION,
                no_send,
                authorize=state.session_authority.output_checker(
                    bound,
                    authorization="Bearer " + state.user_token,
                    request=state.request,
                    session_id=SESSION,
                ),
                check_interval=1.0,
            )
        )
        await asyncio.sleep(0.1)
        with state.engine.begin() as db:
            db.execute(delete(ApplicationPermissionGrant))
        with pytest.raises(SessionOutputError):
            await asyncio.wait_for(pump, timeout=4)
        assert provider.closed == 1

    asyncio.run(scenario())


def test_session_scope_uses_existing_authenticated_review_http_flow(session_app):
    state = session_app
    with state.engine.begin() as db:
        db.execute(update(Installation).values(enabled=False, status="disabled"))
    proof = native(state)
    app = FastAPI()
    app.include_router(router)

    def database():
        with Session(state.engine) as db:
            yield db

    app.dependency_overrides[get_db] = database
    path = (
        "/api/v1/application-extensions/"
        + state.validated.manifest.module_id
        + "/authority/reviews"
    )
    payload = {
        "request_id": identity(),
        "native_review_id": proof["native_review_id"],
        "scopes": [SCOPE],
    }
    with TestClient(app) as client:
        assert client.post(path, json=payload).status_code == 401
        assert (
            client.post(
                path,
                json=payload,
                headers={"Authorization": "Bearer " + state.user_token},
            ).status_code
            == 403
        )
        response = client.post(
            path, json=payload, headers={"Authorization": "Bearer " + state.token}
        )
        assert response.status_code == 200, response.text
        assert response.json()["scopes"] == [SCOPE]
        assert response.headers["cache-control"] == "no-store"


def test_session_context_preserves_checkpoint_admission_without_implied_session_access(
    session_app,
):
    state = session_app
    definition = state.validated.application_extension.model_dump(mode="json")
    definition["checkpoints"] = [
        {
            "contract_version": 1,
            "checkpoint_id": "cursor",
            "mode": "read",
            "max_value_bytes": 1024,
        }
    ]
    store_checkpoint_package(state, definition)
    activate(state, scopes=["checkpoint:cursor:read"])
    with Session(state.engine) as db:
        with effect_admission(db, 1, "checkpoint:cursor:read") as lease:
            assert lease.compatibility is False
            assert lease.identities == () and lease.status_projections == ()
            db.commit()
            lease()
    with pytest.raises(SessionAuthorityError):
        admit(state)


def test_optional_sessions_do_not_relax_required_older_resource_grants(session_app):
    state = session_app
    definition = state.validated.application_extension.model_dump(mode="json")
    definition["checkpoints"] = [
        {
            "contract_version": 1,
            "checkpoint_id": "cursor",
            "mode": "read",
            "max_value_bytes": 1024,
        }
    ]
    store_checkpoint_package(state, definition)
    with pytest.raises(AuthorityManagementError, match="selection_not_allowed"):
        review(state)  # Session-only selection cannot omit the old checkpoint.
    activate(state, scopes=[SCOPE, "checkpoint:cursor:read"])
    assert check(state, admit(state)) is None
