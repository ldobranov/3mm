import json
import base64,hashlib,os,uuid
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
import pytest

import backend.database  # noqa: F401 - register the complete Core model graph
from backend.config import ApplicationRuntimeSettings
from backend.db.base import Base
from backend.db.authority import CoreAuthorityGuard
from backend.db.device import Device
from backend.db.module import (
    ApplicationExtensionInstallation,
    ApplicationPermissionGrant,
    ModulePackage,
)
from backend.db.user import User
from backend.db.session import UserSession
from backend.routes import application_extensions, modules
from backend.routes.application_extensions import router as application_router
from backend.routes.modules import router as module_router
from backend.services import application_extensions as gateway
from backend.services import compiled_ui
from backend.services.compiled_ui import compile_ui_package
from backend.services.module_packages import validate_module_package
from backend.tests.test_module_packages import application_definition, application_package
from backend.utils.db_utils import get_db
from backend.utils.jwt_utils import create_access_token
from three_mm_runtime.application_activation import application_instance_id


class ReadyClient:
    def __init__(self, *_args):
        pass

    def invoke(self, _operation_id, _payload, _context):
        return {}


def fake_compiler(command, **_kwargs):
    output = Path(command[3])
    (output / "assets").mkdir(parents=True)
    entries = {}
    for entrypoint_id in ("registration", "operations"):
        name = f"assets/{entrypoint_id}.mjs"
        (output / name).write_text("export default {}", encoding="utf-8")
        entries[entrypoint_id] = name
    (output / "entrypoints.json").write_text(
        json.dumps({"entries": entries, "styles": []}),
        encoding="utf-8",
    )
    return subprocess.CompletedProcess(command, 0, "", "")


