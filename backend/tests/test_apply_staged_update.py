import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from backend.services.update_staging import StagedUpdate
from deployment import apply_staged_update as worker
from deployment.deployment_contract import CONTRACT_PATH, LEGACY_REQUIRED_FILES
from backend.tests.test_update_staging import write_release_archive


def staged_update(
    tmp_path: Path, *, installer: bytes = b"#!/bin/bash\nexit 0\n", contract=None
) -> StagedUpdate:
    stage_root = tmp_path / "stage"
    stage_root.mkdir(exist_ok=True)
    archive = stage_root / "staged-release.tar.gz"
    entries = {"deployment/install-systemd.sh": installer}
    if contract is not None:
        entries[CONTRACT_PATH] = json.dumps(contract).encode()
        entries["deployment/systemd/new-target.service"] = (
            b"[Service]\nUser=new-target\n"
        )
    write_release_archive(archive, extra_entries=entries)
    data = archive.read_bytes()
    return StagedUpdate(
        release_id="v1.2.0",
        version="1.2.0",
        commit="b" * 40,
        architecture="aarch64",
        artifact_filename="3mm-1.2.0-aarch64.tar.gz",
        artifact_sha256=hashlib.sha256(data).hexdigest(),
        artifact_size_bytes=len(data),
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
    monkeypatch.setattr(
        worker,
        "_service_ids",
        lambda *_names: (getattr(os, "getuid", lambda: 0)(), 1000),
    )
    return statuses, audits


@pytest.mark.parametrize(
    "frontend_origin", ["http://localhost", "http://192.168.1.88:8080"]
)
def test_worker_installs_only_missing_allowlisted_dependencies_then_uses_installer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, frontend_origin: str
) -> None:
    staged = staged_update(tmp_path).model_copy(
        update={"frontend_origin": frontend_origin}
    )
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
        runner=FakeRunner(),
        dependency_inspector=lambda _packages: next(inspections),
    )

    assert result == 0
    assert statuses[0].state == "applying"
    assert statuses[-1].state == "succeeded"
    assert commands[0][:2] == ("/usr/bin/bash", "-n")
    assert commands[1] == ("/usr/bin/apt-get", "update")
    assert commands[2][-2:] == ("--", "python3")
    assert commands[3][0] == "/usr/bin/bash"
    assert "current" not in commands[3][1]
    assert commands[3][1] == commands[0][2]
    assert Path(commands[3][1]).parent == Path(commands[3][2]).parent
    assert commands[3][2] != str(tmp_path / "stage" / "staged-release.tar.gz")
    assert commands[3][3:] == (
        "v1.2.0",
        frontend_origin,
        "",
        staged.artifact_sha256,
    )
    assert not Path(commands[3][1]).exists()  # Root-private workspace cleaned.
    assert (tmp_path / "stage" / "staged-release.tar.gz").exists()
    assert audits[-1]["result"] == "succeeded"
    assert audits[-1]["installer_source"] == "verified_target_artifact"


def test_worker_records_failure_after_installer_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staged = staged_update(tmp_path)
    statuses, audits = prepare_worker(monkeypatch, staged)

    class FakeRunner:
        def run(self, arguments, *, environment=None) -> int:
            return 17 if arguments[0] == "/usr/bin/bash" and arguments[1] != "-n" else 0

    result = worker.apply_staged_update(
        stage_root=tmp_path / "stage",
        state_root=tmp_path / "state",
        allowlist=tmp_path / "allowlist.json",
        release_id=staged.release_id,
        approval_nonce=staged.approval_nonce,
        requested_by_user_id=7,
        runner=FakeRunner(),
        dependency_inspector=lambda packages: {name: True for name in packages},
    )

    assert result == 1
    assert statuses[-1].state == "failed"
    assert statuses[-1].error_code == "installer_failed"
    assert "code 17" in statuses[-1].message
    assert "3mm-update-apply.service" in statuses[-1].message
    assert audits[-1]["result"] == "failed"


def target_contract():
    return {
        "schema_version": 2,
        "profile": "full",
        "installer": "deployment/install-systemd.sh",
        "installer_api": "immutable-full-v1",
        "required_files": sorted(
            LEGACY_REQUIRED_FILES | {"deployment/systemd/new-target.service"}
        ),
    }


