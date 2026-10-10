"""Real bounded file socket, authentication, one-use and restart fencing."""

import base64
import os
from pathlib import Path
import tempfile
import uuid

import pytest

from three_mm_protocol.tests.test_application_private_files import file_request
from three_mm_runtime.application_file_executor import (
    ApplicationFileExecutor,
    call_file_executor,
)
from three_mm_runtime.application_transport import ApplicationTransportError


pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="POSIX worker, filesystem and clock"
)


@pytest.fixture
def runtime():
    with tempfile.TemporaryDirectory(prefix="3mm-worker-") as temporary:
        root = Path(temporary) / ("c" * 24)
        (root / "run").mkdir(parents=True)
        (root / "data").mkdir(mode=0o700)
        metadata = {
            "instance_id": "c" * 24,
            "sha256": "a" * 64,
            "storage": {
                "private_files": file_request(
                    max_file_bytes=8, max_total_bytes=12, max_files=2
                )
            },
        }
        yield root, metadata, b"s" * 32


def permit(hello):
    return {
        key: hello[key]
        for key in ("instance_id", "package_sha256", "runtime_nonce", "declaration")
    } | {"authority_epoch": "b" * 32, "deadline_ms": hello["clock_ms"] + 5000}


def put():
    return {
        "file_request_version": 1,
        "request_id": uuid.uuid4().hex,
        "operation": "put",
        "file_id": "logo",
        "expected_sha256": None,
        "content_base64": base64.b64encode(b"on").decode("ascii"),
    }


@pytest.mark.parametrize(
    "drift",
    [
        "runtime_nonce",
        "package_sha256",
        "instance_id",
        "authority_epoch",
        "deadline_ms",
        "bool_limit",
        "foreign_path",
    ],
)
def test_invalid_admission_refuses_before_opening_namespace(runtime, drift):
    root, metadata, secret = runtime
    with ApplicationFileExecutor(root, metadata, secret) as worker:
        hello = call_file_executor(worker.path, secret, "hello", {})
        admission = permit(hello)
        if drift == "bool_limit":
            admission["declaration"]["max_files"] = True
        elif drift == "foreign_path":
            admission["declaration"]["path"] = "/var/lib/3mm/core"
        elif drift == "deadline_ms":
            admission[drift] = hello["clock_ms"] - 1
        else:
            admission[drift] = "foreign"
        with pytest.raises(ApplicationTransportError):
            call_file_executor(
                worker.path,
                secret,
                "execute",
                {"admission": admission, "request": put()},
            )
        assert not (root / "data/sdk-files").exists()


def test_bad_key_and_consumed_permit_are_not_replayed(runtime):
    root, metadata, secret = runtime
    with ApplicationFileExecutor(root, metadata, secret) as worker:
        with pytest.raises(ApplicationTransportError):
            call_file_executor(worker.path, b"x" * 32, "hello", {})
        hello = call_file_executor(worker.path, secret, "hello", {})
        payload = {"admission": permit(hello), "request": put()}
        assert (
            call_file_executor(worker.path, secret, "execute", payload)["file"][
                "size_bytes"
            ]
            == 2
        )
        with pytest.raises(ApplicationTransportError):
            call_file_executor(worker.path, secret, "execute", payload)
    with ApplicationFileExecutor(root, metadata, secret) as worker:
        with pytest.raises(ApplicationTransportError):
            call_file_executor(worker.path, secret, "execute", payload)
        assert (root / "data/sdk-files/blob_logo").read_bytes() == b"on"


def test_read_only_executor_denies_forged_write_request(runtime):
    root, metadata, secret = runtime
    metadata["storage"]["private_files"]["mode"] = "read"
    with ApplicationFileExecutor(root, metadata, secret) as worker:
        hello = call_file_executor(worker.path, secret, "hello", {})
        with pytest.raises(ApplicationTransportError):
            call_file_executor(
                worker.path,
                secret,
                "execute",
                {"admission": permit(hello), "request": put()},
            )
        assert not (root / "data/sdk-files").exists()


def test_transport_ceiling_does_not_silently_clamp_declaration(runtime):
    root, metadata, secret = runtime
    metadata["storage"]["private_files"] = file_request(max_file_bytes=2 * 1024 * 1024)
    with pytest.raises(ValueError, match="scoped runtime limit"):
        ApplicationFileExecutor(root, metadata, secret)
    assert not (root / "run/files.sock").exists()


def test_one_mib_payload_uses_bounded_file_framing_without_changing_service_rpc(
    runtime,
):
    root, metadata, secret = runtime
    metadata["storage"]["private_files"] = file_request()
    content = b"x" * (1024 * 1024)
    value = {**put(), "content_base64": base64.b64encode(content).decode("ascii")}
    with ApplicationFileExecutor(root, metadata, secret) as worker:
        hello = call_file_executor(worker.path, secret, "hello", {})
        assert call_file_executor(
            worker.path,
            secret,
            "execute",
            {"admission": permit(hello), "request": value},
        )["file"]["size_bytes"] == len(content)
        read = {
            "file_request_version": 1,
            "request_id": uuid.uuid4().hex,
            "operation": "get",
            "file_id": "logo",
        }
        hello = call_file_executor(worker.path, secret, "hello", {})
        result = call_file_executor(
            worker.path,
            secret,
            "execute",
            {"admission": permit(hello), "request": read},
        )
        assert base64.b64decode(result["file"]["content_base64"]) == content
