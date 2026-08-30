from datetime import UTC, datetime, timedelta

import backend.database  # noqa: F401
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.config import ApplicationRuntimeSettings
from backend.db.base import Base
from backend.db.module import ApplicationExtensionInstallation, ApplicationJobState, ModulePackage
from backend.services.application_jobs import run_application_jobs
from three_mm_protocol import ApplicationExtensionV1


def job_definition():
    return ApplicationExtensionV1.model_validate({"application_extension_version": 1, "module_id": "org.3mm.job-test", "version": "1.0.0", "service": {"artifact": "service/test.whl", "artifact_sha256": "a" * 64, "entrypoint": "test:create", "health_operation_id": "health"}, "operations": [{"operation_id": "health", "kind": "query", "audiences": ["internal"], "idempotency": "forbidden", "output_schema": {"type": "object", "properties": {"status": {"type": "string", "enum": ["ready"]}}, "required": ["status"], "additionalProperties": False}}, {"operation_id": "sync", "kind": "job", "audiences": ["internal"], "idempotency": "required"}], "jobs": [{"job_id": "sync", "handler_operation_id": "sync", "interval_seconds": 60}], "storage": {"schema_revision": "0001", "migration_entrypoint": "test:migrations"}})


def test_scheduler_persists_single_run_lease_and_next_run(monkeypatch):
    engine = create_engine("sqlite://"); Base.metadata.create_all(engine); db = Session(engine)
    package = ModulePackage(module_id="org.3mm.job-test", version="1.0.0", manifest={}, sha256="c" * 64, size_bytes=1, file_path="unused", registrations=[]); db.add(package); db.flush()
    installation = ApplicationExtensionInstallation(module_id=package.module_id, module_package_id=package.id, instance_id="2" * 24, active_version="1.0.0", status="active", enabled=True, socket_path="unused"); db.add(installation); db.commit()
    calls = []
    monkeypatch.setattr("backend.services.application_jobs.load_application_definition", lambda _package: job_definition())
    monkeypatch.setattr("backend.services.application_jobs.invoke_application", lambda *args, **kwargs: calls.append((args, kwargs)) or {})
    now = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)

    run_application_jobs(db, ApplicationRuntimeSettings(), now=now)
    run_application_jobs(db, ApplicationRuntimeSettings(), now=now + timedelta(seconds=30))
    run_application_jobs(db, ApplicationRuntimeSettings(), now=now + timedelta(seconds=61))

    state = db.scalar(select(ApplicationJobState))
    assert len(calls) == 2
    assert state.run_count == 2
    assert state.last_outcome == "succeeded"
    assert state.lease_until is None
    assert calls[0][0][5]["idempotency_key"].startswith("job:")
    db.close(); engine.dispose()
