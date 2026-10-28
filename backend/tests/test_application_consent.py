"""Administrator package consent uses real POSIX seals/current logins, no devices."""
import json
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.db.base import Base
from backend.db.application_authority_grant import ApplicationAuthorityPlan as Plan, ApplicationAuthorityGrant as Grant, ApplicationNativeReview as Native
from backend.db.audit_log import AuditLog
from backend.db.authority import CoreAuthorityGuard
from backend.db.module import ApplicationExtensionInstallation as Installation, ApplicationPermissionGrant
from backend.db.session import UserSession
from backend.db.user import User
from backend.routes.application_authority import router
from backend.services import application_consent as consent
from backend.services.application_authority_keys import KEY_NAME, AuthorityReviewKeyError
from backend.services.application_authority_management import AuthorityManagementError, _load
from backend.tests.test_application_authority_management import identity, installed, source_subject, source_installed
from backend.tests.test_application_ui_authority import ui_app, managed_installed
from backend.tests.test_application_relational_review_api import db_app, READ, WRITE
from backend.utils.db_utils import get_db

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Real Core-owned key files/flock and SQLite authority transactions")


@pytest.fixture
def state(installed):
    Base.metadata.create_all(installed.engine)
    return installed


def preview(s, **overrides):
    return consent.preview(s.manager, 1, actor_token=s.token, request_id=overrides.pop("request_id", identity()), **overrides)


def allow(s, reviewed, **overrides):
    payload = {"request_id": identity(), "preview_id": reviewed["preview_id"],
        "expected_revision": reviewed["revision"], "fingerprint": reviewed["fingerprint"],
        "scopes": reviewed["selected_scopes"], "user_permissions": reviewed["selected_user_permissions"],
        "accept_native_code": True}
    payload.update(overrides)
    return consent.allow(s.manager, 1, actor_token=s.token, **payload)


def read(s, kind, model, identifier):
    with s.manager.keys.locked() as key, Session(s.engine) as db, db.begin():
        return _load(db, key, kind, db.get(model, identifier), identifier)


def test_preview_is_default_selected_but_never_trust_or_resource_approval(state):
    s=state
    reviewed=preview(s)
    assert reviewed["consent_version"]==1 and reviewed["access_saved"] is False
    assert reviewed["scopes"]==reviewed["selected_scopes"]==["command:pulse", "connector:business_api"]
    assert reviewed["built_ui_sha256"] is None and reviewed["user_permissions"]==[]
    assert reviewed["installation_enabled"] and reviewed["installation_status"]=="active"
    assert reviewed["resources"]["commands"] and reviewed["resources"]["connectors"]
    record=read(s,"plan",Plan,reviewed["preview_id"])
    assert record["data"]["kind"]==consent.KIND and record["state"]=="consent_preview"
    with Session(s.engine) as db:
        assert db.scalar(select(Native.review_id)) is None
        assert db.get(Grant,1) is None
        assert db.get(Installation,1).authority_mode=="compatibility"


def test_preview_provisions_only_missing_key_and_audits_neutral_infrastructure(state):
    s=state
    (s.key_directory/KEY_NAME).unlink()
    reviewed=preview(s)
    first=(s.key_directory/KEY_NAME).read_bytes()
    assert reviewed["access_saved"] is False
    preview(s)
    assert (s.key_directory/KEY_NAME).read_bytes()==first
    with Session(s.engine) as db:
        events=list(db.scalars(select(AuditLog).where(AuditLog.action=="APPLICATION_AUTHORITY_KEY")))
        assert len(events)==1 and events[0].changes["permission_approval"]=="not_evaluated"
        assert db.get(Grant,1) is None and db.scalar(select(Native.review_id)) is None


@pytest.mark.parametrize("fault",["corrupt","stale"])
def test_preview_never_repairs_existing_unusable_key(state,fault):
    s=state
    if fault=="corrupt":(s.key_directory/KEY_NAME).write_text("not-a-key")
    else:
        with s.engine.begin() as db:db.execute(update(CoreAuthorityGuard).values(generation=identity()))
    before=(s.key_directory/KEY_NAME).read_bytes()
    with pytest.raises(AuthorityReviewKeyError):preview(s)
    assert (s.key_directory/KEY_NAME).read_bytes()==before
    with Session(s.engine) as db:assert db.get(Grant,1) is None


