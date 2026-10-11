"""Operational alerts (M15): secret-free, bounded, actionable status."""

from datetime import UTC, datetime

from backend.config import AppSettings, BackupSettings
from backend.services.backups import BackupOperationStatus
from backend.services.diagnostics import DiagnosticBundle, DiagnosticCheck
from backend.services.operational_alerts import (
    OperationalAlertSummary,
    build_operational_alert_summary,
)

PLENTY = 100 * 1024 * 1024


class Disk:
    def __init__(self, free):
        self.total = PLENTY
        self.used = 0
        self.free = free


def settings(tmp_path):
    return AppSettings(
        backups=BackupSettings(storage_dir=tmp_path / "backups"),
    )


def ok_diagnostics():
    return DiagnosticBundle(
        generated_at=datetime.now(UTC),
        application={},
        system={},
        storage={"total_bytes": 0, "used_bytes": 0, "free_bytes": 0},
        operations={},
        checks=(DiagnosticCheck(name="agent", status="ok", summary="ok"),),
        excluded=(),
    )


def warning_diagnostics():
    return DiagnosticBundle(
        generated_at=datetime.now(UTC),
        application={},
        system={},
        storage={"total_bytes": 0, "used_bytes": 0, "free_bytes": 0},
        operations={},
        checks=(
            DiagnosticCheck(
                name="agent",
                status="error",
                summary="Agent health endpoint is unavailable",
            ),
        ),
        excluded=(),
    )


def test_no_alerts_when_everything_is_healthy(tmp_path):
    s = settings(tmp_path)
    summary = build_operational_alert_summary(
        s,
        now=datetime.now(UTC),
        diagnostics=lambda *a, **kw: ok_diagnostics(),
        disk_usage=lambda _p: Disk(free=PLENTY),
        backup_status=lambda _p: BackupOperationStatus(),
    )
    assert isinstance(summary, OperationalAlertSummary)
    assert summary.alert_count == 0
    assert summary.alerts == ()


def test_failed_backup_yields_error_alert(tmp_path):
    s = settings(tmp_path)
    summary = build_operational_alert_summary(
        s,
        now=datetime.now(UTC),
        diagnostics=lambda *a, **kw: ok_diagnostics(),
        disk_usage=lambda _p: Disk(free=PLENTY),
        backup_status=lambda _p: BackupOperationStatus(state="failed"),
    )
    assert summary.alert_count == 1
    assert summary.alerts[0].severity == "error"
    assert summary.alerts[0].code == "backup.failed"


def test_low_free_space_yields_warning(tmp_path):
    s = settings(tmp_path)
    summary = build_operational_alert_summary(
        s,
        now=datetime.now(UTC),
        diagnostics=lambda *a, **kw: ok_diagnostics(),
        disk_usage=lambda _p: Disk(free=1024),
        backup_status=lambda _p: BackupOperationStatus(),
    )
    assert summary.alerts[0].code == "storage.low_free_space"


def test_diagnostic_error_is_promoted_to_alert(tmp_path):
    s = settings(tmp_path)
    summary = build_operational_alert_summary(
        s,
        now=datetime.now(UTC),
        diagnostics=lambda *a, **kw: warning_diagnostics(),
        disk_usage=lambda _p: Disk(free=PLENTY),
        backup_status=lambda _p: BackupOperationStatus(),
    )
    codes = {alert.code for alert in summary.alerts}
    assert "check.agent" in codes


def test_secret_free_output_shape(tmp_path):
    s = settings(tmp_path)
    summary = build_operational_alert_summary(
        s,
        now=datetime.now(UTC),
        diagnostics=lambda *a, **kw: ok_diagnostics(),
        disk_usage=lambda _p: Disk(free=PLENTY),
        backup_status=lambda _p: BackupOperationStatus(),
    )
    dumped = summary.model_dump(mode="json")
    assert set(dumped) == {"generated_at", "alert_count", "alerts"}
    # No secret-bearing keys may exist anywhere in the summary.
    assert "password" not in str(dumped).lower()
    assert "token" not in str(dumped).lower()
