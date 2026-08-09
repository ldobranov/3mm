from pathlib import Path

from datetime import UTC, datetime

from agent.core_client import CommandJournal, DeviceCredential, DeviceCredentialStore
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
