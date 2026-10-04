from datetime import UTC, datetime, timedelta
import json
import os

import pytest
import requests

from agent.core_client import (
    CommandJournal,
    DeviceCredentialStore,
    OutboxEntry,
    OutboxStore,
)
from agent.tests.test_runtime_features import publisher
from three_mm_protocol import AgentCommand, AgentCommandResult


def command(**changes):
    now = datetime.now(UTC)
    return AgentCommand(
        **(
            {
                "device_id": "dev_" + "1" * 32,
                "command_id": "cmd_" + "2" * 32,
                "command_type": "agent.refresh_inventory",
                "payload": {},
                "idempotency_key": "one",
                "created_at": now,
                "expires_at": now + timedelta(seconds=60),
            }
            | changes
        )
    )


def test_receipt_content_binding_survives_restart_and_refuses_changed_content(tmp_path):
    journal = CommandJournal(tmp_path)
    request = command()
    result = AgentCommandResult(
        command_id=request.command_id,
        device_id=request.device_id,
        status="succeeded",
        completed_at=datetime.now(UTC),
        output={"done": True},
    )
    journal.save(request.idempotency_key, result, command=request)
    journal = CommandJournal(tmp_path)
    assert journal.get_for_command(request) == result
    altered = request.model_copy(update={"payload": {"value": True}})
    assert journal.get_for_command(altered).output["execution_state"] == "conflict"
    # A crash/tamper leaving a mismatched result/proof cannot fabricate success.
    raw = json.loads(journal.path.read_text())
    raw["one"]["output"] = {"done": "changed"}
    journal.path.write_text(json.dumps(raw))
    assert CommandJournal(tmp_path).get_for_command(request).status == "failed"


def test_legacy_unbound_receipt_is_preserved_but_not_replayed(tmp_path):
    journal = CommandJournal(tmp_path)
    request = command()
    result = AgentCommandResult(
        command_id=request.command_id,
        device_id=request.device_id,
        status="succeeded",
        completed_at=datetime.now(UTC),
    )
    journal.save(request.idempotency_key, result)
    assert (
        journal.get(request.idempotency_key) == result
    )  # Old format remains readable.
    assert journal.get_for_command(request).output["execution_state"] == "unknown"


def test_outbox_overflow_never_evicts_pending_results(tmp_path):
    outbox = OutboxStore(tmp_path)
    entries = [
        OutboxEntry(suffix="events", payload={"i": i}, deduplication_key=str(i))
        for i in range(500)
    ]
    outbox.save(entries)
    with pytest.raises(RuntimeError, match="preserved"):
        outbox.enqueue(
            OutboxEntry(suffix="events", payload={}, deduplication_key="new")
        )
    assert outbox.load() == entries
    replacement = entries[0].model_copy(update={"payload": {"replacement": True}})
    outbox.enqueue(replacement)
    assert len(outbox.load()) == 500 and outbox.load()[-1] == replacement


def test_redirect_is_not_an_ack_and_credentials_are_not_forwarded(
    monkeypatch, tmp_path
):
    node = publisher(tmp_path)

    def redirect(*args, **kwargs):
        assert kwargs["allow_redirects"] is False
        result = requests.Response()
        result.status_code = 302
        return result

    monkeypatch.setattr("agent.core_client.requests.post", redirect)
    payload = {"event_id": "evt_" + "a" * 32, "device_id": node.credential.device_id,
        "event_type": "test.event", "occurred_at": datetime.now(UTC).isoformat(), "payload": {"sample": True}}
    assert node._send_or_queue("events", payload, "redirected") is False
    assert node.outbox.load()[0].deduplication_key == "redirected"


def test_linux_credential_and_proof_storage_is_private(tmp_path):
    if os.name != "posix":
        pytest.skip("POSIX access modes require the deployed Linux host")
    node = publisher(tmp_path)
    store = DeviceCredentialStore(tmp_path)
    store.save(node.credential)
    store.path.chmod(0o644)
    assert store.load() == node.credential
    assert store.path.stat().st_mode & 0o777 == 0o600
    target = tmp_path / "foreign.json"
    store.path.rename(target)
    store.path.symlink_to(target)
    with pytest.raises(RuntimeError, match="symbolic"):
        store.load()
