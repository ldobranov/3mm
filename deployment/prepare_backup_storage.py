"""Prepare recovery storage before starting sandboxed runtime services."""

from pathlib import Path
import os

from deployment.create_backup import BACKUP_ROOT, KEY_FILE, _load_or_create_key


def prepare_backup_storage(
    backup_root: Path = BACKUP_ROOT,
    key_file: Path = KEY_FILE,
    *,
    owner: tuple[int, int],
) -> None:
    # Keep the existing key: retained local backups still depend on it.
    _load_or_create_key(key_file)
    os.chown(key_file, 0, 0)
    for directory, mode in ((backup_root, 0o750), (backup_root / "exports", 0o730)):
        directory.mkdir(parents=True, exist_ok=True, mode=mode)
        os.chown(directory, *owner)
        os.chmod(directory, mode)


if __name__ == "__main__":
    import grp

    if os.geteuid() != 0:
        raise SystemExit("Recovery storage preparation must run as root")
    prepare_backup_storage(owner=(0, grp.getgrnam("3mm").gr_gid))
