from datetime import UTC, datetime
from pathlib import Path

import pytest

from backend.services.update_staging import StagedUpdate
from three_mm_protocol import AgentRole
from three_mm_provisioning import (
    FileProvisioningStore,
    NetworkCredentials,
    ProvisioningRequest,
    ProvisioningSnapshot,
)
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


def test_manual_network_setup_accepts_only_a_fixed_admin_request(tmp_path: Path) -> None:
    data_dir = tmp_path / "provisioning"
    FileProvisioningStore(data_dir).save(
        ProvisioningSnapshot.provisioned(
            ProvisioningRequest(
                network=NetworkCredentials("network", "not-persisted"),
                locale="en-GB",
                device_name="device",
                administrator_name="admin",
                role=AgentRole.STANDALONE,
            )
        )
    )
    calls = []

    class FakeBoundary:
        def schedule_network_setup(self, trigger, **values):
            calls.append((trigger, values))

    response = update_helper._handle_request(
        {"action": "start_network_setup", "requested_by_user_id": 7},
        stage_root=tmp_path / "stage",
        state_root=tmp_path / "state",
        allowlist=tmp_path / "allowlist.json",
        status_file=tmp_path / "status.json",
        boundary=FakeBoundary(),
        provisioning_data_dir=data_dir,
    )
    injected = update_helper._handle_request(
        {
            "action": "start_network_setup",
            "requested_by_user_id": 7,
            "command": "nmcli connection delete anything",
        },
        stage_root=tmp_path / "stage",
        state_root=tmp_path / "state",
        allowlist=tmp_path / "allowlist.json",
        status_file=tmp_path / "status.json",
        boundary=FakeBoundary(),
        provisioning_data_dir=data_dir,
    )

    assert response == {"ok": True, "status": "queued"}
    assert calls == [
        (
            "manual",
            {
                "data_dir": data_dir,
                "service_user": "3mm",
                "service_group": "3mm",
            },
        )
    ]
    assert injected == {"ok": False, "error": "invalid_request"}


def test_network_setup_boundary_uses_only_the_fixed_module() -> None:
    calls: list[tuple[str, ...]] = []

    class FakeRunner:
        def run(self, arguments) -> int:
            calls.append(tuple(arguments))
            return 0

    boundary = UpdateMutationBoundary(runner=FakeRunner())
    boundary.schedule_network_setup("automatic")

    command = calls[0]
    assert command[0] == "/usr/bin/systemd-run"
    assert "/bin/sh" not in command
    assert "/bin/bash" not in command
    assert "three_mm_runtime.network_recovery" in command
    assert "--property=ProtectSystem=strict" in command
    assert "--property=ReadWritePaths=/var/lib/3mm/provisioning" in command
    assert "--property=ReadWritePaths=/run/lock" in command
    assert command[-7:] == (
        "/var/lib/3mm/provisioning",
        "--trigger",
        "automatic",
        "--user",
        "3mm",
        "--group",
        "3mm",
    )


def test_system_actions_accept_only_fixed_requests_and_workers(tmp_path: Path) -> None:
    scheduled: list[str] = []

    class FakeBoundary:
        def schedule_system_action(self, action: str) -> None:
            scheduled.append(action)

    common = {
        "stage_root": tmp_path / "stage",
        "state_root": tmp_path / "state",
        "allowlist": tmp_path / "allowlist.json",
        "status_file": tmp_path / "status.json",
        "boundary": FakeBoundary(),
    }
    restarted = update_helper._handle_request(
        {"action": "restart_device", "requested_by_user_id": 7},
        **common,
    )
    reset = update_helper._handle_request(
        {"action": "factory_reset", "requested_by_user_id": 7},
        **common,
    )
    injected = update_helper._handle_request(
        {
            "action": "factory_reset",
            "requested_by_user_id": 7,
            "path": "/var/lib/anything",
        },
        **common,
    )

    assert restarted == {"ok": True, "status": "queued"}
    assert reset == {"ok": True, "status": "queued"}
    assert injected == {"ok": False, "error": "invalid_request"}
    assert scheduled == ["restart_device", "factory_reset"]


def test_system_action_boundary_uses_fixed_commands() -> None:
    calls: list[tuple[str, ...]] = []

    class FakeRunner:
        def run(self, arguments) -> int:
            calls.append(tuple(arguments))
            return 0

    boundary = UpdateMutationBoundary(runner=FakeRunner())
    boundary.schedule_system_action("restart_device")
    boundary.schedule_system_action("factory_reset")

    restart, reset = calls
    assert restart[-2:] == ("/usr/bin/systemctl", "reboot")
    assert "/bin/sh" not in restart and "/bin/bash" not in restart
    assert reset[-1] == "/opt/3mm/current/deployment/factory_reset.py"
    assert "--property=ProtectSystem=strict" in reset
    assert "--property=ReadWritePaths=/var/lib/3mm" in reset
    assert "/bin/sh" not in reset and "/bin/bash" not in reset
