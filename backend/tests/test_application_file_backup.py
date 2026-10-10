"""Real encrypted SDK-file recovery on disposable POSIX data, not live services."""

import hashlib
import io
import os
import shutil
import sqlite3
import stat
import tarfile
from pathlib import Path

import pytest

from backend.services.backups import (
    build_backup_preview,
    read_backup_operation_status,
    validate_application_backup_inventory,
)
from backend.tests.test_backup_preview import _settings
from deployment import restore_application_extensions as reconstruction
from deployment import restore_backup as recovery
from deployment.create_backup import create_backup, encrypt_file
from deployment.portable_backup import create_portable_export, import_portable_backup
from three_mm_application_sdk import ApplicationFileLimits, ApplicationFileStorage
from three_mm_protocol import BackupEntryV1, BackupManifestV1
from three_mm_runtime.application_activation import (
    activate_application_package,
    application_instance_id,
)
from three_mm_runtime.tests.test_application_activation import (
    ReadyClient,
    Supervisor,
    service_package,
)


pytestmark = pytest.mark.skipif(os.name != "posix", reason="Real POSIX SDK storage")
MODULE_ID = "org.3mm.workflow-reference"
INSTANCE = application_instance_id(MODULE_ID)


class Controller:
    """Only OS service effects and migration are doubled; filesystem is real."""

    def __init__(self):
        self.calls = []

    def stop(self, services):
        self.calls.append("stop")

    def start(self, services):
        self.calls.append("start")

    def migrate(self):
        self.calls.append("migrate")

    def activate_and_verify(self):
        self.calls.append("verify")


def _data(settings):
    return settings.backups.application_extensions_dir / INSTANCE / "data"


def _files(settings):
    data = _data(settings)
    data.mkdir(parents=True, exist_ok=True)
    return ApplicationFileStorage(data)


def _backup(settings, root):
    key = root / "keys/backup.key"
    backup = create_backup(
        settings, key_file=key, requested_by_user_id=7, controller=Controller()
    )
    return backup, key


def _restore(settings, root, backup_id, key, controller):
    return recovery.restore_backup(
        settings,
        backup_id=backup_id,
        key_file=key,
        requested_by_user_id=7,
        runtime=controller,
        service_ids=(os.getuid(), os.getgid()),
        state_root=root,
        host_config=settings.backups.host_config_file,
        apply_ownership=False,
    )


@pytest.mark.parametrize("failed_health", [False, True])
def test_local_restore_preserves_sdk_files_and_rolls_back_failed_health(
    tmp_path, failed_health
):
    settings = _settings(tmp_path)
    files = _files(settings)
    old = files.put("logo", b"backup-image", expected_sha256=None)
    files.put("empty", b"", expected_sha256=None)
    (_data(settings) / "legacy.txt").write_bytes(b"legacy-backup")
    backup, key = _backup(settings, tmp_path)
    files.put("logo", b"live-image", expected_sha256=old.sha256)
    files.delete("empty", expected_sha256=hashlib.sha256(b"").hexdigest())
    files.put("new", b"live-only", expected_sha256=None)
    (_data(settings) / "legacy.txt").write_bytes(b"legacy-live")

    class Runtime(Controller):
        def activate_and_verify(self):
            super().activate_and_verify()
            if failed_health and self.calls.count("verify") == 1:
                # Read what actually reached the health boundary before failing.
                recovered = _files(settings).get("logo")
                assert recovered.content == b"backup-image"
                _files(settings).put(
                    "logo", b"failed-runtime-write", expected_sha256=recovered.sha256
                )
                _files(settings).put(
                    "candidate", b"candidate-only", expected_sha256=None
                )
                raise RuntimeError("health failed")

    runtime = Runtime()
    if failed_health:
        with pytest.raises(RuntimeError, match="health failed"):
            _restore(settings, tmp_path, backup.backup_id, key, runtime)
        assert (
            read_backup_operation_status(
                settings.backups.storage_dir / "status.json"
            ).state
            == "rolled_back"
        )
        assert _files(settings).get("logo").content == b"live-image"
        assert _files(settings).list_entries() == [("logo", 10), ("new", 9)]
        assert (_data(settings) / "legacy.txt").read_bytes() == b"legacy-live"
        assert runtime.calls == ["stop", "migrate", "verify", "stop", "verify"]
    else:
        assert (
            _restore(settings, tmp_path, backup.backup_id, key, runtime).state
            == "completed"
        )
        assert _files(settings).get("logo").content == b"backup-image"
        assert _files(settings).list_entries() == [("empty", 0), ("logo", 12)]
        assert (_data(settings) / "legacy.txt").read_bytes() == b"legacy-backup"
        assert stat.S_IMODE((_data(settings) / "sdk-files").stat().st_mode) == 0o700
        assert all(
            stat.S_IMODE(path.stat().st_mode) == 0o600
            for path in (_data(settings) / "sdk-files").iterdir()
        )
        assert runtime.calls == ["stop", "migrate", "verify"]
    assert not list(settings.backups.storage_dir.glob(".rollback-*"))


