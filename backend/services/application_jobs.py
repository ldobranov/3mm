"""Persistent bounded scheduler for application-declared internal jobs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import threading

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import ApplicationRuntimeSettings
from backend.db.module import (
    ApplicationExtensionInstallation,
    ApplicationJobState,
    ModulePackage,
)
from backend.services.application_extensions import (
    ApplicationGatewayError,
    invoke_application,
    load_application_definition,
)


_job_lock = threading.Lock()


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def run_application_jobs(
    db: Session,
    settings: ApplicationRuntimeSettings,
    *,
    now: datetime | None = None,
) -> None:
    current = now or datetime.now(UTC)
    rows = db.execute(
        select(ApplicationExtensionInstallation, ModulePackage)
        .join(ModulePackage, ModulePackage.id == ApplicationExtensionInstallation.module_package_id)
        .where(
            ApplicationExtensionInstallation.enabled.is_(True),
            ApplicationExtensionInstallation.status == "active",
        )
    ).all()
    for installation, package in rows:
        try:
            definition = load_application_definition(package)
        except ApplicationGatewayError:
            continue
        for job in definition.jobs:
            existed = True
            state = db.scalar(
                select(ApplicationJobState).where(
                    ApplicationJobState.application_installation_id == installation.id,
                    ApplicationJobState.job_id == job.job_id,
                )
            )
            if state is None:
                existed = False
                state = ApplicationJobState(
                    application_installation_id=installation.id,
                    job_id=job.job_id,
                    next_run_at=current,
                )
                db.add(state)
                db.commit()
            if _aware(state.next_run_at) > current:
                continue
            if (
                existed
                and job.catch_up == "skip"
                and current - (_aware(state.next_run_at) or current)
                >= timedelta(seconds=job.interval_seconds)
            ):
                state.next_run_at = current + timedelta(seconds=job.interval_seconds)
                state.last_outcome = "skipped"
                db.commit()
                continue
            lease_until = _aware(state.lease_until)
            if lease_until is not None and lease_until > current:
                continue
            scheduled_at = _aware(state.next_run_at) or current
            state.lease_until = current + timedelta(seconds=job.interval_seconds if job.interval_seconds < 300 else 300)
            state.last_started_at = current
            state.last_outcome = "running"
            state.last_error = None
            db.commit()
            try:
                invoke_application(
                    installation,
                    package,
                    settings,
                    job.handler_operation_id,
                    {},
                    {
                        "audience": "internal",
                        "correlation_id": f"job:{installation.instance_id}:{job.job_id}",
                        "idempotency_key": (
                            f"job:{installation.instance_id}:{job.job_id}:"
                            f"{scheduled_at.isoformat()}"
                        ),
                    },
                    required_audience="internal",
                )
            except ApplicationGatewayError as exc:
                state.last_outcome = "failed"
                state.last_error = str(exc)[:500]
                state.next_run_at = current + timedelta(
                    seconds=min(job.interval_seconds, 60)
                )
            else:
                state.last_outcome = "succeeded"
                state.last_error = None
                state.run_count += 1
                state.next_run_at = current + timedelta(seconds=job.interval_seconds)
            state.last_completed_at = datetime.now(UTC)
            state.lease_until = None
            db.commit()


def run_application_jobs_once(settings: ApplicationRuntimeSettings) -> None:
    from backend.database import SessionLocal

    with _job_lock:
        db = SessionLocal()
        try:
            run_application_jobs(db, settings)
        finally:
            db.close()
