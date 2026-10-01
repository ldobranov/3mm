import base64
from datetime import UTC, datetime, timedelta

import pytest
import requests

from agent.core_client import CommandJournal, CorePublisher, DeviceCredential, OutboxStore, ReconciliationStore
from agent.node_update_client import NodeUpdateHelperError
from agent.node_update_execution import NodeUpdateExecution
from three_mm_protocol import AgentCommand
from three_mm_protocol.node_updates import NodeUpdateApplyRequest, NodeUpdateAuthorization, NodeUpdateOperation, NodeUpdateSupport

DEVICE = "dev_" + "a" * 32


def command(operation="b"):
    now = datetime.now(UTC)
    request = NodeUpdateApplyRequest(
        operation_id="nodeupd_" + operation * 32, device_id=DEVICE,
        release_id="v0.3.0-beta.26", archive_sha256="c" * 64,
        confirmed_install=True, created_at=now, expires_at=now + timedelta(seconds=120),
    )
    authorization = NodeUpdateAuthorization(
        key_id="d" * 64, request=request, signature=base64.b64encode(b"s" * 64).decode(),
    )
    return AgentCommand(
        command_id="cmd_" + operation * 32, device_id=DEVICE,
        command_type="agent.update.apply", payload=authorization.model_dump(mode="json"),
        idempotency_key="node-update-apply:" + request.operation_id,
        created_at=now, expires_at=request.expires_at,
    )


def outcome(authorization, status="accepted", now=None):
    request = authorization.request
    return NodeUpdateOperation(
        operation_id=request.operation_id, device_id=request.device_id,
        release_id=request.release_id, archive_sha256=request.archive_sha256,
        status=status, updated_at=now or datetime.now(UTC),
    )


class Helper:
    def __init__(self):
        self.calls = []
        self.operation = None

    def apply(self, authorization):
        self.calls.append(authorization)
        self.operation = outcome(authorization)
        return self.operation

    def status(self, operation_id):
        assert self.operation is None or self.operation.operation_id == operation_id
        return self.operation


def test_tracking_is_durable_before_handoff_and_restart_only_reports(tmp_path):
    helper = Helper()
    execution = NodeUpdateExecution(data_dir=tmp_path, device_id=DEVICE, helper=helper)
    original = helper.apply

    def apply(authorization):
        assert execution.path.is_file()
        return original(authorization)

    helper.apply = apply
    assert execution.apply(command()).status == "accepted"
    helper.operation = outcome(helper.calls[0], "succeeded")
    restarted = NodeUpdateExecution(data_dir=tmp_path, device_id=DEVICE, helper=helper)
    reports = []
    restarted.report_pending(lambda suffix, body: reports.append((suffix, body)))
    restarted.report_pending(lambda *_: pytest.fail("Already acknowledged outcome was re-sent"))
    assert len(helper.calls) == 1
    assert reports[0][0] == "node-updates/" + helper.operation.operation_id + "/report"
    assert reports[0][1]["status"] == "succeeded"


def test_lost_handoff_response_does_not_reexecute_on_restart(tmp_path):
    helper = Helper()
    execution = NodeUpdateExecution(data_dir=tmp_path, device_id=DEVICE, helper=helper)
    original = helper.apply

    def lost_response(authorization):
        original(authorization)
        raise NodeUpdateHelperError("lost_response")

    helper.apply = lost_response
    with pytest.raises(NodeUpdateHelperError):
        execution.apply(command())
    restarted = NodeUpdateExecution(data_dir=tmp_path, device_id=DEVICE, helper=helper)
    reports = []
    restarted.report_pending(lambda _, body: reports.append(body))
    assert len(helper.calls) == 1
    assert reports[0]["status"] == "accepted"


def test_offline_reports_retry_newest_root_outcome_without_queueing(tmp_path):
    helper = Helper()
    execution = NodeUpdateExecution(data_dir=tmp_path, device_id=DEVICE, helper=helper)
    execution.apply(command())

    def offline(*_):
        raise requests.ConnectionError("offline")

    with pytest.raises(requests.ConnectionError):
        execution.report_pending(offline)
    helper.operation = outcome(helper.calls[0], "rolled_back")
    reports = []
    execution.report_pending(lambda _, body: reports.append(body))
    assert [body["status"] for body in reports] == ["rolled_back"]
    assert len(helper.calls) == 1


@pytest.mark.parametrize("change", ["device", "deadline", "unsigned"])
def test_unsigned_wrong_device_or_changed_deadline_never_reaches_helper(tmp_path, change):
    helper = Helper()
    execution = NodeUpdateExecution(data_dir=tmp_path, device_id=DEVICE, helper=helper)
    message = command()
    payload = dict(message.payload)
    if change == "device":
        payload["request"] = {**payload["request"], "device_id": "dev_" + "e" * 32}
    elif change == "deadline":
        message = message.model_copy(update={"expires_at": message.expires_at + timedelta(seconds=1)})
    else:
        payload = payload["request"]
    with pytest.raises(ValueError if change == "unsigned" else NodeUpdateHelperError):
        execution.apply(message.model_copy(update={"payload": payload}))
    assert not helper.calls
    assert not execution.path.exists()


