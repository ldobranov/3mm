import hashlib
from types import SimpleNamespace

import pytest

from backend.config import UpdateCatalogSettings
from backend.routes.node_update_delivery import (
    download_node_update_archive,
    router,
)
from backend.services.node_update_delivery import (
    stage_node_delivery,
)
from backend.utils.device_auth import require_device


DEVICE_A = "dev_" + "a" * 32
DEVICE_B = "dev_" + "b" * 32
OPERATION = "nodeupd_" + "c" * 32


def make_settings(tmp_path):
    return UpdateCatalogSettings(
        staging_dir=tmp_path / "staging",
        minimum_free_bytes=64 * 1024 * 1024,
        max_artifact_bytes=1024 * 1024,
    )


def make_device(device_id):
    return SimpleNamespace(
        device_id=device_id,
    )


def prepare(tmp_path):
    settings = make_settings(tmp_path)

    data = b"authenticated-node-update"

    source = tmp_path / "release.tar.gz"
    source.write_bytes(data)

    sha256 = hashlib.sha256(
        data
    ).hexdigest()

    stage_node_delivery(
        settings,
        operation_id=OPERATION,
        device_id=DEVICE_A,
        release_id="v0.3.0-beta.25",
        archive_sha256=sha256,
        archive_size_bytes=len(data),
        source_path=source,
    )

    return settings, data, sha256


def test_paired_device_downloads_only_its_own_archive(
    tmp_path,
):
    settings, data, sha256 = prepare(
        tmp_path
    )

    response = download_node_update_archive(
        DEVICE_A,
        OPERATION,
        device=make_device(DEVICE_A),
        settings=settings,
    )

    assert response.status_code == 200

    assert (
        response.headers[
            "x-3mm-node-operation"
        ]
        == OPERATION
    )

    assert (
        response.headers[
            "x-3mm-node-release"
        ]
        == "v0.3.0-beta.25"
    )

    assert (
        response.headers[
            "x-3mm-node-sha256"
        ]
        == sha256
    )

    assert (
        response.headers[
            "content-length"
        ]
        == str(len(data))
    )


def test_route_rejects_path_identity_mismatch(
    tmp_path,
):
    settings, _, _ = prepare(
        tmp_path
    )

    with pytest.raises(Exception) as error:
        download_node_update_archive(
            DEVICE_A,
            OPERATION,
            device=make_device(
                DEVICE_B
            ),
            settings=settings,
        )

    assert (
        getattr(
            error.value,
            "status_code",
            None,
        )
        == 403
    )


def test_other_paired_device_cannot_probe_operation(
    tmp_path,
):
    settings, _, _ = prepare(
        tmp_path
    )

    with pytest.raises(Exception) as error:
        download_node_update_archive(
            DEVICE_B,
            OPERATION,
            device=make_device(
                DEVICE_B
            ),
            settings=settings,
        )

    assert (
        getattr(
            error.value,
            "status_code",
            None,
        )
        == 404
    )


def test_router_uses_device_authentication():
    dependant = None

    for route in router.routes:
        if (
            getattr(
                route,
                "endpoint",
                None,
            )
            is download_node_update_archive
        ):
            dependant = route.dependant
            break

    assert dependant is not None

    dependencies = [
        item.call
        for item in dependant.dependencies
    ]

    assert require_device in dependencies