def environment(monkeypatch, tmp_path, blob=None):
    engine = create_engine(
        "sqlite:///"+str(tmp_path/"access.db"),
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    admin = User(username="admin", email="admin@example.com", hashed_password="x", role="admin")
    operator = User(username="operator", email="operator@example.com", hashed_password="x", role="user")
    db.add_all([admin, operator, CoreAuthorityGuard(singleton_id=1)])
    db.commit()

    blob = blob or application_package()
    validated = validate_module_package(blob)
    (tmp_path/"modules").mkdir(exist_ok=True)
    archive = tmp_path / "modules" / f"{validated.sha256}.zip"
    archive.write_bytes(blob)
    package = ModulePackage(
        module_id=validated.manifest.module_id,
        version=validated.manifest.version,
        manifest=validated.manifest.model_dump(mode="json"),
        sha256=validated.sha256,
        size_bytes=len(blob),
        file_path=str(archive),
        registrations=[],
    )
    db.add(package)
    db.commit()
    installation = ApplicationExtensionInstallation(
        module_id=package.module_id,
        module_package_id=package.id,
        instance_id="a" * 24,
        active_version=package.version,
        status="active",
        enabled=True,
        socket_path=str(tmp_path / "service.sock"),
    )
    db.add(installation)
    db.commit()

    key_root = tmp_path / "keys"
    key_root.mkdir()
    (key_root / f"{installation.instance_id}.key").write_bytes(b"s" * 32)
    runtime_settings = ApplicationRuntimeSettings(
        root=tmp_path / "apps",
        key_root=key_root,
        helper_socket=tmp_path / "helper.sock",
    )
    monkeypatch.setattr(
        application_extensions,
        "get_settings",
        lambda: type("Settings", (), {"applications": runtime_settings})(),
    )
    monkeypatch.setattr(gateway, "ApplicationServiceClient", ReadyClient)
    from backend.tests.response_helpers import install_response_transport
    install_response_transport(monkeypatch)

    app = FastAPI()
    app.include_router(application_router)
    app.include_router(module_router)
    from backend.routes.auth_refresh import router as refresh_router
    app.include_router(refresh_router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    admin_session = UserSession(user_id=admin.id, token="pending-admin", is_active=True,
        expires_at=datetime.now(UTC) + timedelta(hours=1))
    operator_session = UserSession(user_id=operator.id, token="pending-operator", is_active=True,
        expires_at=datetime.now(UTC) + timedelta(hours=1))
    db.add_all([admin_session, operator_session]); db.flush()
    admin_token = create_access_token(str(admin.id), {"role": "admin", "sid": admin_session.id, "token_version": admin.token_version})
    operator_token = create_access_token(str(operator.id), {"role": "user", "sid": operator_session.id, "token_version": operator.token_version})
    admin_session.token = admin_token; operator_session.token = operator_token; db.commit()
    if os.name=='posix':
        from backend.db.installation_identity import CoreInstallationIdentity
        from backend.services import application_authority_management as authority
        public=Ed25519PrivateKey.generate().public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
        db.add(CoreInstallationIdentity(singleton_id=1,installation_id='inst_'+'5'*32,identity_version=1,key_generation=1,
            key_id=hashlib.sha256(public).hexdigest(),public_key=base64.b64encode(public).decode(),encrypted_private_key='unused',created_at=datetime.now(UTC)))
        db.commit()
        manager=authority.ApplicationAuthorityManager(engine,uploads_root=tmp_path,core_version='0.3.0',review_key_directory=tmp_path/'review')
        manager.keys.provision()
        monkeypatch.setattr(authority,'configured_manager',lambda _engine:manager)
    return client, db, engine, admin, operator, installation, package, admin_token, operator_token


def kiosk_enrollment(label='Kiosk',**extra):
    return dict(request_id=uuid.uuid4().hex,label=label,**extra)

def kiosk_claim(code,**extra):
    return dict(request_id=uuid.uuid4().hex,recovery_proof=base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip('='),code=code,**extra)


def headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_application_activation_selects_and_persists_a_managed_device(
    monkeypatch, tmp_path
):
    (
        client,
        db,
        engine,
        _admin,
        _operator,
        installation,
        package,
        admin_token,
        _operator_token,
    ) = environment(monkeypatch, tmp_path)
    device_id = "dev_0123456789abcdef0123456789abcdef"
    db.add(
        Device(
            device_id=device_id,
            display_name="Front reader",
            role="node",
            protocol_version="1.0",
            approved_at=datetime.now(UTC),
        )
    )
    db.commit()
    helper_calls = []
    monkeypatch.setattr(
        application_extensions.UpdateHelperClient,
        "activate_application_extension",
        lambda _self, sha256, user_id, configuration, _lifecycle: helper_calls.append(
            (sha256, user_id, configuration)
        )
        or {
            "module_id": package.module_id,
            "version": package.version,
            "instance_id": installation.instance_id,
            "socket_path": installation.socket_path,
        },
    )
    try:
        configuration = client.get(
            f"/api/v1/application-extensions/packages/{package.sha256}/configuration",
            headers=headers(admin_token),
        )
        assert configuration.status_code == 200
        assert configuration.json()["fields"][0]["key"] == "READER_DEVICE_ID"
        assert configuration.json()["devices"][0]["device_id"] == device_id

        activated = client.post(
            f"/api/v1/application-extensions/packages/{package.sha256}/activate",
            json={"configuration": {"READER_DEVICE_ID": device_id}},
            headers=headers(admin_token),
        )
        assert activated.status_code == 200
        db.refresh(installation)
        assert installation.configuration["READER_DEVICE_ID"] == device_id
        assert helper_calls == [
            (package.sha256, 1, installation.configuration)
        ]
    finally:
        db.close()
        engine.dispose()


def test_operator_permission_is_server_enforced_and_revocable(monkeypatch, tmp_path):
    client, db, engine, admin, operator, _installation, _package, admin_token, operator_token = environment(monkeypatch, tmp_path)
    try:
        path = "/api/v1/application-extensions/org.3mm.workflow-reference/operator/operations/approve"
        request = {"payload": {}, "idempotency_key": "request-0001"}
        assert client.post(path, json=request, headers=headers(operator_token)).status_code == 403
        granted = client.post(
            "/api/v1/application-extensions/org.3mm.workflow-reference/permissions/grants",
            json={"user_id": operator.id, "permission_id": "records_manage"},
            headers=headers(admin_token),
        )
        assert granted.status_code == 201
        assert client.post(path, json=request, headers=headers(operator_token)).status_code == 200
        revoked = client.delete(
            f"/api/v1/application-extensions/org.3mm.workflow-reference/permissions/grants/{operator.id}/records_manage",
            headers=headers(admin_token),
        )
        assert revoked.status_code == 200
        assert client.post(path, json=request, headers=headers(operator_token)).status_code == 403
    finally:
        db.close()
        engine.dispose()


@pytest.mark.parametrize('selection,devices,expected',[
    ({},[],200),({'READER_DEVICE_ID':'dev_'+'1'*32},['dev_'+'1'*32],200),
    ({'SECONDARY_DEVICE_ID':'dev_'+'2'*32},[],422),
])
def test_activation_handles_zero_optional_devices_but_checks_every_supplied_binding(monkeypatch,tmp_path,selection,devices,expected):
    from backend.tests.test_application_configuration import optional_readers,reader_schema
    definition=optional_readers().model_dump(mode='json')
    from backend.tests.test_module_packages import application_manifest
    manifest=application_manifest(configuration_schema=reader_schema())
    client,db,engine,_,_,installation,package,token,_=environment(monkeypatch,tmp_path,application_package(definition=definition,manifest_value=manifest))
    calls=[]
    for device in devices:db.add(Device(device_id=device,display_name='Reader',role='node',protocol_version='1.0',approved_at=datetime.now(UTC)))
    db.commit()
    monkeypatch.setattr(application_extensions.UpdateHelperClient,'activate_application_extension',lambda *_args:calls.append(True) or dict(module_id=package.module_id,version=package.version,instance_id=installation.instance_id,socket_path=installation.socket_path))
    try:
        response=client.post(f'/api/v1/application-extensions/packages/{package.sha256}/activate',headers=headers(token),json={'configuration':selection})
        assert response.status_code==expected,response.text
        assert len(calls)==int(expected==200)
        if expected==200:
            db.refresh(installation)
            assert {k:v for k,v in installation.configuration.items() if k.endswith('DEVICE_ID')}==selection
            if selection:
                # Missing configuration is ordinary activation, not a new empty
                # device choice; explicit empty selection clears optional keys.
                for body in ({},None):
                    kept=client.post(f'/api/v1/application-extensions/packages/{package.sha256}/activate',headers=headers(token),json=body)
                    assert kept.status_code==200,kept.text
                    db.refresh(installation);assert installation.configuration['READER_DEVICE_ID']==selection['READER_DEVICE_ID']
                cleared=client.post(f'/api/v1/application-extensions/packages/{package.sha256}/activate',headers=headers(token),json={'configuration':{}})
                assert cleared.status_code==200,cleared.text
                db.refresh(installation);assert 'READER_DEVICE_ID' not in installation.configuration
    finally:db.close();engine.dispose()


def test_optional_device_revoked_after_preflight_cannot_start_runtime(monkeypatch,tmp_path):
    from backend.tests.test_application_configuration import optional_readers,reader_schema
    from backend.tests.test_module_packages import application_manifest
    from sqlalchemy import update
    device='dev_'+'1'*32
    blob=application_package(definition=optional_readers().model_dump(mode='json'),manifest_value=application_manifest(configuration_schema=reader_schema()))
    client,db,engine,_,_,installation,package,token,_=environment(monkeypatch,tmp_path,blob)
    db.add(Device(device_id=device,display_name='Reader',role='node',protocol_version='1.0',approved_at=datetime.now(UTC)));db.commit()
    prepare=application_extensions.prepare_lifecycle_consent
    def revoke_before_lock(*args):
        result=prepare(*args)
        with engine.begin() as connection:connection.execute(update(Device).values(revoked_at=datetime.now(UTC)))
        return result
    monkeypatch.setattr(application_extensions,'prepare_lifecycle_consent',revoke_before_lock)
    calls=[];monkeypatch.setattr(application_extensions.UpdateHelperClient,'activate_application_extension',lambda *_args:calls.append(True))
    try:
        response=client.post(f'/api/v1/application-extensions/packages/{package.sha256}/activate',headers=headers(token),json={'configuration':{'READER_DEVICE_ID':device}})
        assert response.status_code==409,response.text
        assert calls==[]
    finally:db.close();engine.dispose()


def test_kiosk_enrollment_session_and_revocation_are_independent_from_users(monkeypatch, tmp_path):
    client, db, engine, _admin, _operator, _installation, _package, admin_token, _operator_token = environment(monkeypatch, tmp_path)
    try:
        base = "/api/v1/application-extensions/org.3mm.workflow-reference/kiosk"
        created = client.post(
            f"{base}/enrollments",
            json=kiosk_enrollment('Front desk tablet'),
            headers=headers(admin_token),
        )
        assert created.status_code == 201
        claimed = client.post(
            f"{base}/enrollments/claim",
            json=kiosk_claim(created.json()['code']),
        )
        assert claimed.status_code == 200
        identity = claimed.json()
        assert client.post(
            f"{base}/enrollments/claim",
            json=kiosk_claim(created.json()['code']),
        ).status_code == 409
        session = client.post(
            f"{base}/sessions",
            json={
                "terminal_id": identity["terminal_id"],
                "credential": identity["credential"],
            },
        )
        assert session.status_code == 200
        kiosk_token = session.json()["access_token"]
        operation = client.post(
            f"{base}/operations/register",
            json={"payload": {}, "idempotency_key": "kiosk-request-0001"},
            headers=headers(kiosk_token),
        )
        assert operation.status_code == 200
        operator_path = "/api/v1/application-extensions/org.3mm.workflow-reference/operator/operations/approve"
        assert client.post(
            operator_path,
            json={"payload": {}, "idempotency_key": "kiosk-request-0002"},
            headers=headers(kiosk_token),
        ).status_code == 401
        assert client.post("/api/user/refresh", headers=headers(kiosk_token)).status_code == 401
        assert client.delete(
            f"{base}/terminals/{identity['terminal_id']}",
            headers=headers(admin_token),
        ).status_code == 200
        assert client.post(
            f"{base}/operations/register",
            json={"payload": {}, "idempotency_key": "kiosk-request-0003"},
            headers=headers(kiosk_token),
        ).status_code == 401
    finally:
        db.close()
        engine.dispose()


def test_public_gateway_allows_only_explicitly_public_operations(monkeypatch, tmp_path):
    definition = application_definition()
    definition["operations"][1]["audiences"] = ["public", "kiosk"]
    blob = application_package(definition=definition)
    client, db, engine, *_rest = environment(monkeypatch, tmp_path, blob=blob)
    try:
        base = "/api/v1/application-extensions/org.3mm.workflow-reference/public/operations"
        assert client.post(
            f"{base}/register",
            json={"payload": {}, "idempotency_key": "public-request-0001"},
        ).status_code == 200
        assert client.post(
            f"{base}/approve",
            json={"payload": {}, "idempotency_key": "public-request-0002"},
        ).status_code == 409
    finally:
        db.close()
        engine.dispose()


def test_compiled_application_catalog_returns_only_authorized_routes(monkeypatch, tmp_path):
    client, db, engine, _admin, operator, installation, _package, admin_token, operator_token = environment(monkeypatch, tmp_path)
    try:
        monkeypatch.setenv("COMPILED_UI_ARTIFACTS_DIR", str(tmp_path / "compiled"))
        monkeypatch.setattr(compiled_ui.subprocess, "run", fake_compiler)
        package = db.get(ModulePackage, installation.module_package_id)
        validated = validate_module_package(Path(package.file_path).read_bytes())
        compile_ui_package(Path(package.file_path).read_bytes(), validated)

        catalog = "/api/v1/modules/compiled-ui/catalog"
        assert client.get(catalog).json()["items"] == []
        assert client.get(catalog, headers=headers(operator_token)).json()["items"] == []
        db.add(
            ApplicationPermissionGrant(
                application_installation_id=installation.id,
                user_id=operator.id,
                permission_id="records_manage",
            )
        )
        db.commit()
        operator_item = client.get(catalog, headers=headers(operator_token)).json()["items"][0]
        assert [item["entrypoint_id"] for item in operator_item["entrypoints"]] == ["operations"]
        assert operator_item["entrypoints"][0]["application_audience"] == "operator"
        assert client.get(catalog, headers=headers(admin_token)).json()["items"] == []
        db.add(ApplicationPermissionGrant(application_installation_id=installation.id,
            user_id=_admin.id, permission_id="records_manage"))
        db.commit()
        admin_item = client.get(catalog, headers=headers(admin_token)).json()["items"][0]
        assert [item["entrypoint_id"] for item in admin_item["entrypoints"]] == ["operations"]
        enrollment = client.post(
            "/api/v1/application-extensions/org.3mm.workflow-reference/kiosk/enrollments",
            json=kiosk_enrollment('Catalog tablet'),
            headers=headers(admin_token),
        ).json()
        kiosk_token = client.post(
            "/api/v1/application-extensions/org.3mm.workflow-reference/kiosk/enrollments/claim",
            json=kiosk_claim(enrollment['code']),
        ).json()["access_token"]
        kiosk_item = client.get(catalog, headers=headers(kiosk_token)).json()["items"][0]
        assert [item["entrypoint_id"] for item in kiosk_item["entrypoints"]] == ["registration"]
        assert kiosk_item["entrypoints"][0]["application_audience"] == "kiosk"
    finally:
        db.close()
        engine.dispose()


def test_uninstall_removes_core_registration_and_preserves_package(monkeypatch, tmp_path):
    (
        client,
        db,
        engine,
        _admin,
        operator,
        installation,
        package,
        admin_token,
        _operator_token,
    ) = environment(monkeypatch, tmp_path)
    helper_calls = []
    erase_calls = []
    monkeypatch.setattr(
        application_extensions.UpdateHelperClient,
        "uninstall_application_extension",
        lambda _self, instance_id, user_id, _lifecycle: helper_calls.append(
            (instance_id, user_id)
        ),
    )
    monkeypatch.setattr(
        application_extensions.UpdateHelperClient,
        "erase_application_extension_data",
        lambda _self, instance_id, user_id, **_context: erase_calls.append(
            (instance_id, user_id)
        ),
    )
    grant = ApplicationPermissionGrant(
        application_installation_id=installation.id,
        user_id=operator.id,
        permission_id="records_manage",
    )
    db.add(grant)
    db.commit()
    installation_id = installation.id
    package_id = package.id
    grant_id = grant.id
    try:
        response = client.delete(
            f"/api/v1/application-extensions/{package.module_id}",
            headers=headers(admin_token),
        )

        assert response.status_code == 200
        assert response.json()["data_preserved"] is True
        assert helper_calls == [("a" * 24, 1)]
        assert db.get(ApplicationExtensionInstallation, installation_id) is None
        assert db.get(ModulePackage, package_id) is not None
        assert db.get(ApplicationPermissionGrant, grant_id) is None

        erased = client.delete(
            f"/api/v1/application-extensions/{package.module_id}/data",
            headers=headers(admin_token),
        )
        assert erased.status_code == 200
        assert erase_calls == [("a" * 24, 1)]
    finally:
        db.close()
        engine.dispose()



def test_activation_rejects_public_route_conflict_before_runtime_mutation(
    monkeypatch, tmp_path
):
    (
        client,
        db,
        engine,
        _admin,
        _operator,
        installation,
        package,
        admin_token,
        _operator_token,
    ) = environment(monkeypatch, tmp_path)
    helper_calls = []
    monkeypatch.setattr(
        application_extensions,
        "validate_public_http_candidate",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            application_extensions.ApplicationPublicWebError(
                "Public HTTP route conflict", status_code=409
            )
        ),
    )
    monkeypatch.setattr(
        application_extensions.UpdateHelperClient,
        "activate_application_extension",
        lambda *_args, **_kwargs: helper_calls.append(True),
    )
    try:
        before = (
            installation.module_package_id,
            installation.active_version,
            installation.status,
            installation.enabled,
        )
        response = client.post(
            f"/api/v1/application-extensions/packages/{package.sha256}/activate",
            headers=headers(admin_token),
            json={"configuration": {}},
        )
        db.refresh(installation)
        assert response.status_code == 409
        assert response.json()["detail"] == "Public HTTP route conflict"
        assert helper_calls == []
        assert (
            installation.module_package_id,
            installation.active_version,
            installation.status,
            installation.enabled,
        ) == before
    finally:
        db.close()
        engine.dispose()
