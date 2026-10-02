import os
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import backend.database  # noqa: F401 - register existing ORM relationship targets
from backend.db.installation_identity import CoreInstallationIdentity
from backend.services.installation_identity import (
    InstallationIdentityError,
    installation_identity,
    prove_installation_identity,
    validate_identity_backup,
)
from backend.services.backups import build_backup_preview
from backend.tests.test_backup_preview import _settings
from deployment.create_backup import create_backup
from deployment.portable_backup import create_portable_export, import_portable_backup
from deployment.restore_backup import restore_backup
from three_mm_protocol.installation_identity import verify_installation_proof
from three_mm_protocol.tests.test_installation_identity import proof_request


@pytest.mark.parametrize("fail_migration", [False, True])
def test_portable_recovery_replaces_destination_identity_and_preserves_signing_key(
    tmp_path, monkeypatch, fail_migration
):
    settings = _settings(tmp_path)
    master_key = Fernet.generate_key().decode()
    monkeypatch.setenv("AI_SETTINGS_MASTER_KEY", master_key)
    settings.backups.host_config_file.write_text(
        "AI_SETTINGS_MASTER_KEY=" + master_key + "\n", encoding="utf-8"
    )
    engine = create_engine(settings.database_url)
    CoreInstallationIdentity.__table__.create(engine)
    with Session(engine) as db:
        original = installation_identity(db).identity
    engine.dispose()

    class Controller:
        def stop(self, _services):
            pass

        def start(self, _services):
            pass

        def migrate(self):
            if fail_migration:
                raise RuntimeError("fixture migration failure")

        def activate_and_verify(self):
            # Real systemd starts with the restored protected host environment.
            value = (
                settings.backups.host_config_file.read_text().strip().split("=", 1)[1]
            )
            monkeypatch.setenv("AI_SETTINGS_MASTER_KEY", value)
            engine = create_engine(settings.database_url)
            try:
                with Session(engine) as db:
                    assert installation_identity(db).identity == (
                        destination if fail_migration else original
                    )
            finally:
                engine.dispose()

    backup_key = tmp_path / "backup.key"
    backup = create_backup(
        settings, key_file=backup_key, requested_by_user_id=1, controller=Controller()
    )
    export = create_portable_export(
        settings.backups.storage_dir,
        backup_key,
        backup.backup_id,
        "fixture-recovery-password",
    )
    imported_root = tmp_path / "imported-backups"
    fresh_key = tmp_path / "fresh-backup.key"
    imported_id = import_portable_backup(
        export.path,
        imported_root,
        fresh_key,
        "fixture-recovery-password",
        max_archive_bytes=32 * 1024 * 1024,
    )

    # Simulate a clean destination that already used G1 with a different master.
    monkeypatch.setenv("AI_SETTINGS_MASTER_KEY", Fernet.generate_key().decode())
    settings.backups.host_config_file.write_text(
        "AI_SETTINGS_MASTER_KEY=" + os.environ["AI_SETTINGS_MASTER_KEY"] + "\n",
        encoding="utf-8",
    )
    engine = create_engine(settings.database_url)
    with Session(engine) as db:
        db.delete(db.get(CoreInstallationIdentity, 1))
        db.commit()
        destination = installation_identity(db).identity
        assert destination != original
    engine.dispose()
    destination_settings = settings.model_copy(
        update={
            "backups": settings.backups.model_copy(
                update={"storage_dir": imported_root}
            )
        }
    )

    def restore():
        return restore_backup(
            destination_settings,
            backup_id=imported_id,
            key_file=fresh_key,
            requested_by_user_id=1,
            runtime=Controller(),
            service_ids=(1000, 1000),
            state_root=tmp_path,
            host_config=settings.backups.host_config_file,
            apply_ownership=False,
        )

    if fail_migration:
        with pytest.raises(RuntimeError, match="fixture migration failure"):
            restore()
    else:
        assert restore().state == "completed"
    engine = create_engine(settings.database_url)
    try:
        now = datetime.now(UTC)
        request = proof_request(created_at=now, expires_at=now + timedelta(seconds=90))
        with Session(engine) as db:
            proof = prove_installation_identity(db, request, now=now)
        expected = destination if fail_migration else original
        assert (
            verify_installation_proof(
                proof, expected_identity=expected, expected_request=request, now=now
            )
            == expected
        )
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "failure", ["missing", "wrong", "duplicate", "corrupt_identity"]
)
def test_backup_preview_refuses_unrecoverable_identity_without_exposing_secrets(
    tmp_path, monkeypatch, failure
):
    settings = _settings(tmp_path)
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("AI_SETTINGS_MASTER_KEY", key)
    settings.backups.host_config_file.write_text("AI_SETTINGS_MASTER_KEY=" + key + "\n")
    engine = create_engine(settings.database_url)
    try:
        CoreInstallationIdentity.__table__.create(engine)
        with Session(engine) as db:
            installation_identity(db)
            if failure == "corrupt_identity":
                db.get(CoreInstallationIdentity, 1).encrypted_private_key = (
                    "invalid fixture ciphertext"
                )
                db.commit()
        if failure == "missing":
            settings.backups.host_config_file.unlink()
        elif failure == "wrong":
            settings.backups.host_config_file.write_text(
                "AI_SETTINGS_MASTER_KEY=" + Fernet.generate_key().decode() + "\n"
            )
        elif failure == "duplicate":
            settings.backups.host_config_file.write_text(
                ("AI_SETTINGS_MASTER_KEY=" + key + "\n") * 2
            )
        with pytest.raises(InstallationIdentityError, match="recovery material"):
            validate_identity_backup(
                tmp_path / "core/3mm.db", settings.backups.host_config_file
            )
        preview = build_backup_preview(settings)
        assert not preview.ready
        assert any(
            issue.code == "compatibility.installation_identity"
            for issue in preview.issues
        )
        assert key not in preview.model_dump_json()
        assert "fixture ciphertext" not in preview.model_dump_json()
    finally:
        engine.dispose()


def test_identity_restore_validation_failure_precedes_service_stop(
    tmp_path, monkeypatch
):
    settings = _settings(tmp_path)
    key = tmp_path / "backup.key"
    calls = []

    class Controller:
        def stop(self, _services):
            calls.append("stop")

        def start(self, _services):
            pass

        def migrate(self):
            calls.append("migrate")

        def activate_and_verify(self):
            calls.append("activate")

    backup = create_backup(
        settings, key_file=key, requested_by_user_id=1, controller=Controller()
    )
    calls.clear()

    def reject_staged_identity(database, host_config):
        assert database.name == "3mm.db" and database != tmp_path / "core/3mm.db"
        assert host_config.name == "3mm.env"
        raise InstallationIdentityError(
            "Installation identity recovery material is missing or invalid"
        )

    monkeypatch.setattr(
        "deployment.restore_backup.validate_identity_backup", reject_staged_identity
    )
    with pytest.raises(InstallationIdentityError, match="recovery material"):
        restore_backup(
            settings,
            backup_id=backup.backup_id,
            key_file=key,
            requested_by_user_id=1,
            runtime=Controller(),
            service_ids=(1000, 1000),
            state_root=tmp_path,
            host_config=settings.backups.host_config_file,
            apply_ownership=False,
        )
    assert calls == []