def test_allow_saves_exact_administrator_consent_without_manual_review_claims(state):
    s=state
    reviewed=preview(s)
    result=allow(s,reviewed,scopes=["command:pulse"])
    assert result["saved"] is True and result["effective"] is True
    assert result["preview_id"]==reviewed["preview_id"]
    grant=read(s,"grant",Grant,1)
    assert grant["data"]["selection"]["scopes"]==["command:pulse"]
    native=read(s,"native",Native,grant["data"]["native_review_id"])
    assert native["state"]=="administrator_approved"
    assert native["data"]["review_kind"]=="authenticated_administrator_package_consent"
    assert "review_document_sha256" not in native["data"] and "native_code_review_completed" not in native["data"]
    assert grant["data"]["policy"]["required_scopes"]==[]
    assert grant["data"]["policy"]["execution_class"]=="administrator_approved_native"
    fresh=preview(s)
    assert fresh["access_saved"] and fresh["selected_scopes"]==["command:pulse"]


def test_empty_selection_is_saved_code_consent_and_does_not_default_back_to_all(state):
    s=state
    result=allow(s,preview(s),scopes=[])
    assert result["saved"] is True
    assert read(s,"grant",Grant,1)["data"]["selection"]["scopes"]==[]
    fresh=preview(s)
    assert fresh["access_saved"] is True and fresh["selected_scopes"]==[]


def test_web_lifecycle_recovery_requires_fresh_consent_without_losing_choices(state, monkeypatch, tmp_path):
    from types import SimpleNamespace
    from backend.routes import application_extensions as lifecycle_routes
    from backend.services.application_package_staging import stage_application_package
    s = state
    # Current packages have sealed inert provenance before their first start.
    # The older adoption fixture must pass through that real preparation path.
    with Session(s.engine) as db, db.begin():
        db.execute(update(Installation).where(Installation.id == 1).values(status='disabled', enabled=False))
    stage_application_package(s.engine, s.validated.sha256, lifecycle_routes.StageApplicationPackageRequest(
        request_id=identity(), expected_artifact_sha256=s.validated.sha256,
        expected_revision=None, configuration={}), s.token)
    allow(s, preview(s), scopes=[])
    previous = read(s, 'grant', Grant, 1)
    with Session(s.engine) as db, db.begin():
        db.execute(update(Installation).where(Installation.id == 1).values(status='recovery_required', enabled=False))
    app = FastAPI(); app.include_router(lifecycle_routes.router)
    def database():
        with Session(s.engine) as db: yield db
    app.dependency_overrides[get_db] = database
    monkeypatch.setattr(lifecycle_routes, 'get_settings', lambda: SimpleNamespace(
        applications=SimpleNamespace(helper_socket=tmp_path/'unused.sock')))
    calls = []
    def recover(_self, instance_id, actor_id, context):
        calls.append(instance_id)
        return dict(status='disabled', instance_id=instance_id, lifecycle=context, quiescent=True)
    monkeypatch.setattr(lifecycle_routes.UpdateHelperClient, 'recover_application_extension', recover)
    with TestClient(app) as client:
        response = client.post('/api/v1/application-extensions/'+s.validated.manifest.module_id+'/lifecycle/recover',
            headers={'Authorization': 'Bearer '+s.token}, json={'confirmed_external_outcome_reviewed': True})
    assert response.status_code == 200, response.text
    assert response.json()['active_version'] is None
    reviewed = preview(s)
    assert reviewed['access_saved'] is False
    assert reviewed['selected_scopes'] == []  # No default restoration of old/all rights.
    assert reviewed['installation_status'] == 'disabled' and not reviewed['installation_enabled']
    assert read(s, 'grant', Grant, 1) == previous  # Preview did not renew anything.
    assert not s.manager.inspect(1)['grant_effective']
    confirmed = allow(s, reviewed, scopes=[])
    assert confirmed['saved'] and not confirmed['effective']
    assert preview(s)['access_saved'] is True
    assert len(calls) == 1  # No activation, code execution or operation retry.


def test_ordinary_disabled_version_keeps_saved_empty_selection(state):
    s = state
    allow(s, preview(s), scopes=[])
    with Session(s.engine) as db, db.begin():
        db.execute(update(Installation).where(Installation.id == 1).values(
            status='disabled', enabled=False, active_version=s.validated.manifest.version, authority_epoch=identity()))
    reviewed = preview(s)
    assert reviewed['access_saved'] and reviewed['selected_scopes'] == []
    assert not reviewed['installation_enabled']


