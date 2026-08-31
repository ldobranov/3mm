from pathlib import Path

from datetime import UTC, datetime
import threading
import time

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

    assert publisher._event_queue.qsize() == 1
    publisher._deliver_event(publisher._event_queue.get_nowait())

    queued = publisher.outbox.load()
    assert len(queued) == 1
    assert queued[0].payload["device_id"] == credential.device_id
    assert queued[0].payload["event_id"].startswith("evt_")


def test_hardware_event_callback_does_not_wait_for_core(monkeypatch, tmp_path: Path) -> None:
    delivery_started = threading.Event()
    release_delivery = threading.Event()

    def blocked_post(*_args, **_kwargs):
        delivery_started.set()
        release_delivery.wait(1)

    monkeypatch.setattr("agent.core_client.CorePublisher._post", blocked_post)
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
    publisher._event_thread = threading.Thread(
        target=publisher._run_event_delivery,
        daemon=True,
    )
    publisher._event_thread.start()

    started_at = time.monotonic()
    publisher.publish_event({"event_type": "gpio.input.changed", "payload": {}})
    elapsed = time.monotonic() - started_at

    assert elapsed < 0.05
    assert delivery_started.wait(0.5)
    release_delivery.set()
    publisher.stop()


def test_command_receiver_uses_bounded_authenticated_long_poll(monkeypatch, tmp_path: Path) -> None:
    request = {}

    class Response:
        status_code = 204

        def raise_for_status(self):
            return None

    def get(url, **kwargs):
        request.update(url=url, **kwargs)
        return Response()

    monkeypatch.setattr("agent.core_client.requests.get", get)
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

    publisher._poll_command(wait_seconds=5.0)

    assert request["url"].endswith(
        "/api/v1/devices/dev_0123456789abcdef0123456789abcdef/commands/next"
    )
    assert request["headers"] == publisher.headers
    assert request["params"] == {"wait_seconds": 5.0}
    assert request["timeout"] == 10.0


def test_command_worker_is_independent_from_heartbeat_loop(monkeypatch, tmp_path: Path) -> None:
    received = threading.Event()

    def receive_once(self, *, wait_seconds=0.0):
        assert wait_seconds == 5.0
        received.set()
        self._stop.set()

    monkeypatch.setattr("agent.core_client.CorePublisher._poll_command", receive_once)
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
        interval_seconds=30,
    )

    publisher._run_commands()

    assert received.is_set()
