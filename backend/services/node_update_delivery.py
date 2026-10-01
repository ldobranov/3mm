"""Bounded Hub-side storage for prepared per-device Node update artifacts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import uuid

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from backend.config import UpdateCatalogSettings
from three_mm_protocol.node_updates import (
    DEVICE_PATTERN,
    OPERATION_PATTERN,
    RELEASE_PATTERN,
    SHA256_PATTERN,
)

DELIVERY_SUBDIR = "node-delivery"
MAX_DELIVERY_SECONDS = 60 * 60
MAX_PREPARED_OPERATIONS = 16


class NodeDeliveryError(RuntimeError):
    pass


class PreparedNodeDelivery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = 1

    operation_id: str = Field(pattern=OPERATION_PATTERN)
    device_id: str = Field(pattern=DEVICE_PATTERN)
    release_id: str = Field(pattern=RELEASE_PATTERN, max_length=80)
    archive_sha256: str = Field(pattern=SHA256_PATTERN)

    archive_size_bytes: int = Field(
        gt=0,
        le=512 * 1024 * 1024,
    )

    prepared_at: AwareDatetime
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def bounded_delivery_window(self):
        duration = (
            self.expires_at - self.prepared_at
        ).total_seconds()

        if not 0 < duration <= MAX_DELIVERY_SECONDS:
            raise ValueError(
                "Node delivery lifetime must be bounded"
            )

        return self


def delivery_root(
    settings: UpdateCatalogSettings,
) -> Path:
    return (
        Path(settings.staging_dir)
        / DELIVERY_SUBDIR
    )


def _operation_directory(
    settings: UpdateCatalogSettings,
    operation_id: str,
) -> Path:
    if not operation_id.startswith("nodeupd_"):
        raise NodeDeliveryError(
            "Invalid Node update operation"
        )

    if len(operation_id) != len("nodeupd_") + 32:
        raise NodeDeliveryError(
            "Invalid Node update operation"
        )

    suffix = operation_id.removeprefix(
        "nodeupd_"
    )

    if any(
        character not in "0123456789abcdef"
        for character in suffix
    ):
        raise NodeDeliveryError(
            "Invalid Node update operation"
        )

    return (
        delivery_root(settings)
        / operation_id
    )


def _read_small_json(
    path: Path,
    limit: int = 64 * 1024,
) -> dict:
    try:
        info = path.lstat()

        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_size > limit
        ):
            raise NodeDeliveryError(
                "Node delivery metadata is invalid"
            )

        if path.is_symlink():
            raise NodeDeliveryError(
                "Node delivery metadata is unsafe"
            )

        data = path.read_bytes()

        if len(data) > limit:
            raise NodeDeliveryError(
                "Node delivery metadata is too large"
            )

        value = json.loads(
            data.decode("utf-8")
        )

        if not isinstance(value, dict):
            raise ValueError

        return value

    except NodeDeliveryError:
        raise

    except (
        OSError,
        UnicodeDecodeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        raise NodeDeliveryError(
            "Node delivery metadata is invalid"
        ) from exc


def _digest_file(
    path: Path,
    *,
    maximum_bytes: int,
) -> tuple[str, int]:
    try:
        info = path.lstat()

        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or path.is_symlink()
            or info.st_size <= 0
            or info.st_size > maximum_bytes
        ):
            raise NodeDeliveryError(
                "Node delivery archive is invalid"
            )

        checksum = hashlib.sha256()
        size = 0

        flags = (
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
        )

        descriptor = os.open(
            path,
            flags,
        )

        try:
            with os.fdopen(
                descriptor,
                "rb",
            ) as source:
                while True:
                    chunk = source.read(
                        1024 * 1024
                    )

                    if not chunk:
                        break

                    size += len(chunk)

                    if size > maximum_bytes:
                        raise NodeDeliveryError(
                            "Node delivery archive is too large"
                        )

                    checksum.update(chunk)

        except Exception:
            raise

        return (
            checksum.hexdigest(),
            size,
        )

    except NodeDeliveryError:
        raise

    except OSError as exc:
        raise NodeDeliveryError(
            "Node delivery archive cannot be read"
        ) from exc


def stage_node_delivery(
    settings: UpdateCatalogSettings,
    *,
    operation_id: str,
    device_id: str,
    release_id: str,
    archive_sha256: str,
    archive_size_bytes: int,
    source_path: Path,
    now: datetime | None = None,
) -> PreparedNodeDelivery:
    """Store one already downloaded and verified archive for one device."""

    instant = now or datetime.now(UTC)

    prepared = PreparedNodeDelivery(
        operation_id=operation_id,
        device_id=device_id,
        release_id=release_id,
        archive_sha256=archive_sha256,
        archive_size_bytes=archive_size_bytes,
        prepared_at=instant,
        expires_at=instant
        + timedelta(
            seconds=MAX_DELIVERY_SECONDS
        ),
    )

    root = delivery_root(settings)
    root.mkdir(
        parents=True,
        exist_ok=True,
    )

    existing_operations = [
        path
        for path in root.iterdir()
        if path.is_dir()
        and path.name.startswith(
            "nodeupd_"
        )
    ]

    target_directory = (
        _operation_directory(
            settings,
            operation_id,
        )
    )

    if (
        not target_directory.exists()
        and len(existing_operations)
        >= MAX_PREPARED_OPERATIONS
    ):
        raise NodeDeliveryError(
            "Node update delivery staging is full"
        )

    digest, size = _digest_file(
        Path(source_path),
        maximum_bytes=settings.max_artifact_bytes,
    )

    if (
        digest != archive_sha256
        or size != archive_size_bytes
    ):
        raise NodeDeliveryError(
            "Prepared Node archive identity mismatch"
        )

    free_bytes = shutil.disk_usage(
        root
    ).free

    if (
        free_bytes
        < size
        + settings.minimum_free_bytes
    ):
        raise NodeDeliveryError(
            "Insufficient free space for Node update"
        )

    target_directory.mkdir(
        mode=0o700,
        exist_ok=True,
    )

    archive_path = (
        target_directory
        / "release.tar.gz"
    )

    metadata_path = (
        target_directory
        / "metadata.json"
    )

    if (
        archive_path.exists()
        or metadata_path.exists()
    ):
        try:
            existing = (
                PreparedNodeDelivery.model_validate(
                    _read_small_json(
                        metadata_path
                    )
                )
            )
        except Exception as exc:
            raise NodeDeliveryError(
                "Existing Node delivery staging is invalid"
            ) from exc

        if existing != prepared.model_copy(
            update={
                "prepared_at":
                    existing.prepared_at,
                "expires_at":
                    existing.expires_at,
            }
        ):
            raise NodeDeliveryError(
                "Node update operation identity conflict"
            )

        existing_digest, existing_size = (
            _digest_file(
                archive_path,
                maximum_bytes=settings.max_artifact_bytes,
            )
        )

        if (
            existing_digest
            != existing.archive_sha256
            or existing_size
            != existing.archive_size_bytes
        ):
            raise NodeDeliveryError(
                "Existing Node delivery archive is invalid"
            )

        return existing

    temporary_archive = (
        target_directory
        / (
            ".archive-"
            + uuid.uuid4().hex
        )
    )

    temporary_metadata = (
        target_directory
        / (
            ".metadata-"
            + uuid.uuid4().hex
        )
    )

    try:
        with (
            Path(source_path).open(
                "rb"
            ) as source,
            temporary_archive.open(
                "xb"
            ) as destination,
        ):
            shutil.copyfileobj(
                source,
                destination,
                length=1024 * 1024,
            )

            destination.flush()
            os.fsync(
                destination.fileno()
            )

        copied_digest, copied_size = (
            _digest_file(
                temporary_archive,
                maximum_bytes=settings.max_artifact_bytes,
            )
        )

        if (
            copied_digest
            != prepared.archive_sha256
            or copied_size
            != prepared.archive_size_bytes
        ):
            raise NodeDeliveryError(
                "Copied Node delivery archive differs"
            )

        os.replace(
            temporary_archive,
            archive_path,
        )

        payload = (
            prepared.model_dump_json(
                indent=2
            )
            + "\n"
        ).encode("utf-8")

        with temporary_metadata.open(
            "xb"
        ) as saved:
            saved.write(payload)
            saved.flush()
            os.fsync(
                saved.fileno()
            )

        os.replace(
            temporary_metadata,
            metadata_path,
        )

        return prepared

    finally:
        temporary_archive.unlink(
            missing_ok=True
        )
        temporary_metadata.unlink(
            missing_ok=True
        )


def open_node_delivery(
    settings: UpdateCatalogSettings,
    *,
    operation_id: str,
    device_id: str,
    now: datetime | None = None,
) -> tuple[PreparedNodeDelivery, Path]:
    """Resolve a prepared artifact only for the device it was prepared for."""

    instant = now or datetime.now(UTC)

    directory = _operation_directory(
        settings,
        operation_id,
    )

    metadata_path = (
        directory
        / "metadata.json"
    )

    archive_path = (
        directory
        / "release.tar.gz"
    )

    prepared = (
        PreparedNodeDelivery.model_validate(
            _read_small_json(
                metadata_path
            )
        )
    )

    if (
        prepared.operation_id
        != operation_id
    ):
        raise NodeDeliveryError(
            "Node update operation identity mismatch"
        )

    if (
        prepared.device_id
        != device_id
    ):
        raise NodeDeliveryError(
            "Node update artifact belongs to another device"
        )

    if (
        prepared.expires_at
        <= instant
    ):
        raise NodeDeliveryError(
            "Node update delivery has expired"
        )

    digest, size = _digest_file(
        archive_path,
        maximum_bytes=settings.max_artifact_bytes,
    )

    if (
        digest
        != prepared.archive_sha256
        or size
        != prepared.archive_size_bytes
    ):
        raise NodeDeliveryError(
            "Node update delivery archive identity mismatch"
        )

    return (
        prepared,
        archive_path,
    )

def read_node_delivery(
    settings: UpdateCatalogSettings,
    operation_id: str,
) -> PreparedNodeDelivery:
    """Read durable Hub metadata without requiring the delivery to be unexpired."""

    directory = _operation_directory(
        settings,
        operation_id,
    )

    metadata_path = (
        directory
        / "metadata.json"
    )

    try:
        prepared = (
            PreparedNodeDelivery.model_validate(
                _read_small_json(
                    metadata_path
                )
            )
        )
    except Exception as exc:
        raise NodeDeliveryError(
            "Node delivery metadata is unavailable"
        ) from exc

    if (
        prepared.operation_id
        != operation_id
    ):
        raise NodeDeliveryError(
            "Node delivery operation identity mismatch"
        )

    return prepared
    
def discard_node_delivery(
    settings: UpdateCatalogSettings,
    operation_id: str,
) -> None:
    """Remove one Hub-side prepared delivery."""

    directory = _operation_directory(
        settings,
        operation_id,
    )

    if not directory.exists():
        return

    if directory.is_symlink():
        raise NodeDeliveryError(
            "Node delivery staging path is unsafe"
        )

    shutil.rmtree(directory)