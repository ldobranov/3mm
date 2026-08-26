from datetime import UTC, datetime
from pathlib import Path

import pytest

from backend.services.update_staging import StagedUpdate
from three_mm_runtime import update_helper
from three_mm_runtime.update_helper import UpdateMutationBoundary


def staged_update() -> StagedUpdate:
    return StagedUpdate(
        release_id="v1.2.0",
        version="1.2.0",
        commit="b" * 40,
        architecture="aarch64",
        artifact_filename="3mm-1.2.0-aarch64.tar.gz",
        artifact_sha256="c" * 64,
        artifact_size_bytes=1234,
        dependencies=["python3"],
        frontend_origin="http://192.168.1.88:8080",
        staged_at=datetime.now(UTC),
        approval_expires_at=datetime.now(UTC),
        approval_nonce="d" * 64,
        preflight=[],
    )


def test_helper_rejects_commands_paths_and_packages_from_the_request(
    tmp_path: Path,
) -> None:
    response = update_helper._handle_request(
        {
            "action": "apply",
            "release_id": "v1.2.0",
            "approval_nonce": "d" * 64,
            "requested_by_user_id": 7,
            "command": "apt install anything",
        },
        stage_root=tmp_path / "stage",
        state_root=tmp_path / "state",
        allowlist=tmp_path / "allowlist.json",
        status_file=tmp_path / "status.json",
    )

    assert response == {"ok": False, "error": "invalid_request"}


def test_helper_revalidates_stage_and_schedules_fixed_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staged = staged_update()
    calls: list[dict[str, object]] = []
    statuses = []

    class FakeBoundary:
        def schedule(self, **arguments) -> None:
            calls.append(arguments)

    monkeypatch.setattr(
        update_helper,
        "validate_staged_payload",
        lambda *_args, **_kwargs: staged,
    )
    monkeypatch.setattr(
        update_helper,
        "write_operation_status",
        lambda _path, value, **_kwargs: statuses.append(value),
    )
    monkeypatch.setattr(update_helper, "_service_ids", lambda *_names: (1000, 1000))

    response = update_helper._handle_request(
        {
            "action": "apply",
            "release_id": staged.release_id,
            "approval_nonce": staged.approval_nonce,
            "requested_by_user_id": 7,
        },
        stage_root=tmp_path / "stage",
        state_root=tmp_path / "state",
        allowlist=tmp_path / "allowlist.json",
        status_file=tmp_path / "status.json",
        boundary=FakeBoundary(),
    )

    assert response == {"ok": True, "status": "queued"}
    assert statuses[0].state == "queued"
    assert calls == [
        {
            "stage_root": tmp_path / "stage",
            "state_root": tmp_path / "state",
            "allowlist": tmp_path / "allowlist.json",
            "release_id": staged.release_id,
            "approval_nonce": staged.approval_nonce,
            "requested_by_user_id": 7,
        }
    ]


def test_mutation_boundary_uses_no_shell_and_only_the_fixed_worker() -> None:
    calls: list[tuple[str, ...]] = []

    class FakeRunner:
        def run(self, arguments) -> int:
            calls.append(tuple(arguments))
            return 0

    boundary = UpdateMutationBoundary(runner=FakeRunner())
    boundary.schedule(
        stage_root=Path("/var/lib/3mm/core/update-staging"),
        state_root=Path("/var/lib/3mm/update-helper"),
        allowlist=Path("/opt/3mm/current/deployment/update-dependency-allowlist.json"),
        release_id="v1.2.0",
        approval_nonce="d" * 64,
        requested_by_user_id=7,
    )

    command = calls[0]
    assert command[0] == "/usr/bin/systemd-run"
    assert "/bin/sh" not in command
    assert "/bin/bash" not in command
    assert command.count("/opt/3mm/current/deployment/apply_staged_update.py") == 1
    assert command[-4:] == (
        "--repository",
        "ldobranov/3mm",
        "--manifest-asset",
        "3mm-update-manifest.json",
    )
    assert "apt-get" not in " ".join(command)
