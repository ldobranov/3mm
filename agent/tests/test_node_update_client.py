from datetime import UTC, datetime, timedelta

import pytest

from agent.node_update_client import NodeUpdateClient, NodeUpdateHelperError
from three_mm_protocol.node_updates import NodeUpdateApplyRequest, NodeUpdateOperation


def test_node_update_client_does_not_call_installer_and_checks_identity(monkeypatch):
    now = datetime.now(UTC)
    request = NodeUpdateApplyRequest(
        operation_id="nodeupd_" + "a" * 32, device_id="dev_" + "b" * 32,
        release_id="v0.3.0-beta.25", archive_sha256="c" * 64,
        confirmed_install=True, created_at=now, expires_at=now + timedelta(seconds=30),
    )
    operation = NodeUpdateOperation(
        **request.model_dump(exclude={"confirmed_install", "created_at", "expires_at"}),
        status="accepted", updated_at=now,
    )
    sent = []
    client = NodeUpdateClient()
    monkeypatch.setattr(client, "_request", lambda payload: sent.append(payload) or operation)
    assert client.apply(request).status == "accepted"  # Not completed installation.
    assert sent[0]["action"] == "apply"
    assert sent[0]["request"]["expires_at"] == request.model_dump(mode="json")["expires_at"]
    monkeypatch.setattr(client, "_request", lambda _: operation.model_copy(update={"device_id": "dev_" + "e" * 32}))
    with pytest.raises(NodeUpdateHelperError, match="invalid_helper_operation"):
        client.apply(request)


def test_missing_helper_does_not_claim_success(tmp_path):
    with pytest.raises(NodeUpdateHelperError):
        NodeUpdateClient(tmp_path / "missing.sock").status()


def test_prepare_checks_root_prepared_identity(monkeypatch):
    now = datetime.now(UTC)

    from three_mm_protocol.node_updates import (
        NodeUpdatePrepareRequest,
        NodeUpdatePreparedArtifact,
    )

    request = NodeUpdatePrepareRequest(
        operation_id="nodeupd_" + "1" * 32,
        device_id="dev_" + "2" * 32,
        release_id="v0.3.0-beta.25",
        archive_sha256="3" * 64,
        archive_size_bytes=123456,
    )

    prepared = NodeUpdatePreparedArtifact(
        **request.model_dump(),
        prepared_at=now,
    )

    client = NodeUpdateClient()

    monkeypatch.setattr(
        client,
        "_exchange",
        lambda payload: {
            "ok": True,
            "prepared": prepared.model_dump(mode="json"),
        },
    )

    assert client.prepare(request) == prepared

    wrong = prepared.model_copy(
        update={"archive_sha256": "4" * 64}
    )

    monkeypatch.setattr(
        client,
        "_exchange",
        lambda payload: {
            "ok": True,
            "prepared": wrong.model_dump(mode="json"),
        },
    )

    with pytest.raises(
        NodeUpdateHelperError,
        match="invalid_helper_prepared_artifact",
    ):
        client.prepare(request)