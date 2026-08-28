"""Password-protected portable recovery bundles for Standalone backups."""

from __future__ import annotations

import hashlib
import io
import os
import tarfile
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from pydantic import BaseModel, ConfigDict, Field

from backend.services.backups import (
    BACKUP_ID_PATTERN,
    BackupCatalogItem,
    checksum_file,
    list_backup_catalog,
    write_backup_catalog_item,
)
from deployment.create_backup import _load_or_create_key, encrypt_file
from deployment.restore_backup import _decrypt_archive_with_key, _validate_and_stage


PORTABLE_MAGIC = b"3MMREC1\0"
PORTABLE_VERSION = 1
SALT_BYTES = 16
NONCE_BYTES = 12
TAG_BYTES = 16
MAX_METADATA_BYTES = 64 * 1024
MIN_PASSPHRASE_BYTES = 8
MAX_PASSPHRASE_BYTES = 256


class PortableMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    format_version: int = Field(default=PORTABLE_VERSION, ge=1, le=1)
    backup_id: str = Field(pattern=BACKUP_ID_PATTERN)
    archive_name: str
    archive_size_bytes: int = Field(ge=1)
    archive_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class PortableExport:
    export_id: str
    backup_id: str
    filename: str
    path: Path


class _PortableEncryptingWriter:
    def __init__(self, target, key: bytes, salt: bytes) -> None:
        self._target = target
        self._nonce = os.urandom(NONCE_BYTES)
        self._encryptor = Cipher(
            algorithms.AES(key), modes.GCM(self._nonce)
        ).encryptor()
        self._position = 0
        target.write(PORTABLE_MAGIC + salt + self._nonce)

    def write(self, data: bytes) -> int:
        self._target.write(self._encryptor.update(data))
        self._position += len(data)
        return len(data)

    def tell(self) -> int:
        return self._position

    def flush(self) -> None:
        self._target.flush()

    def finalize(self) -> None:
        self._target.write(self._encryptor.finalize())
        self._target.write(self._encryptor.tag)
        self._target.flush()
        os.fsync(self._target.fileno())


def _passphrase_bytes(passphrase: str) -> bytes:
    encoded = passphrase.encode("utf-8")
    if not MIN_PASSPHRASE_BYTES <= len(encoded) <= MAX_PASSPHRASE_BYTES:
        raise ValueError("Recovery password must be between 8 and 256 bytes")
    return encoded


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    return Scrypt(salt=salt, length=32, n=2**14, r=8, p=1).derive(
        _passphrase_bytes(passphrase)
    )


def _safe_device_key(key_file: Path) -> bytes:
    key = key_file.read_bytes()
    unsafe_mode = os.name != "nt" and bool(key_file.stat().st_mode & 0o077)
    if len(key) != 32 or unsafe_mode:
        raise ValueError("Device backup key is missing or unsafe")
    return key