def _seed_installation(settings):
    """Minimal fake-runtime Core DB, deliberately not Alembic migration evidence."""
    blob = service_package()
    digest = hashlib.sha256(blob).hexdigest()
    packages = settings.backend.uploads_dir / "modules"
    packages.mkdir()
    (packages / f"{digest}.zip").write_bytes(blob)
    with sqlite3.connect(settings.backups.agent_data_dir.parent / "core/3mm.db") as db:
        for name, kind in (
            ("module_id", "TEXT"),
            ("module_package_id", "INTEGER"),
            ("instance_id", "TEXT"),
            ("socket_path", "TEXT"),
            ("health_checked_at", "TEXT"),
            ("error", "TEXT"),
        ):
            db.execute(
                f"ALTER TABLE application_extension_installations ADD COLUMN {name} {kind}"
            )
        db.execute(
            "CREATE TABLE module_packages(id INTEGER PRIMARY KEY, module_id TEXT, version TEXT, sha256 TEXT)"
        )
        db.execute(
            "INSERT INTO module_packages VALUES(1, ?, '1.0.0', ?)", (MODULE_ID, digest)
        )
        db.execute(
            """INSERT INTO application_extension_installations(
            id, authority_incarnation, authority_epoch, authority_mode,
            configuration, status, enabled, module_id, module_package_id, instance_id, socket_path)
            VALUES(1, ?, ?, 'compatibility', ?, 'active', 1, ?, 1, ?, 'old.sock')""",
            (
                "b" * 32,
                "c" * 32,
                '{"READER_DEVICE_ID":"dev_0123456789abcdef0123456789abcdef"}',
                MODULE_ID,
                INSTANCE,
            ),
        )


