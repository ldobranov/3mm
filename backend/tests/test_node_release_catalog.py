import pytest

from backend.config import (
    UpdateCatalogSettings,
)
from backend.services.node_release_catalog import (
    NodeReleaseCatalogError,
    find_published_node_release,
)


TAG = "v0.3.0-beta.25"

ARCHIVE = (
    "3mm-0.3.0-beta.25-"
    "node-armv6l.tar.gz"
)

SHA = "a" * 64

REPOSITORY = "ldobranov/3mm"


def settings(tmp_path):
    return UpdateCatalogSettings(
        repository=REPOSITORY,
        staging_dir=tmp_path,
        minimum_free_bytes=(
            64 * 1024 * 1024
        ),
        max_artifact_bytes=(
            512 * 1024 * 1024
        ),
    )


def manifest():
    return {
        "schema_version": 1,
        "profile": "node",
        "version": "0.3.0-beta.25",
        "release_id": TAG,
        "commit": "b" * 40,
        "channel": "beta",
        "dependencies": {
            "apt_packages": [],
        },
        "artifacts": [
            {
                "architecture":
                    "armv6l",
                "python":
                    "3.13",
                "filename":
                    ARCHIVE,
                "sha256":
                    SHA,
                "size_bytes":
                    123456,
                "download_url": (
                    "https://github.com/"
                    f"{REPOSITORY}"
                    f"/releases/download/{TAG}/"
                    f"{ARCHIVE}"
                ),
            }
        ],
    }


def release():
    return {
        "tag_name": TAG,
        "name": TAG,
        "draft": False,
        "prerelease": True,
        "assets": [
            {
                "name":
                    "3mm-node-manifest.json",
                "browser_download_url": (
                    "https://github.com/"
                    f"{REPOSITORY}"
                    f"/releases/download/{TAG}/"
                    "3mm-node-manifest.json"
                ),
                "size":
                    1000,
            },
            {
                "name":
                    ARCHIVE,
                "browser_download_url": (
                    "https://github.com/"
                    f"{REPOSITORY}"
                    f"/releases/download/{TAG}/"
                    f"{ARCHIVE}"
                ),
                "size":
                    123456,
                "digest":
                    f"sha256:{SHA}",
            },
        ],
    }


def test_valid_official_armv6_node_release(
    tmp_path,
):
    def fetch(url, _timeout):
        if url.endswith(
            "3mm-node-manifest.json"
        ):
            return manifest()

        return [
            release()
        ]

    result = find_published_node_release(
        settings(tmp_path),
        channel="beta",
        fetch_json=fetch,
    )

    assert result.tag == TAG

    assert (
        result.artifact.architecture
        == "armv6l"
    )

    assert (
        result.artifact.python
        == "3.13"
    )

    assert (
        result.artifact.sha256
        == SHA
    )


def test_manifest_cannot_redirect_node_to_other_host(
    tmp_path,
):
    bad = manifest()

    bad["artifacts"][0][
        "download_url"
    ] = (
        "https://evil.example/"
        "release.tar.gz"
    )

    def fetch(url, _timeout):
        if url.endswith(
            "3mm-node-manifest.json"
        ):
            return bad

        return [
            release()
        ]

    with pytest.raises(
        NodeReleaseCatalogError
    ):
        find_published_node_release(
            settings(tmp_path),
            channel="beta",
            fetch_json=fetch,
        )


def test_manifest_and_github_asset_identity_must_match(
    tmp_path,
):
    bad_release = release()

    bad_release["assets"][1][
        "size"
    ] = 999

    def fetch(url, _timeout):
        if url.endswith(
            "3mm-node-manifest.json"
        ):
            return manifest()

        return [
            bad_release
        ]

    with pytest.raises(
        NodeReleaseCatalogError,
        match="size",
    ):
        find_published_node_release(
            settings(tmp_path),
            channel="beta",
            fetch_json=fetch,
        )


def test_wrong_profile_or_architecture_is_rejected(
    tmp_path,
):
    bad = manifest()

    bad["profile"] = "full"

    def fetch(url, _timeout):
        if url.endswith(
            "3mm-node-manifest.json"
        ):
            return bad

        return [
            release()
        ]

    with pytest.raises(
        NodeReleaseCatalogError,
        match="manifest",
    ):
        find_published_node_release(
            settings(tmp_path),
            channel="beta",
            fetch_json=fetch,
        )
        
        
