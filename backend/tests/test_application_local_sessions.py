"""Real installed source -> registry -> M20 grants -> generic local runtime.

No installed service mutation. Actual OS isolation has its separate opt-in test.
"""

import hashlib
import io
import json
import threading
import time
import zipfile
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from backend.db.device import Device, DeviceCapabilityHealth, DeviceCapabilityProvider
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.db.module import (
    ModulePackage,
)
from backend.services import application_local_sessions as local
from backend.services.application_authority_management import AuthorityManagementError
from backend.services.device_capability_registry import (
    capability_catalog,
    registered_capabilities,
)
from backend.services.module_packages import validate_module_package
from backend.tests.test_application_session_authority import (
    SCOPE,
    checkpoint_app,
    decide,
    identity,
    managed_installed,
    native,
    review,
    session_app,
    source_installed,
    source_subject,
)
from three_mm_protocol.device_capabilities import CapabilityProviderReportV1
from three_mm_runtime.tests.test_session_worker import wheel


@pytest.fixture
def local_app(session_app, monkeypatch):
    s = session_app
    definition = s.validated.application_extension.model_dump(mode="json")
    manifest = s.validated.manifest.model_dump(mode="json")
    module_id = manifest["module_id"]
    binding = definition["session_bindings"][0]
    binding["provider_id"] = module_id
    definition["session_providers"] = [
        {
            "capability_id": binding["capability_id"],
            "factory": "worker_fixture:create_provider",
            "resource_profile": "isolated_session_v1",
            "contract": {
                "contract_version": 1,
                "access_modes": ["write"],
                "control_actions": ["resize"],
            },
        }
    ]
    manifest["capabilities"]["provides"] = [binding["capability_id"]]
    payload = wheel()
    definition["service"]["artifact_sha256"] = hashlib.sha256(payload).hexdigest()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("application-extension.json", json.dumps(definition))
        archive.writestr(definition["service"]["artifact"], payload)
    s.validated = validate_module_package(stream.getvalue())
    s.archive = s.root / "modules" / (s.validated.sha256 + ".zip")
    s.archive.write_bytes(stream.getvalue())
    with s.engine.begin() as db:
        db.execute(delete(DeviceCapabilityHealth))
        db.execute(delete(DeviceCapabilityProvider))
        db.execute(
            update(ModulePackage)
            .where(ModulePackage.id == 1)
            .values(
                sha256=s.validated.sha256,
                size_bytes=len(stream.getvalue()),
                manifest=manifest,
            )
        )
        db.execute(
            update(Installation)
            .where(Installation.id == 1)
            .values(enabled=False, status="disabled")
        )
    monkeypatch.setenv("THREE_MM_LOCAL_SESSIONS", "1")
    monkeypatch.setattr(local, "local_device_id", lambda: s.request.device_id)
    monkeypatch.setattr(local, "supervisor_available", lambda: True)
    monkeypatch.setattr(
        local,
        "get_settings",
        lambda: SimpleNamespace(backend=SimpleNamespace(uploads_dir=s.root)),
    )
    s.request = s.request.model_copy(update={"provider_id": module_id})
    s.manager._prepare(1)  # Fresh ZIP validation populates declarations, not rights.
    return s


