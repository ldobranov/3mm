from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from backend.services.update_staging import StagedUpdate
from deployment import apply_staged_update as worker


def staged_update() -> StagedUpdate:
    return StagedUpdate(
        release_id="v1.2.0",
        version="1.2.0",
        commit="b" * 40,
        architecture="aarch64",
        artifact_filename="3mm-1.2.0-aarch64.tar.gz",
        artifact_sha256="c" * 64,
        artifact_size_bytes=1234,
        dependencies=["ca-certificates", "python3"],
        frontend_origin="http://192.168.1.88:8080",
        staged_at=datetime.now(UTC),
        approval_expires_at=datetime.now(UTC) + timedelta(minutes=30),
        approval_nonce="d" * 64,
        preflight=[],
    )


def prepare_worker(
    monkeypatch: pytest.MonkeyPatch,
    staged: StagedUpdate,
) -> tuple[list, list]:
    statuses = []
    audits = []
    monkeypatch.setattr(
        worker,
        "validate_staged_payload",
        lambda *_args, **_kwargs: staged,
    )
    monkeypatch.setattr(
        worker,
        "revalidate_official_release",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        worker,
        "write_operation_status",
        lambda _path, value, **_kwargs: statuses.append(value),
    )
    monkeypatch.setattr(
        worker,
        "_append_audit",
        lambda _path, value, _group_id: audits.append(value),
    )
    monkeypatch.setattr(worker, "_service_ids", lambda *_names: (1000, 1000))
    return statuses, audits


def test_worker_installs_only_missing_allowlisted_dependencies_then_uses_installer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staged = staged_update()
    statuses, audits = prepare_worker(monkeypatch, staged)
    commands: list[tuple[str, ...]] = []
    inspections = iter(
        [
            {"ca-certificates": True, "python3": False},
            {"ca-certificates": True, "python3": True},
        ]
    )

    class FakeRunner:
        def run(self, arguments, *, environment=None) -> int:
            commands.append(tuple(arguments))
            return 0

    result = worker.apply_staged_update(
        stage_root=tmp_path / "stage",
        state_root=tmp_path / "state",
        allowlist=tmp_path / "allowlist.json",
        release_id=staged.release_id,
        approval_nonce=staged.approval_nonce,
        requested_by_user_id=7,
        installer=Path("/trusted/install-systemd.sh"),
        runner=FakeRunner(),
        dependency_inspector=lambda _packages: next(inspections),
    )

    assert result == 0
    assert statuses[0].state == "applying"
    assert statuses[-1].state == "succeeded"
    assert commands[0] == ("/usr/bin/apt-get", "update")
    assert commands[1][-2:] == ("--", "python3")
    assert commands[2] == (
        "/usr/bin/bash",
        str(Path("/trusted/install-systemd.sh")),
        str(tmp_path / "stage" / "staged-release.tar.gz"),
        "v1.2.0",
        "http://192.168.1.88:8080",
        "",
        "c" * 64,
    )
    assert audits[-1]["result"] == "succeeded"


def test_worker_records_failure_after_installer_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staged = staged_update()
    statuses, audits = prepare_worker(monkeypatch, staged)

    class FakeRunner:
        def run(self, arguments, *, environment=None) -> int:
            return 1 if arguments[0] == "/usr/bin/bash" else 0

    result = worker.apply_staged_update(
        stage_root=tmp_path / "stage",
        state_root=tmp_path / "state",
        allowlist=tmp_path / "allowlist.json",
        release_id=staged.release_id,
        approval_nonce=staged.approval_nonce,
        requested_by_user_id=7,
        installer=Path("/trusted/install-systemd.sh"),
        runner=FakeRunner(),
        dependency_inspector=lambda packages: {name: True for name in packages},
    )

    assert result == 1
    assert statuses[-1].state == "failed"
    assert statuses[-1].error_code == "installer_failed"
    assert audits[-1]["result"] == "failed"