class FakeDownload:
    def __init__(
        self,
        data,
        *,
        url,
        content_length=None,
    ):
        self.data = data
        self.url = url
        self.offset = 0
        self.headers = {}

        if content_length is not None:
            self.headers[
                "Content-Length"
            ] = str(content_length)

    def __enter__(self):
        return self

    def __exit__(
        self,
        *_args,
    ):
        return False

    def geturl(self):
        return self.url

    def read(self, count):
        if (
            self.offset
            >= len(self.data)
        ):
            return b""

        chunk = self.data[
            self.offset:
            self.offset + count
        ]

        self.offset += len(
            chunk
        )

        return chunk


def test_node_archive_download_verifies_body(
    tmp_path,
):
    import hashlib

    from backend.services.node_release_catalog import (
        PublishedNodeRelease,
        NodeReleaseManifest,
        download_published_node_archive,
    )

    data = b"official-node-archive"

    checksum = hashlib.sha256(
        data
    ).hexdigest()

    payload = manifest()

    payload["artifacts"][0][
        "sha256"
    ] = checksum

    payload["artifacts"][0][
        "size_bytes"
    ] = len(data)

    release_data = PublishedNodeRelease(
        tag=TAG,
        manifest=(
            NodeReleaseManifest.model_validate(
                payload
            )
        ),
        artifact=(
            NodeReleaseManifest.model_validate(
                payload
            ).artifacts[0]
        ),
    )

    redirected_url = (
        "https://release-assets."
        "githubusercontent.com/"
        "asset"
    )

    def opener(
        _request,
        timeout,
    ):
        assert timeout > 0

        return FakeDownload(
            data,
            url=redirected_url,
            content_length=len(data),
        )

    destination = (
        tmp_path
        / "release.tar.gz"
    )

    result = (
        download_published_node_archive(
            release_data,
            destination,
            settings(tmp_path),
            opener=opener,
        )
    )

    assert result == destination
    assert destination.read_bytes() == data


def test_node_archive_download_rejects_untrusted_redirect(
    tmp_path,
):
    import hashlib

    from backend.services.node_release_catalog import (
        PublishedNodeRelease,
        NodeReleaseManifest,
        download_published_node_archive,
    )

    data = b"official-node-archive"

    payload = manifest()

    payload["artifacts"][0][
        "sha256"
    ] = hashlib.sha256(
        data
    ).hexdigest()

    payload["artifacts"][0][
        "size_bytes"
    ] = len(data)

    validated = (
        NodeReleaseManifest.model_validate(
            payload
        )
    )

    release_data = PublishedNodeRelease(
        tag=TAG,
        manifest=validated,
        artifact=validated.artifacts[0],
    )

    destination = (
        tmp_path
        / "release.tar.gz"
    )

    with pytest.raises(
        NodeReleaseCatalogError,
        match="redirect",
    ):
        download_published_node_archive(
            release_data,
            destination,
            settings(tmp_path),
            opener=lambda *_args, **_kwargs:
                FakeDownload(
                    data,
                    url=(
                        "https://evil.example/"
                        "archive.tar.gz"
                    ),
                    content_length=len(data),
                ),
        )

    assert not destination.exists()


def test_node_archive_download_rejects_wrong_checksum(
    tmp_path,
):
    from backend.services.node_release_catalog import (
        PublishedNodeRelease,
        NodeReleaseManifest,
        download_published_node_archive,
    )

    payload = manifest()

    payload["artifacts"][0][
        "size_bytes"
    ] = 4

    validated = (
        NodeReleaseManifest.model_validate(
            payload
        )
    )

    release_data = PublishedNodeRelease(
        tag=TAG,
        manifest=validated,
        artifact=validated.artifacts[0],
    )

    destination = (
        tmp_path
        / "release.tar.gz"
    )

    with pytest.raises(
        NodeReleaseCatalogError,
        match="checksum",
    ):
        download_published_node_archive(
            release_data,
            destination,
            settings(tmp_path),
            opener=lambda *_args, **_kwargs:
                FakeDownload(
                    b"FAIL",
                    url=(
                        "https://objects."
                        "githubusercontent.com/"
                        "asset"
                    ),
                    content_length=4,
                ),
        )

    assert not destination.exists()