@pytest.mark.parametrize("changed",["fingerprint","revision","expiry","reboot","guard","configuration","actor","human_grants"])
def test_changed_preview_or_current_authority_denies_without_partial_grants(state,monkeypatch,changed):
    s=state
    reviewed=preview(s)
    options={}
    if changed=="fingerprint":options["fingerprint"]="a"*64
    elif changed=="revision":options["expected_revision"]=identity()
    elif changed in {"expiry","reboot"}:
        boot,now=consent.authority._clock()
        monkeypatch.setattr(consent.authority,"_clock",lambda:(identity() if changed=="reboot" else boot,now+consent.TTL_MS+1))
    else:
        with s.engine.begin() as db:
            if changed=="guard":db.execute(update(CoreAuthorityGuard).values(revision=CoreAuthorityGuard.revision+1))
            elif changed=="configuration":
                installation=db.execute(select(Installation.configuration)).scalar_one()
                db.execute(update(Installation).values(configuration={**installation,"TARGET_DEVICE_ID":"dev_"+"f"*32}))
            elif changed=="actor":db.execute(update(UserSession).where(UserSession.id==1).values(is_active=False))
            else:db.execute(ApplicationPermissionGrant.__table__.insert().values(application_installation_id=1,user_id=1,permission_id="unrelated",granted_by=1))
    with pytest.raises(AuthorityManagementError):allow(s,reviewed,**options)
    with Session(s.engine) as db:
        assert db.get(Grant,1) is None and db.scalar(select(Native.review_id)) is None


@pytest.mark.parametrize("options",[{"scopes":["command:not_declared"]},{"scopes":["command:pulse","command:pulse"]},{"user_permissions":["not_declared"]},{"accept_native_code":False}])
def test_unchecked_native_trust_or_unknown_duplicate_selection_is_denied(state,options):
    s=state
    with pytest.raises((AuthorityManagementError,ValueError)):allow(s,preview(s),**options)
    with Session(s.engine) as db:assert db.get(Grant,1) is None and db.scalar(select(Native.review_id)) is None


def test_allow_retry_is_historical_and_new_request_cannot_reuse_applied_preview(state):
    s=state
    reviewed=preview(s);request_id=identity()
    saved=allow(s,reviewed,request_id=request_id)
    replay=allow(s,reviewed,request_id=request_id)
    assert replay["saved"] and replay["historical"] and replay["replayed"]
    assert replay["grant_revision"]==saved["grant_revision"]
    with pytest.raises(AuthorityManagementError):allow(s,reviewed)
    with Session(s.engine) as db:assert db.get(Grant,1).revision==1


def test_compiled_ui_and_current_administrator_permissions_are_exact_and_other_users_unchanged(ui_app):
    s=ui_app
    with s.engine.begin() as db:
        db.execute(ApplicationPermissionGrant.__table__.insert().values(application_installation_id=1,user_id=2,permission_id="records_manage",granted_by=1))
    reviewed=preview(s)
    assert reviewed["built_ui_sha256"]==s.build.built_ui_sha256
    assert reviewed["user_permissions"]==[{"permission_id":"records_manage","name":"Manage records"}]
    assert reviewed["selected_user_permissions"]==["records_manage"]
    result=allow(s,reviewed)
    assert result["saved"] and not result["effective"]  # Existing fixture is stopped.
    grant=read(s,"grant",Grant,1);native=read(s,"native",Native,grant["data"]["native_review_id"])
    assert native["data"]["accepts_same_origin_ui_risk"] is True
    assert native["data"]["built_ui_sha256"]==s.build.built_ui_sha256
    with Session(s.engine) as db:
        assert set(db.execute(select(ApplicationPermissionGrant.user_id,ApplicationPermissionGrant.permission_id)))=={(1,"records_manage"),(2,"records_manage")}
    allow(s,preview(s),user_permissions=[])
    fresh=preview(s)
    assert fresh["access_saved"] and fresh["selected_user_permissions"]==[]
    with Session(s.engine) as db:assert set(db.scalars(select(ApplicationPermissionGrant.user_id)))=={2}


