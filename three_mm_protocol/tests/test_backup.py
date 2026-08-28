from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from three_mm_protocol import (
    BackupCompatibilityV1,
    BackupEntryV1,
    BackupManifestV1,
    BackupProtectionV1,
)


def _entry(**overrides) -> BackupEntryV1:
    values = {
        "area": "core",
        "path": "3mm.db",
        "sensitivity": "secret",
        "size_bytes": 128,
        "sha256": "a" * 64,
    }
    values.update(overrides)
    return BackupEntryV1.model_validate(values)


def _manifest(*, entries=None, protection=None, total_size_bytes=128):
    return BackupManifestV1(
        backup_id="bkp_20260828T120000Z_0123abcd",
        created_at=datetime.now(UTC),
        device_id="dev_0123456789abcdef0123456789abcdef",
        compatibility=BackupCompatibilityV1(
            application_version="0.3.0-beta.9",
            protocol_version="1.0",
            database_revision="18d2e3f4a5b6",
            architecture="aarch64",
        ),
        protection=protection
        or BackupProtectionV1(
            mode="device-bound",
            export_policy="local-only",
            secret_material_included=True,
        ),
        entries=entries or (_entry(),),
        total_size_bytes=total_size_bytes,
    )


def test_backup_manifest_round_trip_is_strict_and_json_safe():
    original = _manifest()

    restored = BackupManifestV1.model_validate_json(original.model_dump_json())

    assert restored == original


@pytest.mark.parametrize(
    "path", ("/etc/3mm/3mm.env", "../agent/identity.json", "core\\3mm.db")
)
def test_backup_entry_rejects_unsafe_paths(path):
    with pytest.raises(ValidationError):
        _entry(path=path)


def test_backup_manifest_rejects_duplicate_entry_paths():
    entries = (_entry(), _entry(size_bytes=64, sha256="b" * 64))

    with pytest.raises(ValidationError, match="must be unique"):
        _manifest(entries=entries, total_size_bytes=192)


def test_backup_manifest_rejects_incorrect_total_size():
    with pytest.raises(ValidationError, match="total size"):
        _manifest(total_size_bytes=127)


def test_secret_entries_cannot_be_marked_downloadable_or_unprotected():
    with pytest.raises(ValidationError, match="device-bound and local-only"):
        BackupProtectionV1(
            mode="none",
            export_policy="downloadable",
            secret_material_included=True,
        )


def test_protection_metadata_must_match_entry_sensitivity():
    protection = BackupProtectionV1(
        mode="none",
        export_policy="downloadable",
        secret_material_included=False,
    )

    with pytest.raises(ValidationError, match="entry sensitivity"):
        _manifest(protection=protection)