def create_portable_export(
    backup_root: Path,
    key_file: Path,
    backup_id: str,
    passphrase: str,
    *,
    owner: tuple[int, int] | None = None,
) -> PortableExport:
    item = next(
        (
            candidate
            for candidate in list_backup_catalog(backup_root).items
            if candidate.backup_id == backup_id
        ),
        None,
    )
    if item is None:
        raise ValueError("Selected backup is unavailable")
    archive = backup_root / item.archive_name
    size, digest = checksum_file(archive)
    if size != item.archive_size_bytes or digest != item.archive_sha256:
        raise ValueError("Selected backup failed its catalog checksum")

    recovery_key = _safe_device_key(key_file)
    salt = os.urandom(SALT_BYTES)
    portable_key = _derive_key(passphrase, salt)
    export_id = uuid.uuid4().hex
    export_dir = backup_root / "exports"
    # The helper creates exports as root, while Core serves and removes them as
    # the 3mm group.  Keep directory listing private, but allow known files to
    # be opened and unlinked after their one-time download.
    export_dir.mkdir(parents=True, exist_ok=True, mode=0o730)
    os.chmod(export_dir, 0o730)
    if owner is not None:
        os.chown(export_dir, *owner)
    output = export_dir / f"{export_id}.3mmrecovery"
    temporary = output.with_suffix(".tmp")
    metadata = PortableMetadata(
        backup_id=item.backup_id,
        archive_name=item.archive_name,
        archive_size_bytes=size,
        archive_sha256=digest,
    ).model_dump_json(indent=2).encode("utf-8")
    try:
        with temporary.open("xb") as raw:
            os.chmod(temporary, 0o640)
            encrypted = _PortableEncryptingWriter(raw, portable_key, salt)
            with tarfile.open(
                fileobj=encrypted, mode="w|", format=tarfile.PAX_FORMAT
            ) as bundle:
                metadata_info = tarfile.TarInfo("bundle.json")
                metadata_info.size = len(metadata)
                metadata_info.mode = 0o600
                bundle.addfile(metadata_info, io.BytesIO(metadata))
                key_info = tarfile.TarInfo("recovery.key")
                key_info.size = len(recovery_key)
                key_info.mode = 0o600
                bundle.addfile(key_info, io.BytesIO(recovery_key))
                archive_info = tarfile.TarInfo("backup.3mmbak")
                archive_info.size = size
                archive_info.mode = 0o600
                with archive.open("rb") as source:
                    bundle.addfile(archive_info, source)
            encrypted.finalize()
        if owner is not None:
            os.chown(temporary, *owner)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return PortableExport(
        export_id=export_id,
        backup_id=backup_id,
        filename=f"{backup_id}.3mmrecovery",
        path=output,
    )


def _decrypt_portable(source_path: Path, passphrase: str, destination: Path) -> None:
    size = source_path.stat().st_size
    header_size = len(PORTABLE_MAGIC) + SALT_BYTES + NONCE_BYTES
    if size <= header_size + TAG_BYTES:
        raise ValueError("Portable recovery file is truncated")
    with source_path.open("rb") as source:
        if source.read(len(PORTABLE_MAGIC)) != PORTABLE_MAGIC:
            raise ValueError("Portable recovery file header is invalid")
        salt = source.read(SALT_BYTES)
        nonce = source.read(NONCE_BYTES)
        source.seek(-TAG_BYTES, os.SEEK_END)
        tag = source.read(TAG_BYTES)
        remaining = size - header_size - TAG_BYTES
        source.seek(header_size)
        decryptor = Cipher(
            algorithms.AES(_derive_key(passphrase, salt)),
            modes.GCM(nonce, tag),
        ).decryptor()
        with destination.open("xb") as target:
            os.chmod(destination, 0o600)
            try:
                while remaining:
                    block = source.read(min(1024 * 1024, remaining))
                    if not block:
                        raise ValueError("Portable recovery file is truncated")
                    remaining -= len(block)
                    target.write(decryptor.update(block))
                target.write(decryptor.finalize())
            except InvalidTag as exc:
                raise ValueError(
                    "Portable recovery password or file is invalid"
                ) from exc


