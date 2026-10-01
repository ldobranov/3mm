"""Authenticated Hub-to-Node update artifact transport."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import uuid

import requests

from agent.node_update_client import (
    NodeUpdateClient,
    NodeUpdateHelperError,
)
from three_mm_protocol.node_updates import (
    NodeUpdatePrepareRequest,
    NodeUpdatePreparedArtifact,
)

CHUNK_SIZE = 1024 * 1024
CONNECT_TIMEOUT_SECONDS = 5
READ_TIMEOUT_SECONDS = 60


class NodeUpdateTransportError(RuntimeError):
    """Safe failure exposed to the Agent command layer."""


class NodeUpdateTransport:
    def __init__(
        self,
        *,
        core_url: str,
        device_id: str,
        headers: dict[str, str],
        data_dir: Path,
        helper: NodeUpdateClient | None = None,
    ) -> None:
        self.core_url = core_url.rstrip("/")
        self.device_id = device_id
        self.headers = dict(headers)
        self.data_dir = Path(data_dir)
        self.helper = helper or NodeUpdateClient()

    def _operation_directory(
        self,
        request: NodeUpdatePrepareRequest,
    ) -> Path:
        return (
            self.data_dir
            / "node-update-inbox"
            / request.operation_id
        )

    def _archive_path(
        self,
        request: NodeUpdatePrepareRequest,
    ) -> Path:
        return (
            self._operation_directory(request)
            / "release.tar.gz"
        )

    def _download_url(
        self,
        request: NodeUpdatePrepareRequest,
    ) -> str:
        return (
            f"{self.core_url}"
            f"/api/v1/devices/{self.device_id}"
            f"/node-updates/{request.operation_id}"
            f"/archive"
        )

    def _ensure_private_directory(
        self,
        path: Path,
    ) -> None:
        path.mkdir(
            parents=True,
            exist_ok=True,
            mode=0o700,
        )

        if os.name == "posix":
            os.chmod(
                path,
                0o700,
            )

    def _digest_existing(
        self,
        path: Path,
    ) -> tuple[str, int] | None:
        if not path.exists():
            return None

        try:
            info = path.lstat()

            if (
                not path.is_file()
                or path.is_symlink()
                or info.st_nlink != 1
                or info.st_size <= 0
            ):
                return None

            checksum = hashlib.sha256()
            size = 0

            flags = (
                os.O_RDONLY
                | getattr(
                    os,
                    "O_NOFOLLOW",
                    0,
                )
                | getattr(
                    os,
                    "O_BINARY",
                    0,
                )
            )

            descriptor = os.open(
                path,
                flags,
            )

            with os.fdopen(
                descriptor,
                "rb",
            ) as source:
                while True:
                    chunk = source.read(
                        CHUNK_SIZE
                    )

                    if not chunk:
                        break

                    size += len(chunk)

                    checksum.update(chunk)

            return (
                checksum.hexdigest(),
                size,
            )

        except OSError:
            return None

    def _existing_download_matches(
        self,
        request: NodeUpdatePrepareRequest,
    ) -> bool:
        identity = self._digest_existing(
            self._archive_path(request)
        )

        if identity is None:
            return False

        digest, size = identity

        return (
            digest
            == request.archive_sha256
            and size
            == request.archive_size_bytes
        )

    def _validate_response_headers(
        self,
        response,
        request: NodeUpdatePrepareRequest,
    ) -> None:
        if response.status_code != 200:
            raise NodeUpdateTransportError(
                "node_update_download_rejected"
            )

        if (
            response.headers.get(
                "X-3mm-Node-Operation"
            )
            != request.operation_id
        ):
            raise NodeUpdateTransportError(
                "node_update_operation_mismatch"
            )

        if (
            response.headers.get(
                "X-3mm-Node-Release"
            )
            != request.release_id
        ):
            raise NodeUpdateTransportError(
                "node_update_release_mismatch"
            )

        if (
            response.headers.get(
                "X-3mm-Node-SHA256"
            )
            != request.archive_sha256
        ):
            raise NodeUpdateTransportError(
                "node_update_checksum_identity_mismatch"
            )

        content_length = response.headers.get(
            "Content-Length"
        )

        try:
            declared_size = int(
                content_length
            )
        except (
            TypeError,
            ValueError,
        ) as exc:
            raise NodeUpdateTransportError(
                "node_update_size_missing"
            ) from exc

        if (
            declared_size
            != request.archive_size_bytes
        ):
            raise NodeUpdateTransportError(
                "node_update_size_mismatch"
            )

    def _download(
        self,
        request: NodeUpdatePrepareRequest,
    ) -> Path:
        operation_dir = (
            self._operation_directory(
                request
            )
        )

        inbox_root = (
            self.data_dir
            / "node-update-inbox"
        )

        self._ensure_private_directory(
            self.data_dir
        )

        self._ensure_private_directory(
            inbox_root
        )

        self._ensure_private_directory(
            operation_dir
        )

        target = (
            self._archive_path(
                request
            )
        )

        if self._existing_download_matches(
            request
        ):
            return target

        target.unlink(
            missing_ok=True
        )

        temporary = (
            operation_dir
            / (
                ".download-"
                + uuid.uuid4().hex
            )
        )

        flags = (
            os.O_CREAT
            | os.O_EXCL
            | os.O_WRONLY
            | getattr(
                os,
                "O_BINARY",
                0,
            )
        )

        descriptor = None

        try:
            response = requests.get(
                self._download_url(
                    request
                ),
                headers=self.headers,
                stream=True,
                timeout=(
                    CONNECT_TIMEOUT_SECONDS,
                    READ_TIMEOUT_SECONDS,
                ),
                allow_redirects=False,
            )

            try:
                self._validate_response_headers(
                    response,
                    request,
                )

                descriptor = os.open(
                    temporary,
                    flags,
                    0o600,
                )

                checksum = hashlib.sha256()
                received = 0

                with os.fdopen(
                    descriptor,
                    "wb",
                ) as destination:
                    descriptor = None

                    for chunk in response.iter_content(
                        chunk_size=CHUNK_SIZE
                    ):
                        if not chunk:
                            continue

                        received += len(chunk)

                        if (
                            received
                            > request.archive_size_bytes
                        ):
                            raise NodeUpdateTransportError(
                                "node_update_download_too_large"
                            )

                        checksum.update(chunk)
                        destination.write(chunk)

                    destination.flush()

                    os.fsync(
                        destination.fileno()
                    )

            finally:
                response.close()

            if (
                received
                != request.archive_size_bytes
            ):
                raise NodeUpdateTransportError(
                    "node_update_download_truncated"
                )

            if (
                checksum.hexdigest()
                != request.archive_sha256
            ):
                raise NodeUpdateTransportError(
                    "node_update_download_checksum_mismatch"
                )

            if os.name == "posix":
                os.chmod(
                    temporary,
                    0o600,
                )

            os.replace(
                temporary,
                target,
            )

            return target

        except requests.RequestException as exc:
            raise NodeUpdateTransportError(
                "node_update_download_failed"
            ) from exc

        except OSError as exc:
            raise NodeUpdateTransportError(
                "node_update_storage_failed"
            ) from exc

        finally:
            if descriptor is not None:
                try:
                    os.close(
                        descriptor
                    )
                except OSError:
                    pass

            temporary.unlink(
                missing_ok=True
            )

    def prepare(
        self,
        request: NodeUpdatePrepareRequest,
    ) -> NodeUpdatePreparedArtifact:
        if (
            request.device_id
            != self.device_id
        ):
            raise NodeUpdateTransportError(
                "node_update_device_mismatch"
            )

        self._download(
            request
        )

        try:
            prepared = self.helper.prepare(
                request
            )
        except NodeUpdateHelperError as exc:
            raise NodeUpdateTransportError(
                "node_update_prepare_failed"
            ) from exc

        if (
            prepared.operation_id
            != request.operation_id
            or prepared.device_id
            != request.device_id
            or prepared.release_id
            != request.release_id
            or prepared.archive_sha256
            != request.archive_sha256
            or prepared.archive_size_bytes
            != request.archive_size_bytes
        ):
            raise NodeUpdateTransportError(
                "node_update_prepared_identity_mismatch"
            )

        # Root owns its verified copy now.
        operation_dir = (
            self._operation_directory(
                request
            )
        )

        try:
            shutil.rmtree(
                operation_dir
            )
        except OSError:
            # Cleanup failure must not turn a successfully prepared
            # root-owned artifact into an update failure.
            pass

        return prepared