def test_http_contract_requires_current_admin_and_strict_bounded_payload(state):
    s=state
    app=FastAPI();app.include_router(router)
    def database():
        with Session(s.engine) as db:yield db
    app.dependency_overrides[get_db]=database
    base="/api/v1/application-extensions/"+s.validated.manifest.module_id+"/authority/consent"
    with TestClient(app) as client:
        assert client.post(base+"/preview",json={"request_id":identity()}).status_code==401
        assert client.post(base+"/preview",headers={"Authorization":"Bearer "+s.user_token},json={"request_id":identity()}).status_code==403
        headers={"Authorization":"Bearer "+s.token}
        assert client.post(base+"/preview",headers=headers,json={"request_id":identity(),"native_code_review_completed":True}).status_code==422
        response=client.post(base+"/preview",headers=headers,json={"request_id":identity()})
        assert response.status_code==200,response.text
        assert response.headers["cache-control"]=="no-store"
        reviewed=response.json()
        request={"request_id":identity(),"preview_id":reviewed["preview_id"],"expected_revision":reviewed["revision"],
            "fingerprint":reviewed["fingerprint"],"scopes":[],"user_permissions":[],"accept_native_code":True}
        assert client.post(base+"/allow",headers=headers,json={**request,"user_id":2}).status_code==422
        result=client.post(base+"/allow",headers=headers,json=request)
        assert result.status_code==200,result.text
        assert result.json()["saved"] and result.json()["consent_version"]==1


def test_nonadministrator_cannot_create_missing_infrastructure_key(state):
    s=state
    (s.key_directory/KEY_NAME).unlink()
    with pytest.raises(AuthorityManagementError) as denied:
        consent.preview(s.manager,1,actor_token=s.user_token,request_id=identity())
    assert denied.value.reason=="actor_unavailable"
    assert not (s.key_directory/KEY_NAME).exists()
    with Session(s.engine) as db:
        assert db.get(Grant,1) is None and db.scalar(select(Plan.plan_id)) is None


def test_preview_cannot_be_approved_by_a_different_current_administrator(state):
    s=state
    reviewed=preview(s)
    with s.engine.begin() as db:db.execute(update(User).where(User.id==2).values(role="admin"))
    with pytest.raises(AuthorityManagementError):
        consent.allow(s.manager,1,actor_token=s.user_token,request_id=identity(),
            preview_id=reviewed["preview_id"],expected_revision=reviewed["revision"],
            fingerprint=reviewed["fingerprint"],scopes=[],user_permissions=[],accept_native_code=True)
    with Session(s.engine) as db:assert db.get(Grant,1) is None and db.scalar(select(Native.review_id)) is None


def test_changed_compiled_build_cannot_inherit_preview_consent(ui_app):
    s=ui_app
    reviewed=preview(s)
    (s.build.path/"assets/operations.mjs").write_text("changed after preview")
    with pytest.raises(AuthorityManagementError):allow(s,reviewed)
    with Session(s.engine) as db:assert db.get(Grant,1) is None and db.scalar(select(Native.review_id)) is None


def test_revoked_consent_is_not_reported_as_saved_and_preview_audit_has_no_raw_resources(state):
    s=state
    saved=allow(s,preview(s),scopes=[])
    s.manager.revoke(1,actor_token=s.token,request_id=identity(),expected_revision=saved["grant_record_revision"])
    fresh=preview(s)
    assert fresh["access_saved"] is False and fresh["selected_scopes"]==fresh["scopes"]
    with Session(s.engine) as db:
        for event in db.scalars(select(AuditLog).where(AuditLog.action=="APPLICATION_AUTHORITY_CONSENT_PREVIEW")):
            assert "resources" not in event.changes


@pytest.mark.parametrize("selected,allowed",[([READ],False),([READ,WRITE],True),([],True)])
def test_optional_relational_consent_preserves_whole_profile_resource_guard(db_app,selected,allowed):
    s=db_app
    Base.metadata.create_all(s.engine)
    reviewed=preview(s)
    assert READ in reviewed["scopes"] and WRITE in reviewed["scopes"]
    if allowed:
        assert allow(s,reviewed,scopes=selected)["saved"] is True
        assert read(s,"grant",Grant,1)["data"]["selection"]["scopes"]==selected
    else:
        with pytest.raises(AuthorityManagementError) as denied:allow(s,reviewed,scopes=selected)
        assert denied.value.reason=="selection_not_allowed"
        with Session(s.engine) as db:
            assert db.get(Grant,1) is None and db.scalar(select(Native.review_id)) is None
        assert read(s,"plan",Plan,reviewed["preview_id"])["state"]=="consent_preview"
