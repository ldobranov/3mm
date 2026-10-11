"""Guarded backup-key rotation (M15)."""

import os

import pytest

from deployment import backup_key_rotation

from deployment.backup_key_rotation import (
    BackupKeyRotationError,
    exclusive_mutation_lock,
    plan_rotation,
    rotate_key,
)


def test_rotation_blocked_when_archives_exist(tmp_path):
    backup_root = tmp_path / "backups"
    backup_root.mkdir()
    (backup_root / "bkp_20260101T000000Z_aaaaaaaa.3mmbak").write_bytes(b"x")
    plan = plan_rotation(
        backup_root, tmp_path / "backup.key", acknowledge_orphaned_archives=False
    )
    assert plan.can_rotate is False
    assert plan.archive_count == 1
    with pytest.raises(BackupKeyRotationError):
        rotate_key(
            backup_root, tmp_path / "backup.key", acknowledge_orphaned_archives=False
        )


def test_rotation_allowed_with_acknowledgement(tmp_path):
    backup_root = tmp_path / "backups"
    backup_root.mkdir()
    (backup_root / "bkp_20260101T000000Z_aaaaaaaa.3mmbak").write_bytes(b"x")
    key_file = tmp_path / "backup.key"
    plan = rotate_key(backup_root, key_file, acknowledge_orphaned_archives=True)
    assert plan.can_rotate is True
    assert key_file.is_file()
    assert len(key_file.read_bytes()) == 32
    if os.name == "posix":
        assert key_file.stat().st_mode & 0o077 == 0


def test_rotation_allowed_when_no_archives(tmp_path):
    backup_root = tmp_path / "backups"
    backup_root.mkdir()
    key_file = tmp_path / "backup.key"
    plan = rotate_key(backup_root, key_file, acknowledge_orphaned_archives=False)
    assert plan.archive_count == 0
    assert key_file.is_file()


def test_rotation_replaces_existing_key(tmp_path):
    backup_root = tmp_path / "backups"
    backup_root.mkdir()
    key_file = tmp_path / "backup.key"
    key_file.write_bytes(b"a" * 32)
    rotate_key(backup_root, key_file, acknowledge_orphaned_archives=False)
    assert key_file.read_bytes() != b"a" * 32


def test_symlinked_backup_root_is_rejected(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(BackupKeyRotationError, match="regular directory"):
        plan_rotation(link, tmp_path / "backup.key", acknowledge_orphaned_archives=True)


def test_shared_mutation_lock_serializes_rotation(tmp_path):
    lock_file = tmp_path / "mutation.lock"
    with exclusive_mutation_lock(lock_file):
        # A concurrent backup/restore/update holds the same lock; rotation must
        # refuse rather than race the key change.
        with pytest.raises(BackupKeyRotationError, match="already running"):
            with exclusive_mutation_lock(lock_file):
                pass
    # After release the lock is available again.
    with exclusive_mutation_lock(lock_file):
        pass


def test_cli_busy_mutation_lock_preserves_key(tmp_path, monkeypatch):
    pytest.importorskip("fcntl")
    key = tmp_path / "backup.key"
    key.write_bytes(b"a" * 32)
    lock = tmp_path / "mutation.lock"
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        "sys.argv",
        [
            "backup_key_rotation",
            "--apply",
            "--key-file",
            str(key),
            "--backup-root",
            str(tmp_path / "backups"),
            "--lock-file",
            str(lock),
        ],
    )
    with exclusive_mutation_lock(lock):
        assert backup_key_rotation.main() == 1
    assert key.read_bytes() == b"a" * 32
    assert not key.with_name("backup.key.new").exists()


def test_cli_holds_shared_lock_during_rotation(tmp_path, monkeypatch):
    pytest.importorskip("fcntl")
    lock = tmp_path / "mutation.lock"
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        "sys.argv",
        [
            "backup_key_rotation",
            "--apply",
            "--key-file",
            str(tmp_path / "backup.key"),
            "--backup-root",
            str(tmp_path / "backups"),
            "--lock-file",
            str(lock),
        ],
    )
    original = backup_key_rotation.rotate_key

    def verify_lock(*args, **kwargs):
        with pytest.raises(BackupKeyRotationError, match="already running"):
            with exclusive_mutation_lock(lock):
                pass
        return original(*args, **kwargs)

    monkeypatch.setattr(backup_key_rotation, "rotate_key", verify_lock)
    assert backup_key_rotation.main() == 0
    assert len((tmp_path / "backup.key").read_bytes()) == 32
