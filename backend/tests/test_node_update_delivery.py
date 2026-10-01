from datetime import UTC, datetime, timedelta
import hashlib
from pathlib import Path

import pytest

from backend.config import UpdateCatalogSettings
from backend.services.node_update_delivery import (
    NodeDeliveryError,
    open_node_delivery,
    stage_node_delivery,
)


def settings(tmp_path):
    return UpdateCatalogSettings(
        staging_dir=tmp_path / "staging",
        minimum_free_bytes=64 * 1024 * 1024,
        max_artifact_bytes=1024 * 1024,
    )


def test_prepared_delivery_is_device_scoped_and_verified(
    tmp_path,
):
    config = settings(tmp_path)

    data = b"node-update-release"
    source = tmp_path / "source.tar.gz"
    source.write_bytes(data)

    operation_id = (
        "nodeupd_"
        + "1" * 32
    )

    device_id = (
        "dev_"
        + "2" * 32
    )

    checksum = hashlib.sha256(
        data
    ).hexdigest()

    prepared = stage_node_delivery(
        config,
        operation_id=operation_id,
        device_id=device_id,
        release_id="v0.3.0-beta.25",
        archive_sha256=checksum,
        archive_size_bytes=len(data),
        source_path=source,
    )

    resolved, archive = open_node_delivery(
        config,
        operation_id=operation_id,
        device_id=device_id,
    )

    assert resolved == prepared
    assert archive.read_bytes() == data

    with pytest.raises(
        NodeDeliveryError,
        match="another device",
    ):
        open_node_delivery(
            config,
            operation_id=operation_id,
            device_id="dev_" + "3" * 32,
        )


def test_delivery_rejects_bad_digest_and_expiry(
    tmp_path,
):
    config = settings(tmp_path)

    data = b"node-update-release"
    source = tmp_path / "source.tar.gz"
    source.write_bytes(data)

    operation_id = (
        "nodeupd_"
        + "4" * 32
    )

    device_id = (
        "dev_"
        + "5" * 32
    )

    checksum = hashlib.sha256(
        data
    ).hexdigest()

    with pytest.raises(
        NodeDeliveryError,
        match="identity mismatch",
    ):
        stage_node_delivery(
            config,
            operation_id=operation_id,
            device_id=device_id,
            release_id="v0.3.0-beta.25",
            archive_sha256="0" * 64,
            archive_size_bytes=len(data),
            source_path=source,
        )

    prepared = stage_node_delivery(
        config,
        operation_id=operation_id,
        device_id=device_id,
        release_id="v0.3.0-beta.25",
        archive_sha256=checksum,
        archive_size_bytes=len(data),
        source_path=source,
    )

    with pytest.raises(
        NodeDeliveryError,
        match="expired",
    ):
        open_node_delivery(
            config,
            operation_id=operation_id,
            device_id=device_id,
            now=prepared.expires_at
            + timedelta(seconds=1),
        )


def test_delivery_replay_is_idempotent(
    tmp_path,
):
    config = settings(tmp_path)

    data = b"same-release"
    source = tmp_path / "source.tar.gz"
    source.write_bytes(data)

    checksum = hashlib.sha256(
        data
    ).hexdigest()

    arguments = dict(
        operation_id=(
            "nodeupd_"
            + "6" * 32
        ),
        device_id=(
            "dev_"
            + "7" * 32
        ),
        release_id="v0.3.0-beta.25",
        archive_sha256=checksum,
        archive_size_bytes=len(data),
        source_path=source,
    )

    first = stage_node_delivery(
        config,
        **arguments,
    )

    second = stage_node_delivery(
        config,
        **arguments,
    )

    assert second.operation_id == first.operation_id
    assert second.archive_sha256 == first.archive_sha256