def test_local_self_provider_needs_real_native_service_and_human_grants(local_app):
    s = local_app
    with Session(s.engine) as db:
        device = db.scalar(
            select(Device).where(Device.device_id == s.request.device_id)
        )
        registered = registered_capabilities(db, device)
        assert registered[0]["provider_type"] == "core_application"
        assert not capability_catalog(db, device)[0].available
    proof = native(s)
    decide(s, decide(s, review(s, proof), "approve"), "apply")
    with s.engine.begin() as db:
        db.execute(
            update(Installation)
            .where(Installation.id == 1)
            .values(enabled=True, status="active", authority_epoch=identity())
        )
    decide(s, decide(s, review(s, proof), "approve"), "apply")
    status = s.manager.inspect(1)
    assert status["grant_effective"] is True and "runtime_blockers" not in status
    binding, resource = s.session_authority._resolve(
        1, "console", "ses_" + "c" * 32, "Bearer " + s.user_token, s.request
    )
    value = resource.model_dump(mode="json")
    runtime = local.runtime_for_resource(s.engine, value)
    assert runtime is not None and runtime.provider.session_id is None
    assert runtime.provider_id == s.validated.manifest.module_id
    assert (
        local.runtime_for_resource(
            s.engine, {**value, "target_device_id": "dev_" + "f" * 32}
        )
        is None
    )
    assert (
        local.runtime_for_resource(
            s.engine,
            {**value, "owner": {**value["owner"], "module_id": "org.other.app"}},
        )
        is None
    )
    assert (
        local.runtime_for_resource(
            s.engine, {**value, "package_artifact_sha256": "f" * 64}
        )
        is None
    )
    s.manager.revoke(
        1,
        actor_token=s.token,
        request_id=identity(),
        expected_revision=status["grant_record_revision"],
    )
    with pytest.raises(ValueError):
        s.session_authority.check(
            binding,
            authorization="Bearer " + s.user_token,
            request=s.request,
            session_id=binding.session_id,
            operation="status",
        )


def test_disabled_feature_no_supervisor_or_changed_artifact_never_opens(
    local_app, monkeypatch
):
    s = local_app
    monkeypatch.delenv("THREE_MM_LOCAL_SESSIONS")
    with Session(s.engine) as db:
        assert not local.provider_offers(db, db.get(Device, 1))
    monkeypatch.setenv("THREE_MM_LOCAL_SESSIONS", "1")
    monkeypatch.setattr(local, "supervisor_available", lambda: False)
    s.archive.write_bytes(b"changed")
    with pytest.raises(AuthorityManagementError):
        s.manager._prepare(1)


def test_agent_cannot_register_core_session_provider_type():
    with pytest.raises(ValueError):
        CapabilityProviderReportV1.model_validate(
            {
                "schema_version": 1,
                "device_id": "dev_" + "a" * 32,
                "provider_type": "core_application",
                "provider_id": "org.example.counter",
                "provider_version": "1.0.0",
                "expected_revision": 0,
                "capabilities": [],
            }
        )


def test_short_key_contention_waits_only_before_admission(local_app):
    from backend.services.application_authority_keys import CoreReviewKeyStore

    s = local_app
    identity = s.keys.provision()
    store = CoreReviewKeyStore(s.engine, s.key_directory, lock_wait_seconds=0.25)
    entered = threading.Event()
    errors = []

    def holder():
        try:
            with s.keys.locked():
                entered.set()
                time.sleep(0.05)
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=holder)
    thread.start()
    assert entered.wait(2)
    try:
        assert store.identity() == identity
    finally:
        thread.join(2)
    assert not errors and not thread.is_alive()


def test_production_router_is_only_explicit_opt_in(tmp_path):
    import os
    import subprocess
    import sys

    script = """
from backend.main import app
from fastapi.testclient import TestClient
client=TestClient(app)
base='/api/v1/application-extensions/org.example.console/session-host/terminal'
r=client.get(base,params={'artifact_sha256':'a'*64,'built_ui_sha256':'b'*64})
assert r.status_code in (401,403), (r.status_code,r.text)
assert client.post('/api/v1/interactive-sessions/ticket').status_code == 404
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=30,
        env={
            **os.environ,
            "THREE_MM_LOCAL_SESSIONS": "1",
            "DATABASE_URL": "sqlite:///" + str(tmp_path / "route.db"),
            "UPLOADS_DIR": str(tmp_path / "uploads"),
            "APP_CONFIG_FILE": str(tmp_path / "absent-config.json"),
        },
    )
    assert result.returncode == 0, result.stdout + result.stderr
