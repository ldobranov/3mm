from pathlib import Path

from datetime import UTC, datetime

from agent.core_client import (
    CommandJournal, DeviceCredential, DeviceCredentialStore,
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