def test_downloaded_backup_recovers_after_original_key_and_state_are_lost(
    tmp_path, monkeypatch
):
    original = tmp_path / "original"
    original.mkdir()
    source = _settings(original)
    _seed_installation(source)
    _files(source).put("logo", b"portable-private", expected_sha256=None)
    with sqlite3.connect(_data(source) / "state.sqlite3") as db:
        db.execute("CREATE TABLE sample(value TEXT)")
        db.execute("INSERT INTO sample VALUES('saved-state')")
    instance = _data(source).parent
    (instance / "active.json").write_text("runtime metadata is not a data archive")
    (instance / "run").mkdir()
    (instance / "run/service.sock").write_bytes(b"transient")
    (instance / "releases").mkdir()
    (instance / "releases/private.key").write_bytes(b"not-a-backup-entry")
    preview = build_backup_preview(source)
    assert preview.ready
    assert {e.path for e in preview.manifest.entries if e.area == "applications"} == {
        f"{INSTANCE}/data/sdk-files/.lock",
        f"{INSTANCE}/data/sdk-files/blob_logo",
        f"{INSTANCE}/data/state.sqlite3",
    }
    backup, old_key = _backup(source, original)
    old_key_bytes = old_key.read_bytes()
    export = create_portable_export(
        source.backups.storage_dir, old_key, backup.backup_id, "portable-password"
    )
    downloaded = tmp_path / "download.3mmrecovery"
    shutil.copyfile(export.path, downloaded)
    # Only the pytest-owned fixture directory is erased; the downloaded file survives.
    shutil.rmtree(original)
    target_root = tmp_path / "fresh"
    target_root.mkdir()
    target = _settings(target_root)
    _files(target).put("unrelated", b"fresh-data", expected_sha256=None)
    target.backups.storage_dir.mkdir()
    new_key = target_root / "keys/backup.key"
    imported_id = import_portable_backup(
        downloaded,
        target.backups.storage_dir,
        new_key,
        "portable-password",
        max_archive_bytes=32 * 1024 * 1024,
    )
    assert new_key.read_bytes() != old_key_bytes
    supervisor = Supervisor()

    def activate(path, digest, **kwargs):
        # Real package validation, staging, SDK snapshot and activation; no root chown/systemd.
        kwargs.pop("service_uid")
        kwargs.pop("service_gid")
        return activate_application_package(
            path, digest, **kwargs, supervisor=supervisor, client_factory=ReadyClient
        )

    monkeypatch.setattr(reconstruction, "activate_application_package", activate)
    monkeypatch.setattr(reconstruction, "WANTS_ROOT", target_root / "wants")

    class Runtime(Controller):
        def activate_and_verify(self):
            super().activate_and_verify()
            assert _files(target).get("logo").content == b"portable-private"
            assert reconstruction.restore_application_extensions(
                target_root / "core/3mm.db",
                upload_root=target.backend.uploads_dir / "modules",
                application_root=target.backups.application_extensions_dir,
                key_root=target_root / "application-keys",
                service_ids=(os.getuid(), os.getgid()),
            ) == (MODULE_ID,)

    assert (
        _restore(target, target_root, imported_id, new_key, Runtime()).state
        == "completed"
    )
    assert _files(target).list_entries() == [("logo", 16)]
    with sqlite3.connect(_data(target) / "state.sqlite3") as db:
        assert db.execute("SELECT value FROM sample").fetchall() == [("saved-state",)]
    with sqlite3.connect(target_root / "core/3mm.db") as db:
        epoch, config, error = db.execute(
            "SELECT authority_epoch, configuration, error FROM application_extension_installations"
        ).fetchone()
        assert epoch != "c" * 32  # Old backup cannot reactivate old authority.
        assert "dev_0123456789abcdef0123456789abcdef" in config and error is None
    assert supervisor.calls[-1] == ("restart", INSTANCE)
    assert not list(_data(target).parent.glob(".activation-*.rollback"))


@pytest.mark.parametrize("present", [False, True])
def test_absent_and_empty_sdk_namespaces_roundtrip(tmp_path, present):
    settings = _settings(tmp_path)
    files = _files(settings)
    (_data(settings) / "legacy.txt").write_bytes(b"keep")
    if present:
        item = files.put("temporary", b"remove", expected_sha256=None)
        files.delete("temporary", expected_sha256=item.sha256)
    backup, key = _backup(settings, tmp_path)
    files.put("new", b"live", expected_sha256=None)
    _restore(settings, tmp_path, backup.backup_id, key, Controller())
    assert (_data(settings) / "sdk-files").exists() is present
    assert _files(settings).list_entries() == []


@pytest.mark.parametrize(
    "marker", [".activation-123.rollback", ".database-123.rollback"]
)
def test_pending_activation_evidence_blocks_backup_and_restore(tmp_path, marker):
    settings = _settings(tmp_path)
    files = _files(settings)
    files.put("logo", b"safe", expected_sha256=None)
    backup, key = _backup(settings, tmp_path)
    evidence = _data(settings).parent / marker
    evidence.mkdir()
    (evidence / "evidence.json").write_bytes(b"retain-for-review")
    preview = build_backup_preview(settings)
    assert not preview.ready
    assert any(
        issue.code == "state.application_data_invalid" for issue in preview.issues
    )
    before_key = key.read_bytes()
    backup_controller = Controller()
    with pytest.raises(ValueError, match="rollback evidence"):
        create_backup(
            settings, key_file=key, requested_by_user_id=7, controller=backup_controller
        )
    assert backup_controller.calls == []
    assert key.read_bytes() == before_key
    assert len(list(settings.backups.storage_dir.glob("*.3mmbak"))) == 1
    runtime = Controller()
    with pytest.raises(ValueError, match="rollback evidence"):
        _restore(settings, tmp_path, backup.backup_id, key, runtime)
    assert runtime.calls == []
    assert (evidence / "evidence.json").read_bytes() == b"retain-for-review"
    assert files.get("logo").content == b"safe"
    assert (
        read_backup_operation_status(
            settings.backups.storage_dir / "status.json"
        ).error_code
        == "restore_validation_failed"
    )