def _extract_bundle(
    bundle_path: Path,
    work: Path,
    *,
    max_archive_bytes: int,
) -> tuple[PortableMetadata, bytes, Path]:
    with tarfile.open(bundle_path, mode="r:") as bundle:
        members = bundle.getmembers()
        by_name = {member.name: member for member in members}
        if len(by_name) != len(members) or set(by_name) != {
            "bundle.json",
            "recovery.key",
            "backup.3mmbak",
        }:
            raise ValueError("Portable recovery contents are invalid")
        metadata_member = by_name["bundle.json"]
        key_member = by_name["recovery.key"]
        archive_member = by_name["backup.3mmbak"]
        if (
            not metadata_member.isfile()
            or metadata_member.size > MAX_METADATA_BYTES
            or not key_member.isfile()
            or key_member.size != 32
            or not archive_member.isfile()
            or not 1 <= archive_member.size <= max_archive_bytes
        ):
            raise ValueError("Portable recovery entry size or type is invalid")
        metadata_file = bundle.extractfile(metadata_member)
        key_file = bundle.extractfile(key_member)
        archive_file = bundle.extractfile(archive_member)
        if metadata_file is None or key_file is None or archive_file is None:
            raise ValueError("Portable recovery entries cannot be read")
        metadata = PortableMetadata.model_validate_json(metadata_file.read())
        recovery_key = key_file.read()
        archive = work / "imported.3mmbak"
        digest = hashlib.sha256()
        with archive.open("xb") as target:
            os.chmod(archive, 0o600)
            for block in iter(lambda: archive_file.read(1024 * 1024), b""):
                digest.update(block)
                target.write(block)
        if (
            archive.stat().st_size != metadata.archive_size_bytes
            or archive_member.size != metadata.archive_size_bytes
            or digest.hexdigest() != metadata.archive_sha256
            or metadata.archive_name != f"{metadata.backup_id}.3mmbak"
        ):
            raise ValueError("Portable recovery archive checksum is invalid")
    return metadata, recovery_key, archive


def import_portable_backup(
    upload: Path,
    backup_root: Path,
    key_file: Path,
    passphrase: str,
    *,
    max_archive_bytes: int,
    owner: tuple[int, int] | None = None,
) -> str:
    if upload.is_symlink() or not upload.is_file():
        raise ValueError("Portable recovery upload is unavailable")
    if upload.stat().st_size > max_archive_bytes + 1024 * 1024:
        raise ValueError("Portable recovery upload is too large")
    try:
        with tempfile.TemporaryDirectory(prefix=".portable-import-") as temporary:
            work = Path(temporary)
            decrypted_bundle = work / "bundle.tar"
            _decrypt_portable(upload, passphrase, decrypted_bundle)
            metadata, recovery_key, imported_archive = _extract_bundle(
                decrypted_bundle,
                work,
                max_archive_bytes=max_archive_bytes,
            )
            plaintext = work / "archive.tar"
            staging = work / "staging"
            staging.mkdir(mode=0o700)
            _decrypt_archive_with_key(imported_archive, recovery_key, plaintext)
            manifest = _validate_and_stage(
                plaintext,
                staging,
                metadata.backup_id,
            )
            existing = next(
                (
                    item
                    for item in list_backup_catalog(backup_root).items
                    if item.backup_id == metadata.backup_id
                ),
                None,
            )
            if existing is not None:
                return existing.backup_id
            backup_root.mkdir(parents=True, exist_ok=True, mode=0o750)
            destination = backup_root / f"{manifest.backup_id}.3mmbak"
            if destination.exists():
                raise ValueError("A conflicting local backup already exists")
            device_key = _load_or_create_key(key_file)
            encrypt_file(plaintext, destination, device_key)
            archive_size, archive_sha256 = checksum_file(destination)
            try:
                write_backup_catalog_item(
                    backup_root,
                    BackupCatalogItem(
                        backup_id=manifest.backup_id,
                        archive_name=destination.name,
                        created_at=manifest.created_at,
                        application_version=manifest.compatibility.application_version,
                        database_revision=manifest.compatibility.database_revision,
                        architecture=manifest.compatibility.architecture,
                        entry_count=len(manifest.entries),
                        payload_size_bytes=manifest.total_size_bytes,
                        archive_size_bytes=archive_size,
                        archive_sha256=archive_sha256,
                        protection=manifest.protection,
                    ),
                    owner=owner,
                )
                os.chmod(destination, 0o640)
                if owner is not None:
                    os.chown(destination, *owner)
            except Exception:
                destination.unlink(missing_ok=True)
                raise
            return manifest.backup_id
    finally:
        upload.unlink(missing_ok=True)


def remove_export(path: Path) -> None:
    if path.is_file() and not path.is_symlink():
        path.unlink()
    parent = path.parent
    try:
        parent.rmdir()
    except OSError:
        pass