def test_unknown_blocks_new_operation_even_after_report_ack(tmp_path):
    helper = Helper()
    execution = NodeUpdateExecution(data_dir=tmp_path, device_id=DEVICE, helper=helper)
    execution.apply(command())
    helper.operation = outcome(helper.calls[0], "unknown")
    execution.report_pending(lambda *_: None)
    with pytest.raises(NodeUpdateHelperError, match="node_update_unresolved"):
        execution.apply(command("e"))
    assert len(helper.calls) == 1
    helper.operation = outcome(helper.calls[0], "running")
    with pytest.raises(NodeUpdateHelperError, match="outcome_regression"):
        execution.report_pending(lambda *_: pytest.fail("Unknown was regressed to running"))


def test_acknowledged_terminal_allows_new_operation_and_rejects_regression(tmp_path):
    helper = Helper()
    execution = NodeUpdateExecution(data_dir=tmp_path, device_id=DEVICE, helper=helper)
    execution.apply(command())
    helper.operation = outcome(helper.calls[0], "succeeded")
    execution.report_pending(lambda *_: None)
    helper.operation = outcome(helper.calls[0], "running")
    with pytest.raises(NodeUpdateHelperError, match="outcome_regression"):
        execution.report_pending(lambda *_: pytest.fail("Regressed status sent"))
    execution.apply(command("e"))
    assert len(helper.calls) == 2


def test_command_loop_records_handoff_not_final_installation(monkeypatch, tmp_path):
    helper = Helper()
    execution = NodeUpdateExecution(data_dir=tmp_path, device_id=DEVICE, helper=helper)
    message = command()

    class Response:
        status_code = 200
        def raise_for_status(self):
            pass
        def json(self):
            return message.model_dump(mode="json")

    monkeypatch.setattr("agent.core_client.requests.get", lambda *_args, **_kwargs: Response())
    publisher = CorePublisher(
        core_url="http://core", credential=DeviceCredential(
            device_id=DEVICE, credential_id="cred_" + "a" * 32, credential_secret="s" * 43,
        ), inventory_provider=lambda: None, command_journal=CommandJournal(tmp_path),
        reconciliation_store=ReconciliationStore(tmp_path), outbox=OutboxStore(tmp_path),
        started_monotonic=0, node_update_execution=execution,
    )
    results = []
    monkeypatch.setattr(CorePublisher, "_submit_result", lambda _, result: results.append(result))
    publisher._poll_command()
    publisher._poll_command()  # Persistent command journal suppresses a repeat handoff.
    assert len(helper.calls) == 1
    assert results[0].status == "succeeded"
    assert results[0].output["handoff_status"] == "accepted"
    assert "installation_succeeded" not in results[0].output


@pytest.mark.parametrize("ready", [True, False])
def test_node_reports_root_support_when_desired_revision_is_unchanged(monkeypatch, tmp_path, ready):
    helper = Helper()

    def support():
        if not ready:
            raise NodeUpdateHelperError("old_helper_or_missing_socket")
        return NodeUpdateSupport(approval_key_id="d" * 64, trusted_device_id=DEVICE)

    helper.support = support
    publisher = CorePublisher(
        core_url="http://core", credential=DeviceCredential(
            device_id=DEVICE, credential_id="cred_" + "a" * 32, credential_secret="s" * 43,
        ), inventory_provider=lambda: None, command_journal=CommandJournal(tmp_path),
        reconciliation_store=ReconciliationStore(tmp_path), outbox=OutboxStore(tmp_path),
        started_monotonic=0,
        node_update_execution=NodeUpdateExecution(data_dir=tmp_path, device_id=DEVICE, helper=helper),
    )

    class Response:
        def raise_for_status(self):
            pass
        def json(self):
            return {"device_id": DEVICE, "revision": 0, "state": {}, "updated_at": datetime.now(UTC).isoformat()}

    monkeypatch.setattr("agent.core_client.requests.get", lambda *_args, **_kwargs: Response())
    sent = []
    monkeypatch.setattr(CorePublisher, "_send_or_queue", lambda _, suffix, body, key: sent.append((suffix, body)))
    publisher._reconcile_state()
    assert sent[0][0] == "reported-state"
    reported = sent[0][1]["state"]["node_update"]
    assert reported["signed_apply_supported"] is ready
    if ready:
        assert reported["approval_key_id"] == "d" * 64
        assert reported["trusted_device_id"] == DEVICE
