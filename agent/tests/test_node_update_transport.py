from datetime import UTC, datetime
import hashlib

import pytest

from agent.node_update_transport import (
    NodeUpdateTransport,
    NodeUpdateTransportError,
)
from three_mm_protocol.node_updates import (
    NodeUpdatePrepareRequest,
    NodeUpdatePreparedArtifact,
)


DEVICE_ID = (
    "dev_"
    + "a" * 32
)

OPERATION_ID = (
    "nodeupd_"
    + "b" * 32
)

RELEASE_ID = "v0.3.0-beta.25"


class FakeResponse:
    def __init__(
        self,
        *,
        data,
        headers,
        status_code=200,
    ):
        self.data = data
        self.headers = headers
        self.status_code = status_code
        self.closed = False

    def iter_content(
        self,
        chunk_size,
    ):
        assert chunk_size > 0

        midpoint = max(
            1,
            len(self.data) // 2,
        )

        yield self.data[:midpoint]
        yield self.data[midpoint:]

    def close(self):
        self.closed = True


class Helper:
    def __init__(self):
        self.requests = []

    def prepare(self, request):
        self.requests.append(
            request
        )

        return NodeUpdatePreparedArtifact(
            **request.model_dump(),
            prepared_at=datetime.now(UTC),
        )


def make_request(
    data=b"node-update-archive",
):
    return NodeUpdatePrepareRequest(
        operation_id=OPERATION_ID,
        device_id=DEVICE_ID,
        release_id=RELEASE_ID,
        archive_sha256=hashlib.sha256(
            data
        ).hexdigest(),
        archive_size_bytes=len(data),
    )


def response_headers(
    request,
):
    return {
        "Content-Length": str(
            request.archive_size_bytes
        ),
        "X-3mm-Node-Operation":
            request.operation_id,
        "X-3mm-Node-Release":
            request.release_id,
        "X-3mm-Node-SHA256":
            request.archive_sha256,
    }


def test_download_uses_bound_hub_device_auth_and_root_prepare(
    tmp_path,
    monkeypatch,
):
    data = b"node-update-archive"

    request = make_request(
        data
    )

    helper = Helper()

    captured = {}

    response = FakeResponse(
        data=data,
        headers=response_headers(
            request
        ),
    )

    def get(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)

        return response

    monkeypatch.setattr(
        "agent.node_update_transport.requests.get",
        get,
    )

    transport = NodeUpdateTransport(
        core_url="http://hub.local:8887/",
        device_id=DEVICE_ID,
        headers={
            "Authorization":
                "Device credential:secret",
        },
        data_dir=tmp_path / "agent",
        helper=helper,
    )

    prepared = transport.prepare(
        request
    )

    assert (
        captured["url"]
        == (
            "http://hub.local:8887"
            f"/api/v1/devices/{DEVICE_ID}"
            f"/node-updates/{OPERATION_ID}"
            "/archive"
        )
    )

    assert captured["headers"] == {
        "Authorization":
            "Device credential:secret",
    }

    assert captured["stream"] is True

    assert (
        captured["allow_redirects"]
        is False
    )

    assert captured["timeout"] == (
        5,
        60,
    )

    assert helper.requests == [
        request
    ]

    assert (
        prepared.operation_id
        == request.operation_id
    )

    assert response.closed is True

    assert not (
        tmp_path
        / "agent"
        / "node-update-inbox"
        / OPERATION_ID
    ).exists()


def test_device_mismatch_fails_before_network(
    tmp_path,
    monkeypatch,
):
    request = make_request().model_copy(
        update={
            "device_id":
                "dev_" + "c" * 32,
        }
    )

    monkeypatch.setattr(
        "agent.node_update_transport.requests.get",
        lambda *_args, **_kwargs:
            pytest.fail(
                "network used for wrong device"
            ),
    )

    transport = NodeUpdateTransport(
        core_url="http://hub.local",
        device_id=DEVICE_ID,
        headers={
            "Authorization":
                "Device credential:secret",
        },
        data_dir=tmp_path,
        helper=Helper(),
    )

    with pytest.raises(
        NodeUpdateTransportError,
        match="node_update_device_mismatch",
    ):
        transport.prepare(
            request
        )


@pytest.mark.parametrize(
    "header,value,error",
    [
        (
            "X-3mm-Node-Operation",
            "nodeupd_" + "d" * 32,
            "node_update_operation_mismatch",
        ),
        (
            "X-3mm-Node-Release",
            "v9.9.9",
            "node_update_release_mismatch",
        ),
        (
            "X-3mm-Node-SHA256",
            "0" * 64,
            "node_update_checksum_identity_mismatch",
        ),
        (
            "Content-Length",
            "999",
            "node_update_size_mismatch",
        ),
    ],
)
def test_response_identity_must_match_command(
    tmp_path,
    monkeypatch,
    header,
    value,
    error,
):
    data = b"node-update-archive"
    request = make_request(data)

    headers = response_headers(
        request
    )

    headers[header] = value

    response = FakeResponse(
        data=data,
        headers=headers,
    )

    monkeypatch.setattr(
        "agent.node_update_transport.requests.get",
        lambda *_args, **_kwargs:
            response,
    )

    helper = Helper()

    transport = NodeUpdateTransport(
        core_url="http://hub.local",
        device_id=DEVICE_ID,
        headers={
            "Authorization":
                "Device credential:secret",
        },
        data_dir=tmp_path,
        helper=helper,
    )

    with pytest.raises(
        NodeUpdateTransportError,
        match=error,
    ):
        transport.prepare(
            request
        )

    assert helper.requests == []


def test_body_checksum_is_verified_before_helper(
    tmp_path,
    monkeypatch,
):
    expected = b"correct-package"

    request = make_request(
        expected
    )

    response = FakeResponse(
        data=b"x" * len(expected),
        headers=response_headers(
            request
        ),
    )

    monkeypatch.setattr(
        "agent.node_update_transport.requests.get",
        lambda *_args, **_kwargs:
            response,
    )

    helper = Helper()

    transport = NodeUpdateTransport(
        core_url="http://hub.local",
        device_id=DEVICE_ID,
        headers={
            "Authorization":
                "Device credential:secret",
        },
        data_dir=tmp_path,
        helper=helper,
    )

    with pytest.raises(
        NodeUpdateTransportError,
        match=(
            "node_update_download_"
            "checksum_mismatch"
        ),
    ):
        transport.prepare(
            request
        )

    assert helper.requests == []