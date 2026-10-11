"""Operational alerts (M15): secret-free, bounded, actionable status summary.

A thin read-only projection over the existing diagnostics/backup signals. It
reads no secrets, logs or application data, performs no mutation and does no
network IO beyond the already-bounded diagnostic probes. An operator can check
this to see at a glance whether anything needs attention.

Alerts are advisory: each carries a stable machine code and a human message.
They do not send notifications, page anyone or change state.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from backend.config import AppSettings
from backend.services.backups import (
    BackupOperationStatus,
    read_backup_operation_status,
)
from backend.services.diagnostics import DiagnosticBundle, build_diagnostic_bundle

Severity = Literal["error", "warning"]


class OperationalAlert(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    severity: Severity
    code: str
    message: str


class OperationalAlertSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    generated_at: AwareDatetime
    alert_count: int = Field(ge=0)
    alerts: tuple[OperationalAlert, ...] = ()


def _nearest_existing(path: Path) -> Path:
    candidate = path.resolve()
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    return candidate


def build_operational_alert_summary(
    settings: AppSettings,
    *,
    now: datetime | None = None,
    diagnostics: Callable[..., DiagnosticBundle] = build_diagnostic_bundle,
    disk_usage: Callable[[Path], object] = shutil.disk_usage,
    backup_status: Callable[
        [Path], BackupOperationStatus
    ] = read_backup_operation_status,
) -> OperationalAlertSummary:
    generated_at = now or datetime.now(UTC)
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)
    alerts: list[OperationalAlert] = []

    # Backup operation: a failed or rolled-back run needs operator review.
    try:
        status = backup_status(settings.backups.storage_dir / "status.json")
        if status.state == "failed":
            alerts.append(
                OperationalAlert(
                    severity="error",
                    code="backup.failed",
                    message="The most recent backup operation failed",
                )
            )
        elif status.state == "rolled_back":
            alerts.append(
                OperationalAlert(
                    severity="error",
                    code="backup.rolled_back",
                    message="The most recent backup operation was rolled back",
                )
            )
    except ValueError:
        alerts.append(
            OperationalAlert(
                severity="warning",
                code="backup.status_invalid",
                message="Backup operation status is invalid or unreadable",
            )
        )

    # Storage headroom on the backup storage filesystem.
    try:
        usage = disk_usage(_nearest_existing(settings.backups.storage_dir))
        if usage.free < settings.backups.minimum_free_bytes:
            alerts.append(
                OperationalAlert(
                    severity="warning",
                    code="storage.low_free_space",
                    message="Backup storage is below the configured minimum free threshold",
                )
            )
    except OSError:
        alerts.append(
            OperationalAlert(
                severity="warning",
                code="storage.inspect_failed",
                message="Backup storage free space cannot be inspected",
            )
        )

    # Database and Agent readiness from the existing secret-free probes.
    bundle = diagnostics(settings, now=generated_at)
    for check in bundle.checks:
        if check.status == "ok":
            continue
        alerts.append(
            OperationalAlert(
                severity="error" if check.status == "error" else "warning",
                code=f"check.{check.name}",
                message=check.summary,
            )
        )

    return OperationalAlertSummary(
        generated_at=generated_at,
        alert_count=len(alerts),
        alerts=tuple(alerts),
    )
