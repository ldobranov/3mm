"""Explicit local Linux authority reset. Never a remotely replayable command.

Stop the Agent first. Preserve identity, modules and execution journals; retain
old authority-bound evidence privately instead of delivering it to another Core.
An interrupted reset blocks enrollment/publishing until local recovery.
"""

import argparse
import json
import os
import subprocess
from pathlib import Path
from uuid import uuid4
from three_mm_protocol.device_authority import sync_directory

AUTHORITY_FILES = (
    "core-credential.json",
    "core-binding.json",
    "hub-enrollment.json",
    "device-authority.json",
    "outbox.json",
    "reconciliation-state.json",
)


def reset_authority(data_dir, confirmed_device_id, *, agent_stopped, ota_trust=None):
    if not agent_stopped:
        raise ValueError("Stop the Agent before authority recovery")
    root = Path(data_dir).absolute()
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Invalid recovery directory")
    root = root.resolve(strict=True)
    identity_path = root / "identity.json"
    if identity_path.is_symlink():
        raise ValueError("Identity cannot be a symbolic link")
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    if (
        identity.get("device_id") != confirmed_device_id
        or not confirmed_device_id.startswith("dev_")
        or len(confirmed_device_id) != 36
    ):
        raise ValueError("Explicit stable device ID confirmation is required")
    targets = [root / name for name in AUTHORITY_FILES]
    trust = Path(ota_trust) if ota_trust is not None else None
    if trust is not None:
        if trust.name != "node-update-trust.json" or trust.parent.is_symlink():
            raise ValueError("Invalid OTA trust target")
        targets.append(trust)
    if any(
        path.is_symlink() or (path.exists() and not path.is_file()) for path in targets
    ):
        raise ValueError("Recovery targets must be regular files")
    recovery_root = root / "authority-recovery"
    if recovery_root.is_symlink() or (
        recovery_root.exists() and not recovery_root.is_dir()
    ):
        raise ValueError("Invalid quarantine directory")
    marker = root / "authority-reset.json"
    # Mark BEFORE moving anything. A partial failure must not bootstrap trust.
    descriptor = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        json.dump(
            {
                "device_id": confirmed_device_id,
                "lifecycle": "recovery",
                "kind": "authority",
            },
            output,
        )
        output.flush()
        os.fsync(output.fileno())
    sync_directory(root)
    recovery_root.mkdir(mode=0o700, exist_ok=True)
    quarantine = recovery_root / uuid4().hex
    quarantine.mkdir(mode=0o700)
    for target in targets:
        if target.exists():
            os.replace(target, quarantine / target.name)
            os.chmod(quarantine / target.name, 0o600)
    sync_directory(quarantine)
    sync_directory(recovery_root)
    sync_directory(root)
    # Receipt records the reset policy; identity and all physical journals stay.
    os.replace(marker, quarantine / "reset-receipt.json")
    sync_directory(quarantine)
    sync_directory(root)
    return quarantine


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("/var/lib/3mm/agent"))
    parser.add_argument("--confirm-device-id", required=True)
    args = parser.parse_args()
    if os.name != "posix" or os.geteuid() != 0:
        raise SystemExit("Local root authorization is required")
    status = subprocess.run(
        ["/usr/bin/systemctl", "is-active", "3mm-agent.service"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    if status.returncode not in {3} or status.stdout.strip() not in {
        "inactive",
        "failed",
    }:
        raise SystemExit("Stop 3mm-agent.service first; unknown status is not safe")
    quarantine = reset_authority(
        args.data_dir,
        args.confirm_device_id,
        agent_stopped=True,
        ota_trust=Path("/etc/3mm/node-update-trust.json"),
    )
    # The daemon/enrollment runs unprivileged after local root recovery.
    owner = (args.data_dir / "identity.json").stat()
    os.chown(quarantine.parent, owner.st_uid, owner.st_gid)
    os.chown(quarantine, owner.st_uid, owner.st_gid)
    for path in quarantine.iterdir():
        os.chown(path, owner.st_uid, owner.st_gid)
    print("Authority reset complete; stable identity and execution evidence preserved.")
    print(
        "Select the intended installation through setup, then explicitly approve enrollment."
    )


if __name__ == "__main__":
    main()
