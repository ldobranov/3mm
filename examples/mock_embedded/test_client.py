"""Durable mock execution; these effects are SQLite state, never real GPIO."""

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
import requests

from examples.mock_embedded.client import CAPABILITY, CHANNEL, MockEmbeddedClient
from three_mm_protocol import AgentCommand


def command(node, **changes):
    now = datetime.now(UTC)
    values = dict(
        device_id=node.device_id,
        command_id=f"cmd_{uuid4().hex}",
        command_type="capability.invoke",
        idempotency_key=uuid4().hex,
        created_at=now,
        expires_at=now + timedelta(minutes=1),
        payload={
            "capability_id": CAPABILITY,
            "action": "set_output",
            "arguments": {"channel": CHANNEL, "value": True},
        },
    )
    return AgentCommand(**(values | changes))


def enabled_node(path):
    node = MockEmbeddedClient("http://core.test:8887", path)
    with node.db:
        node._set("enabled", True)
    return node


def test_identity_mock_effect_and_receipt_survive_restart(tmp_path):
    node = enabled_node(tmp_path)
    identity = node.identity.copy()
    request = command(node)
    first = node.execute(request)
    assert first.status == "succeeded"
    assert node.execute(request) == first
    assert node.executions == 1 and node.output is True and node.pending_count == 3
    node.close()
    node = enabled_node(tmp_path)
    try:
        assert node.identity == identity
        assert node.execute(request) == first
        assert node.executions == 1 and node.pending_count == 3
        modified = request.model_copy(
            update={
                "payload": request.payload
                | {"arguments": {"channel": CHANNEL, "value": False}}
            }
        )
        with pytest.raises(ValueError, match="different content"):
            node.execute(modified)
        with pytest.raises(ValueError, match="different content"):
            node.execute(request.model_copy(update={"idempotency_key": "changed"}))
        with pytest.raises(ValueError, match="different content"):
            node.execute(
                request.model_copy(update={"command_id": f"cmd_{uuid4().hex}"})
            )
        assert node.executions == 1 and node.output is True
    finally:
        node.close()


@pytest.mark.parametrize(
    "kind",
    [
        "expired",
        "disabled",
        "invalid",
        "module.install",
        "agent.update.apply",
        "application.capability.invoke",
    ],
)
def test_unsupported_expired_or_disabled_requests_never_act(tmp_path, kind):
    node = enabled_node(tmp_path)
    try:
        changes = {}
        if kind == "expired":
            changes["created_at"] = datetime.now(UTC) - timedelta(minutes=1)
            changes["expires_at"] = datetime.now(UTC) - timedelta(seconds=1)
        elif kind == "disabled":
            with node.db:
                node._set("enabled", False)
        elif kind == "invalid":
            changes["payload"] = {
                "capability_id": CAPABILITY,
                "action": "set_output",
                "arguments": {"channel": CHANNEL, "value": 1},
            }
        else:
            changes["command_type"] = kind
        result = node.execute(command(node, **changes))
        assert (
            result.status == "failed"
            and result.output["execution_state"] == "not_executed"
        )
        assert node.executions == 0 and node.output is False
        assert node.pending_count == 1  # Failure receipt only, no event/state effect.
        with pytest.raises(ValueError, match="identity"):
            node.execute(command(node, device_id=f"dev_{uuid4().hex}"))
    finally:
        node.close()


def test_full_outbox_rolls_back_mock_effect_and_receipt(tmp_path):
    node = enabled_node(tmp_path)
    try:
        with node.db:
            for i in range(128):
                node._enqueue(f"event:{i}", "/events", {"test": i})
        with pytest.raises(ValueError, match="capacity"):
            node.execute(command(node))
        assert node.executions == 0 and node.output is False
        assert node.db.execute("SELECT count(*) FROM receipts").fetchone()[0] == 0
        assert node.pending_count == 128
    finally:
        node.close()


def test_identity_cannot_silently_move_to_another_core(tmp_path):
    node = enabled_node(tmp_path)
    identity = node.identity.copy()
    node.close()
    with pytest.raises(ValueError, match="different Core"):
        MockEmbeddedClient("http://other.test:8887", tmp_path)
    node = enabled_node(tmp_path)
    assert node.identity == identity
    node.close()


