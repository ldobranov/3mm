"""Closed bounded file wire and host-selected SDK adapter; no live platform."""

import base64
import uuid

import pytest

from three_mm_application_sdk import (
    ApplicationFileExecutionUnconfirmed,
    ApplicationFileLimits,
    ApplicationFileStorageError,
    ApplicationScopedFileStorage,
)
from three_mm_application_sdk.file_wire import MAX_SCOPED_FILE_BYTES, parse_file_request


@pytest.mark.parametrize(
    "change",
    [
        {"file_request_version": True},
        {"request_id": ""},
        {"request_id": "a" * 31},
        {"file_id": "../foreign"},
        {"path": "/opt/3mm/current"},
        {"approved": True},
        {"operation": []},
        {"operation": "move"},
        {"expected_sha256": True},
        {"content_base64": "A==="},
        {
            "content_base64": base64.b64encode(
                b"x" * (MAX_SCOPED_FILE_BYTES + 1)
            ).decode()
        },
    ],
)
def test_wire_refuses_unknown_paths_grants_invalid_types_and_oversized_content(change):
    value = {
        "file_request_version": 1,
        "request_id": uuid.uuid4().hex,
        "operation": "put",
        "file_id": "logo",
        "expected_sha256": None,
        "content_base64": "eA==",
        **change,
    }
    with pytest.raises(ValueError):
        parse_file_request(value)


@pytest.mark.parametrize("reply", ["error", "malformed", "wrong_id", "unknown"])
def test_sdk_keeps_identity_and_uncertainty_without_retry(tmp_path, reply):
    calls = []

    class Platform:
        def _call(self, action, payload):
            calls.append((action, payload))
            if reply == "error":
                raise RuntimeError("connection lost")
            if reply == "malformed":
                return {}
            request = payload["file_request"]
            return {
                "receipt": {
                    "request_id": (
                        "0" * 32 if reply == "wrong_id" else request["request_id"]
                    ),
                    "operation": "put",
                    "file_id": "logo",
                    "outcome": "execution_unconfirmed",
                }
            }

    files = ApplicationScopedFileStorage(tmp_path, platform=Platform())
    identifier = uuid.uuid4().hex
    with pytest.raises(ApplicationFileExecutionUnconfirmed) as error:
        files.put("logo", b"x", expected_sha256=None, request_id=identifier)
    assert error.value.request_id == identifier and len(calls) == 1
    assert list(tmp_path.iterdir()) == []


def test_scoped_read_only_and_local_bounds_refuse_before_platform(tmp_path):
    class Platform:
        def _call(self, *args):
            pytest.fail("Invalid local operation reached platform")

    read = ApplicationScopedFileStorage(tmp_path, mode="read", platform=Platform())
    with pytest.raises(ApplicationFileStorageError, match="read-only"):
        read.put("logo", b"x", expected_sha256=None)
    with pytest.raises(ApplicationFileStorageError, match="read-only"):
        read.delete("logo", expected_sha256="a" * 64)
    write = ApplicationScopedFileStorage(
        tmp_path, limits=ApplicationFileLimits(1, 1, 1), platform=Platform()
    )
    with pytest.raises(ApplicationFileStorageError):
        write.put("logo", b"xx", expected_sha256=None)
    assert list(tmp_path.iterdir()) == []
