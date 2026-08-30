from pathlib import Path

from datetime import UTC, datetime

from agent.core_client import (
    CommandJournal, CorePublisher, DeviceCredential, DeviceCredentialStore,
    OutboxEntry, OutboxStore, ReconciliationState, ReconciliationStore,
)
from three_mm_protocol import AgentCommandResult


def test_device_credential_round_trip_is_private(tmp_path: Path) -> None:
    credential = DeviceCredential(
        device_id="dev_0123456789abcdef0123456789abcdef",
        credential_id="cred_0123456789abcdef0123456789abcdef",
        credential_secret="s" * 43,
    )
    store = DeviceCredentialStore(tmp_path / "agent")

    store.save(credential)

    assert store.load() == credential
    assert store.path.stat().st_mode & 0o777 == 0o600


def test_command_journal_round_trip_is_private(tmp_path: Path) -> None:
    journal = CommandJournal(tmp_path / "agent")
    result = AgentCommandResult(
        command_id="cmd_0123456789abcdef0123456789abcdef",
        device_id="dev_0123456789abcdef0123456789abcdef",
        status="succeeded",
        completed_at=datetime.now(UTC),
        output={"inventory_published": True},
    )

    journal.save("refresh-1", result)

    assert CommandJournal(tmp_path / "agent").get("refresh-1") == result
    assert journal.path.stat().st_mode & 0o777 == 0o600


def test_reconciliation_state_survives_restart(tmp_path: Path) -> None:
    store = ReconciliationStore(tmp_path / "agent")
    state = ReconciliationState(applied_revision=3, inventory_generation=2)
    store.save(state)
    assert ReconciliationStore(tmp_path / "agent").load() == state
    assert store.path.stat().st_mode & 0o777 == 0o600


def test_outbox_deduplicates_replaceable_events(tmp_path: Path) -> None:
    outbox = OutboxStore(tmp_path / "agent")
    outbox.enqueue(OutboxEntry(suffix="heartbeat", payload={"sequence": 1}, deduplication_key="heartbeat"))
    outbox.enqueue(OutboxEntry(suffix="heartbeat", payload={"sequence": 2}, deduplication_key="heartbeat"))
    assert [entry.payload for entry in outbox.load()] == [{"sequence": 2}]
    assert outbox.path.stat().st_mode & 0o777 == 0o600


def test_core_publisher_posts_current_capability_snapshots(monkeypatch, tmp_path: Path) -> None:
    posted = []

    class Response:
        def raise_for_status(self):
            return None

    monkeypatch.setattr(
        "agent.core_client.requests.post",
        lambda url, **kwargs: posted.append((url, kwargs["json"])) or Response(),
    )

    class Runtime:
        def capability_states(self):
            return {"gpio.digital.input": {"gpio.input.1": True}}

    credential = DeviceCredential(
        device_id="dev_0123456789abcdef0123456789abcdef",
        credential_id="cred_0123456789abcdef0123456789abcdef",
        credential_secret="s" * 43,
    )
    publisher = CorePublisher(
        core_url="http://core",
        credential=credential,
        inventory_provider=lambda: None,
        command_journal=CommandJournal(tmp_path),
        reconciliation_store=ReconciliationStore(tmp_path),
        outbox=OutboxStore(tmp_path),
        started_monotonic=0,
        module_runtime=Runtime(),
    )

    publisher._publish_capability_states()

    assert posted[0][0].endswith(
        "/api/v1/devices/dev_0123456789abcdef0123456789abcdef/capabilities/gpio.digital.input/state"
    )
    assert posted[0][1]["values"] == {"gpio.input.1": True}


def test_identifier_event_uses_agent_identity_and_persistent_outbox(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "agent.core_client.CorePublisher._post",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            __import__("requests").RequestException("offline")
        ),
    )
    credential = DeviceCredential(
        device_id="dev_0123456789abcdef0123456789abcdef",
        credential_id="cred_0123456789abcdef0123456789abcdef",
        credential_secret="s" * 43,
    )
    publisher = CorePublisher(
        core_url="http://core",
        credential=credential,
        inventory_provider=lambda: None,
        command_journal=CommandJournal(tmp_path),
        reconciliation_store=ReconciliationStore(tmp_path),
        outbox=OutboxStore(tmp_path),
        started_monotonic=0,
    )

    publisher.publish_event(
        {
            "device_id": "dev_ffffffffffffffffffffffffffffffff",
            "event_type": "identifier.scan.v1",
            "payload": {
                "capability_id": "identifier.scan.v1",
                "opaque_identifier": "TAG-1",
                "reader_id": "reader.mock.1",
                "adapter_kind": "mock",
                "sequence": 1,
            },
        }
    )

    queued = publisher.outbox.load()
    assert len(queued) == 1
    assert queued[0].payload["device_id"] == credential.device_id
    assert queued[0].payload["event_id"].startswith("evt_")