def test_runtime_has_no_agent_backend_or_fleet_imports():
    for filename in ("client.py", "__main__.py"):
        tree = ast.parse(Path(__file__).with_name(filename).read_text(encoding="utf-8"))
        for item in ast.walk(tree):
            names = (
                [alias.name for alias in item.names]
                if isinstance(item, ast.Import)
                else [item.module] if isinstance(item, ast.ImportFrom) else []
            )
            assert not any(
                name and name.split(".")[0] in {"agent", "backend", "fleet"}
                for name in names
            )


class PermitTransport:
    def __init__(self, command_id, fault=None):
        self.command_id = command_id
        self.fault = fault
        self.calls = 0

    def request(self, method, url, **kwargs):
        self.calls += 1
        assert method == "POST" and url.endswith(
            f"/commands/{self.command_id}/authorize-execution"
        )
        assert kwargs["timeout"] == 2 and kwargs["allow_redirects"] is False
        if self.fault == "lost_reply":
            raise requests.ConnectionError("Lost permit acknowledgement")
        if self.fault == "crash":
            raise KeyboardInterrupt()
        response = requests.Response()
        response.status_code = 409 if self.fault == "denied" else 200
        import json

        response._content = json.dumps(
            {
                "authorized": True,
                "command_id": self.command_id if self.fault != "identity" else "other",
            }
        ).encode()
        return response


def application_command(node):
    now = datetime.now(UTC)
    return command(
        node,
        command_type="application.capability.invoke",
        created_at=now,
        expires_at=now + timedelta(seconds=10),
    )


@pytest.mark.parametrize("fault", [None, "denied", "lost_reply", "identity", "late"])
def test_application_permit_is_prompt_identity_bound_and_never_retried(
    tmp_path, monkeypatch, fault
):
    node = enabled_node(tmp_path)
    request = application_command(node)
    transport = PermitTransport(request.command_id, fault)
    node.transport = transport
    if fault == "late":
        times = iter([0, 3])
        monkeypatch.setattr(
            "examples.mock_embedded.client.time.monotonic", lambda: next(times)
        )
    try:
        result = node.execute(request)
        assert result.status == ("succeeded" if fault is None else "failed")
        assert result.output["execution_state"] == (
            "executed" if fault is None else "not_executed"
        )
        assert node.executions == (1 if fault is None else 0)
        assert node.execute(request) == result and transport.calls == 1
    finally:
        node.close()


def test_crash_during_permit_leaves_durable_uncertainty_not_replay_permission(tmp_path):
    node = enabled_node(tmp_path)
    request = application_command(node)
    transport = PermitTransport(request.command_id, "crash")
    node.transport = transport
    with pytest.raises(KeyboardInterrupt):
        node.execute(request)
    node.close()
    node = enabled_node(tmp_path)
    node.transport = transport
    try:
        result = node.execute(request)
        assert result.output["execution_state"] == "unknown"
        assert node.executions == 0 and transport.calls == 1
        assert node.pending_count == 1
    finally:
        node.close()


def test_outbox_overflow_after_permit_never_replays_attempt(tmp_path):
    node = enabled_node(tmp_path)
    request = application_command(node)
    transport = PermitTransport(request.command_id)
    node.transport = transport
    try:
        with node.db:
            for i in range(128):
                node._enqueue(f"event:{i}", "/events", {"test": i})
        with pytest.raises(ValueError, match="capacity"):
            node.execute(request)
        assert node.executions == 0 and node.output is False and transport.calls == 1
        with node.db:
            node.db.execute("DELETE FROM outbox WHERE key='event:0'")
        assert node.execute(request).output["execution_state"] == "unknown"
        assert node.executions == 0 and transport.calls == 1
    finally:
        node.close()


def test_deadline_is_rechecked_after_permit_before_simulated_effect(
    tmp_path, monkeypatch
):
    node = enabled_node(tmp_path)
    request = application_command(node)
    transport = PermitTransport(request.command_id)
    node.transport = transport

    class Clock:
        calls = 0

        @classmethod
        def now(cls, timezone):
            cls.calls += 1
            return request.created_at if cls.calls == 1 else request.expires_at

    monkeypatch.setattr("examples.mock_embedded.client.datetime", Clock)
    try:
        result = node.execute(request)
        assert result.output["execution_state"] == "not_executed"
        assert node.executions == 0 and transport.calls == 1
    finally:
        node.close()
