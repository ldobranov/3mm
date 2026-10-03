"""C8 persistent-file and old-Core wire compatibility, no live host changes."""

import json
from datetime import UTC, datetime

import pytest

from agent.core_client import CommandJournal, DeviceCredentialStore, ReconciliationState
from agent.tests.test_node_security import command
from agent.tests.test_runtime_features import publisher, response
from three_mm_protocol import AgentCommandResult, AgentInventory
from three_mm_protocol.node_security import NODE_MESSAGE_BYTES


def test_invalid_historical_receipt_is_not_a_cache_miss_or_global_startup_failure(
    tmp_path, monkeypatch
):
    request = command()
    raw = AgentCommandResult(
        command_id=request.command_id,
        device_id=request.device_id,
        status="succeeded",
        completed_at=datetime.now(UTC),
    ).model_dump(mode="json")
    raw["output"] = {"large": "x" * NODE_MESSAGE_BYTES}
    path = tmp_path / "command-journal.json"
    path.write_text(json.dumps({"one": raw}), encoding="utf-8")
    journal = CommandJournal(tmp_path)
    assert journal.get_for_command(request).output == {
        "execution_state": "unknown",
        "recovery_code": "legacy_receipt_invalid",
    }
    result = AgentCommandResult(
        command_id="cmd_" + "3" * 32,
        device_id=request.device_id,
        status="succeeded",
        completed_at=datetime.now(UTC),
    )
    with pytest.raises(RuntimeError, match="overwritten"):
        journal.save("one", result)
    journal.save("different", result)
    assert json.loads(path.read_text())["one"] == raw
    reloaded = CommandJournal(tmp_path)
    assert reloaded.get("different") == result
    assert reloaded.get_for_command(request).status == "failed"
    node = publisher(tmp_path)
    monkeypatch.setattr(
        "agent.core_client.requests.get",
        lambda *a, **k: response(200, request.model_dump(mode="json")),
    )
    monkeypatch.setattr(
        type(node),
        "_publish_inventory",
        lambda *_: pytest.fail("Historical action must not run again"),
    )
    submitted = []
    monkeypatch.setattr(
        type(node), "_submit_result", lambda self, item: submitted.append(item)
    )
    node._poll_command()
    assert submitted[0].output["execution_state"] == "unknown"
    assert json.loads(path.read_text())["one"] == raw


def test_rollback_receipt_write_invalidates_proof_without_replaying(tmp_path):
    request = command()
    result = AgentCommandResult(
        command_id=request.command_id,
        device_id=request.device_id,
        status="succeeded",
        completed_at=datetime.now(UTC),
        output={"revision": 1},
    )
    journal = CommandJournal(tmp_path)
    journal.save("one", result, command=request)
    # An old release writes only the original result map, unaware of proofs.
    raw = json.loads(journal.path.read_text())
    raw["one"]["output"] = {"revision": 2}
    journal.path.write_text(json.dumps(raw), encoding="utf-8")
    assert (
        CommandJournal(tmp_path).get_for_command(request).output["execution_state"]
        == "conflict"
    )


@pytest.mark.parametrize("legacy_status", [404, 405])
def test_updated_publisher_sends_legacy_inventory_to_old_core_without_rekeying(
    monkeypatch, tmp_path, legacy_status
):
    node = publisher(tmp_path, feature_negotiation=True, inventory_schema_version=2)
    report = AgentInventory(
        device_id=node.credential.device_id,
        collected_at=datetime.now(UTC),
        hostname="compatibility-node",
        model="test",
        operating_system="Linux",
        operating_system_version="test",
        kernel_version="test",
        architecture="test",
        python_version="3.13",
        logical_cpu_count=1,
        memory_total_bytes=1024,
        root_total_bytes=2048,
        root_free_bytes=1024,
        network_manager_active=False,
        hardware_driver="mock",
    )
    node.inventory_provider = lambda: report
    credential = node.credential.model_copy(
        update={
            "hub_endpoint": "http://core.test",
            "api_endpoint": "http://core.test/api/v1",
        }
    )
    store = DeviceCredentialStore(tmp_path)
    store.save(credential)
    before = store.path.read_bytes(), store.binding_path.read_bytes()
    calls = []
    monkeypatch.setattr(
        "agent.runtime_features.requests.get", lambda *a, **k: response(legacy_status)
    )
    monkeypatch.setattr(
        "agent.runtime_features.requests.put",
        lambda *a, **k: pytest.fail("Old Core must not receive feature PUT"),
    )

    def post(url, **kwargs):
        calls.append(kwargs["json"])
        return response(202)

    monkeypatch.setattr("agent.core_client.requests.post", post)
    node._publish_inventory()
    assert calls[0]["hostname"] == report.hostname and "schema_version" not in calls[0]
    node.reconciliation_store.save(
        ReconciliationState(applied_revision=7, inventory_generation=3)
    )
    assert node.reconciliation_store.load().applied_revision == 7
    assert store.load() == credential
    assert (store.path.read_bytes(), store.binding_path.read_bytes()) == before
    # Original credential file still contains only the old schema's fields.
    assert set(json.loads(before[0])) == {
        "schema_version",
        "device_id",
        "credential_id",
        "credential_secret",
    }
