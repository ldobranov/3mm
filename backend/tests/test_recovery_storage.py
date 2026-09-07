import errno
import json
import os
import shutil
from pathlib import Path

import pytest

from backend.tests.test_backup_preview import _settings
from deployment.create_backup import create_backup
from deployment.portable_backup import create_portable_export, import_portable_backup
from deployment.prepare_backup_storage import prepare_backup_storage
from deployment.restore_backup import _decrypt_archive_with_key, _validate_and_stage
from three_mm_runtime import update_helper
from three_mm_runtime.update_helper_client import UpdateHelperClient, UpdateHelperError


def test_clean_install_key_survives_repreparation_and_import(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "chown", lambda *_args: None, raising=False)
    source = tmp_path / "source"
    source.mkdir()
    settings = _settings(source)
    source_key = source / "backup.key"

    class Controller:
        def stop(self, _services):
            pass

        def start(self, _services):
            pass

    backup = create_backup(settings, key_file=source_key,
                           requested_by_user_id=1, controller=Controller())
    export = create_portable_export(settings.backups.storage_dir, source_key,
                                    backup.backup_id, "test-recovery-password")
    root = tmp_path / "new-device" / "backups"
    key = tmp_path / "new-device" / "etc" / "backup.key"
    prepare_backup_storage(root, key, owner=(0, 0))
    original = key.read_bytes()
    assert len(original) == 32
    assert original != source_key.read_bytes()
    assert (root / "exports").is_dir()
    prepare_backup_storage(root, key, owner=(0, 0))
    assert key.read_bytes() == original
    if os.name != "nt":
        assert key.stat().st_mode & 0o777 == 0o600
    upload = tmp_path / "upload.3mmrecovery"
    shutil.copyfile(export.path, upload)
    imported = import_portable_backup(upload, root, key, "test-recovery-password",
                                      max_archive_bytes=32 * 1024 * 1024)
    plaintext = tmp_path / "restored.tar"
    staging = tmp_path / "staging"
    staging.mkdir()
    _decrypt_archive_with_key(root / f"{imported}.3mmbak", original, plaintext)
    manifest = _validate_and_stage(plaintext, staging, imported)
    assert manifest.backup_id == backup.backup_id
    assert key.read_bytes() == original
    assert not upload.exists()


@pytest.mark.parametrize("failure, code", [
    (OSError(errno.EROFS, "Read-only file system"), "portable_restore_storage_failed"),
    (ValueError("Invalid recovery file"), "portable_restore_validation_failed"),
])
def test_import_failure_is_logged_and_classified(tmp_path, monkeypatch, caplog, failure, code):
    monkeypatch.setattr(update_helper, "_service_ids", lambda *_: (0, 0))

    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(update_helper, "import_portable_backup", fail)
    response = update_helper._handle_request(
        {"action": "restore_portable_backup", "upload_id": "a" * 32,
         "passphrase": "never-log-this-password", "requested_by_user_id": 1},
        stage_root=tmp_path, state_root=tmp_path, allowlist=tmp_path / "allowlist",
        status_file=tmp_path / "status", backup_root=tmp_path / "backups",
    )
    assert response == {"ok": False, "error": code}
    assert "Portable recovery import or scheduling failed" in caplog.text
    assert "never-log-this-password" not in caplog.text


def test_installer_prepares_storage_before_service_activation():
    installer = (Path(__file__).parents[2] / "deployment/install-systemd.sh").read_text()
    assert installer.index("-m deployment.prepare_backup_storage") < installer.index(
        'install_units "$release_dir"'
    )


@pytest.mark.parametrize("code, message", [
    ("portable_restore_storage_failed", "Recovery storage could not be accessed"),
    ("portable_restore_validation_failed", "Check the export password and file"),
    ("unexpected-private-detail", "helper rejected the request"),
])
def test_client_reports_known_errors_without_exposing_arbitrary_details(monkeypatch, code, message):
    class Socket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def settimeout(self, value):
            pass

        def connect(self, path):
            pass

        def sendall(self, data):
            pass

        def recv(self, size):
            return json.dumps({"ok": False, "error": code}).encode() + b"\n"

    monkeypatch.setattr("three_mm_runtime.update_helper_client.socket.socket", lambda *args: Socket())
    monkeypatch.setattr("three_mm_runtime.update_helper_client.socket.AF_UNIX", 1, raising=False)
    with pytest.raises(UpdateHelperError, match=message):
        UpdateHelperClient(Path("unused")).request_portable_restore("a" * 32, "test-password", 1)