@pytest.mark.skipif(
    os.name != "posix", reason="Real bash transport, isolated fake deployment only"
)
@pytest.mark.parametrize("fail_health", [False, True])
def test_old_worker_runs_target_installer_with_new_user_unit_and_rollback(
    tmp_path,
    monkeypatch,
    fail_health,
):
    # The installed worker has no knowledge of new-target.service or its user.
    # Only the target script supplies the new primitive. All mutations stay in
    # this test directory; never invoke live systemd or touch /opt or /etc.
    installed = tmp_path / "installed"
    installed.mkdir()
    (installed / "current").write_text("old")
    (installed / "database").write_text("old-data")
    script = f"""#!/bin/bash
set -Eeuo pipefail
root='{installed.as_posix()}'
restore() {{ printf old > "$root/current"; printf old-data > "$root/database"; rm -f "$root/new-target.service"; }}
trap restore ERR
tar -xOf "$1" deployment/systemd/new-target.service > "$root/new-target.service"
grep -q User=new-target "$root/new-target.service"
printf new > "$root/current"
printf migrated > "$root/database"
{'false' if fail_health else ':'}
""".encode()
    staged = staged_update(tmp_path, installer=script, contract=target_contract())
    statuses, audits = prepare_worker(monkeypatch, staged)

    class LocalRunner:
        def run(self, arguments, *, environment=None):
            if arguments[0] != "/usr/bin/bash":
                assert tuple(arguments) == (
                    "/usr/bin/systemctl",
                    "try-restart",
                    "3mm-update-helper.service",
                )
                return 0
            return subprocess.run(arguments, check=False, env=environment).returncode

    result = worker.apply_staged_update(
        stage_root=tmp_path / "stage",
        state_root=tmp_path / "state",
        allowlist=tmp_path / "allowlist.json",
        release_id=staged.release_id,
        approval_nonce=staged.approval_nonce,
        requested_by_user_id=7,
        runner=LocalRunner(),
        dependency_inspector=lambda packages: {name: True for name in packages},
    )
    assert result == int(fail_health)
    assert (installed / "current").read_text() == ("old" if fail_health else "new")
    assert (installed / "database").read_text() == (
        "old-data" if fail_health else "migrated"
    )
    assert (installed / "new-target.service").exists() is not fail_health
    assert statuses[-1].state == ("failed" if fail_health else "succeeded")
    if not fail_health:
        assert audits[-1]["deployment_contract_version"] == 2


@pytest.mark.parametrize("problem", ["tampered", "unsupported_contract", "syntax"])
def test_target_preflight_fails_before_dependencies_or_activation(
    tmp_path, monkeypatch, problem
):
    contract = target_contract()
    if problem == "unsupported_contract":
        contract["schema_version"] = 99
    staged = staged_update(tmp_path, contract=contract)
    statuses, _audits = prepare_worker(monkeypatch, staged)
    if problem == "tampered":
        (tmp_path / "stage" / "staged-release.tar.gz").write_bytes(
            b"modified after validation"
        )
    commands = []

    class FakeRunner:
        def run(self, arguments, *, environment=None):
            commands.append(tuple(arguments))
            return 2

    def forbidden(_packages):
        pytest.fail("Dependency mutations/inspection must not precede target preflight")

    result = worker.apply_staged_update(
        stage_root=tmp_path / "stage",
        state_root=tmp_path / "state",
        allowlist=tmp_path / "allowlist.json",
        release_id=staged.release_id,
        approval_nonce=staged.approval_nonce,
        requested_by_user_id=7,
        runner=FakeRunner(),
        dependency_inspector=forbidden,
    )
    assert result == 1
    assert statuses[-1].error_code == "target_preflight_failed"
    assert commands == [] or (len(commands) == 1 and commands[0][1] == "-n")


def test_snapshot_is_not_changed_by_a_later_stage_rewrite(tmp_path, monkeypatch):
    staged = staged_update(tmp_path)
    statuses, _audits = prepare_worker(monkeypatch, staged)
    archive = tmp_path / "stage" / "staged-release.tar.gz"

    class FakeRunner:
        def run(self, arguments, *, environment=None):
            if arguments[1] == "-n":
                archive.write_bytes(b"replacement after snapshot")
            elif arguments[0] == "/usr/bin/bash":
                assert (
                    hashlib.sha256(Path(arguments[2]).read_bytes()).hexdigest()
                    == staged.artifact_sha256
                )
                assert Path(arguments[1]).read_bytes() == b"#!/bin/bash\nexit 0\n"
            return 0

    assert (
        worker.apply_staged_update(
            stage_root=tmp_path / "stage",
            state_root=tmp_path / "state",
            allowlist=tmp_path / "allowlist.json",
            release_id=staged.release_id,
            approval_nonce=staged.approval_nonce,
            requested_by_user_id=7,
            runner=FakeRunner(),
            dependency_inspector=lambda packages: {name: True for name in packages},
        )
        == 0
    )
    assert statuses[-1].state == "succeeded"