@pytest.mark.parametrize(
    "unsafe",
    ["symlink", "hardlink", "fifo", "pending", "missing-lock", "nonempty-lock", "busy"],
)
def test_backup_preview_refuses_unsafe_private_namespace(tmp_path, unsafe):
    import fcntl

    settings = _settings(tmp_path)
    _files(settings).put("logo", b"private", expected_sha256=None)
    namespace = _data(settings) / "sdk-files"
    foreign = tmp_path / "foreign"
    foreign.write_bytes(b"untouched")
    locked = None
    if unsafe == "symlink":
        (namespace / "blob_logo").unlink()
        (namespace / "blob_logo").symlink_to(foreign)
    elif unsafe == "hardlink":
        os.link(foreign, namespace / "blob_link")
    elif unsafe == "fifo":
        os.mkfifo(namespace / "blob_pipe")
    elif unsafe == "pending":
        (namespace / ".pending-leftover").write_bytes(b"retain")
    elif unsafe == "missing-lock":
        (namespace / ".lock").unlink()
    elif unsafe == "nonempty-lock":
        (namespace / ".lock").write_bytes(b"unknown")
    else:
        locked = (namespace / ".lock").open("rb")
        fcntl.flock(locked, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        preview = build_backup_preview(settings)
        assert not preview.ready
        assert any(
            issue.code == "state.application_data_invalid" for issue in preview.issues
        )
        assert foreign.read_bytes() == b"untouched"
        assert (namespace / ".lock").exists() is (unsafe != "missing-lock")
    finally:
        if locked:
            locked.close()


def _entry(name, size=0):
    return BackupEntryV1(
        area="applications",
        path=f"{INSTANCE}/data/sdk-files/{name}",
        sensitivity="secret",
        size_bytes=size,
        sha256="a" * 64,
    )


@pytest.mark.parametrize("limit", ["file", "count", "total"])
def test_backup_source_quotas_fail_before_hashing_or_archiving(tmp_path, limit):
    settings = _settings(tmp_path)
    _files(settings).put("logo", b"safe", expected_sha256=None)
    namespace = _data(settings) / "sdk-files"
    if limit == "file":
        with (namespace / "blob_large").open("wb") as stream:
            stream.truncate(16 * 1024 * 1024 + 1)
    else:
        for index in range(1024 if limit == "count" else 5):
            with (namespace / f"blob_item_{index}").open("wb") as stream:
                if limit == "total":
                    stream.truncate(16 * 1024 * 1024)
    preview = build_backup_preview(settings)
    assert not preview.ready and preview.manifest is None
    assert any(
        issue.code == "state.application_data_invalid" for issue in preview.issues
    )
    assert (namespace / "blob_logo").read_bytes() == b"safe"
    assert not settings.backups.storage_dir.exists()


def test_backup_accepts_explicit_sdk_bounds_above_defaults(tmp_path):
    settings = _settings(tmp_path)
    data = _data(settings)
    data.mkdir(parents=True)
    content = b"x" * (1024 * 1024 + 1)
    files = ApplicationFileStorage(data, limits=ApplicationFileLimits(2 * 1024 * 1024))
    before = files.put("large", content, expected_sha256=None)
    backup, key = _backup(settings, tmp_path)
    files.delete("large", expected_sha256=before.sha256)
    assert (
        _restore(settings, tmp_path, backup.backup_id, key, Controller()).state
        == "completed"
    )
    assert files.get("large").sha256 == before.sha256


@pytest.mark.parametrize(
    "entries, message",
    [
        ((_entry("blob_logo"),), "incomplete"),
        ((_entry(".lock", 1),), "lock"),
        ((_entry(".lock"), _entry(".pending")), "identity"),
        ((_entry(".lock"), _entry("nested/blob_logo")), "namespace"),
        ((_entry(".lock"), _entry("blob_logo", 16 * 1024 * 1024 + 1)), "size limit"),
        (
            (_entry(".lock"), *(_entry(f"blob_item_{i}") for i in range(1025))),
            "count limit",
        ),
        (
            (
                _entry(".lock"),
                *(_entry(f"blob_item_{i}", 16 * 1024 * 1024) for i in range(5)),
            ),
            "total size",
        ),
    ],
)
def test_imported_inventory_is_bounded_before_extraction(entries, message):
    with pytest.raises(ValueError, match=message):
        validate_application_backup_inventory(entries)


@pytest.mark.parametrize(
    "path",
    [f"{INSTANCE}/active.json", f"{INSTANCE}/releases/code.py", "platform/socket"],
)
def test_archive_cannot_restore_runtime_data_as_application_files(path):
    entry = BackupEntryV1(
        area="applications",
        path=path,
        sensitivity="secret",
        size_bytes=0,
        sha256="a" * 64,
    )
    with pytest.raises(ValueError, match="data namespace"):
        validate_application_backup_inventory((entry,))


def test_even_authenticated_archive_with_pending_file_fails_before_stop(tmp_path):
    settings = _settings(tmp_path)
    _files(settings).put("logo", b"safe", expected_sha256=None)
    backup, key = _backup(settings, tmp_path)
    encrypted = settings.backups.storage_dir / backup.archive_name
    plain = tmp_path / "plain.tar"
    recovery._decrypt_archive(encrypted, key, plain)
    modified = tmp_path / "modified.tar"
    with tarfile.open(plain, "r") as source, tarfile.open(modified, "w") as target:
        for member in source.getmembers():
            content = source.extractfile(member).read()
            if member.name == "manifest.json":
                manifest = BackupManifestV1.model_validate_json(content)
                entries = tuple(
                    entry.model_copy(
                        update={
                            "path": entry.path.replace("blob_logo", ".pending-leftover")
                        }
                    )
                    for entry in manifest.entries
                )
                content = (
                    manifest.model_copy(update={"entries": entries})
                    .model_dump_json()
                    .encode()
                )
                member.size = len(content)
            member.name = member.name.replace("blob_logo", ".pending-leftover")
            target.addfile(member, io.BytesIO(content))
    encrypt_file(modified, encrypted, key.read_bytes())
    staging = tmp_path / "test-staging"
    staging.mkdir()
    with pytest.raises(ValueError, match="identity"):
        recovery._validate_and_stage(modified, staging, backup.backup_id)
    assert not (staging / "payload").exists()
    runtime = Controller()
    with pytest.raises(ValueError, match="identity"):
        _restore(settings, tmp_path, backup.backup_id, key, runtime)
    assert runtime.calls == []
    assert _files(settings).get("logo").content == b"safe"


def test_payload_preparation_uses_private_modes_and_application_service_ids(
    tmp_path, monkeypatch
):
    payload = tmp_path / "payload"
    for name in (
        "core/3mm.db",
        "agent/identity.json",
        "provisioning/provisioning.json",
    ):
        path = payload / name
        path.parent.mkdir(parents=True)
        path.write_bytes(b"fixture")
    data = payload / "applications" / INSTANCE / "data"
    data.mkdir(parents=True)
    ApplicationFileStorage(data).put("logo", b"private", expected_sha256=None)
    calls = []
    monkeypatch.setattr(
        recovery.os,
        "chown",
        lambda path, uid, gid: calls.append((Path(path), uid, gid)),
    )
    recovery._prepare_payload(payload, 101, 102, application_service_ids=(201, 202))
    namespace = data / "sdk-files"
    assert stat.S_IMODE(namespace.stat().st_mode) == 0o700
    for path in (namespace / ".lock", namespace / "blob_logo"):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert (path, 201, 202) in calls
    assert (namespace, 201, 202) in calls
    assert (payload / "core/3mm.db", 101, 102) in calls
