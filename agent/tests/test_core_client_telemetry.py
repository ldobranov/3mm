"""Input/command lanes cannot wait behind replaceable telemetry snapshots."""
from datetime import UTC, datetime, timedelta
import threading
from types import SimpleNamespace

from agent.core_client import CommandJournal, CorePublisher, DeviceCredential, OutboxStore, ReconciliationStore
from packages.protocol import AgentCommand
from packages.protocol.transport import DeviceTransportError


DEVICE = 'dev_' + 'a' * 32


def publisher(tmp_path, **kwargs):
    return CorePublisher(core_url='http://core', credential=DeviceCredential(device_id=DEVICE,
        credential_id='cred_'+'b'*32, credential_secret='s'*43), inventory_provider=lambda: None,
        command_journal=CommandJournal(tmp_path), reconciliation_store=ReconciliationStore(tmp_path),
        outbox=OutboxStore(tmp_path), started_monotonic=0, **kwargs)


def test_blocked_telemetry_does_not_delay_edges_and_bursts_coalesce_on_existing_publisher(monkeypatch, tmp_path):
    entered, release, delivered, refreshed = (threading.Event() for _ in range(4))
    input_value = [False]
    edges, snapshots, health_threads, heartbeats, inventories, maintenance = [], [], [], [], [], []
    runtime = SimpleNamespace(capability_states=lambda: {'gpio.digital.input': {'gpio.input.1': input_value[0]}},
        maintain_services=lambda: maintenance.append(True))
    subject = publisher(tmp_path, module_runtime=runtime, interval_seconds=30)
    monkeypatch.setattr(CorePublisher, '_negotiated_inventory_version', lambda _: 1)
    monkeypatch.setattr(CorePublisher, '_publish_inventory', lambda _: inventories.append(True))
    monkeypatch.setattr(CorePublisher, '_flush_outbox', lambda _: None)
    monkeypatch.setattr(CorePublisher, '_reconcile_state', lambda _: None)
    monkeypatch.setattr(CorePublisher, '_node_execution', lambda _: None)

    def health(_):
        health_threads.append(threading.current_thread().name)
        entered.set()
        assert release.wait(5), 'Owned telemetry gate was not released'

    def post(_, suffix, payload):
        if suffix == 'events':
            edges.append(payload['payload']['value'])
            input_value[0] = edges[-1]
            if len(edges) == 20:
                delivered.set()
        elif suffix == 'heartbeat':
            heartbeats.append(True)
        elif suffix.startswith('capabilities/'):
            snapshots.append(payload['values']['gpio.input.1'])
            if len(snapshots) == 2:
                refreshed.set()
                subject._stop.set()

    monkeypatch.setattr(CorePublisher, '_publish_capability_availability', health)
    monkeypatch.setattr(CorePublisher, '_post', post)
    subject._thread = threading.Thread(target=subject._run, name='owned-existing-publisher', daemon=True)
    subject._event_thread = threading.Thread(target=subject._run_event_delivery, name='owned-event-lane', daemon=True)
    subject._thread.start(); subject._event_thread.start()
    try:
        assert entered.wait(2)
        for index in range(20):
            subject.publish_event({'event_type': 'gpio.input.changed', 'payload': {'value': index % 2 == 0}})
        assert delivered.wait(2), 'Second edge waited behind optional telemetry I/O'
        assert edges == [index % 2 == 0 for index in range(20)]
        release.set()
        assert refreshed.wait(3), 'Coalesced latest state was not published promptly'
    finally:
        release.set()
        subject.stop()
    assert snapshots == [False, False]
    assert health_threads == ['owned-existing-publisher', 'owned-existing-publisher']
    assert heartbeats == inventories == maintenance == [True]
    assert not subject._thread.is_alive() and not subject._event_thread.is_alive()


def test_command_receipt_and_next_permit_do_not_wait_for_telemetry(monkeypatch, tmp_path):
    now = datetime.now(UTC)
    commands = [AgentCommand(protocol_version='1.0', command_id='cmd_'+str(index)*32, device_id=DEVICE,
        command_type='application.capability.invoke', payload={'capability_id':'test.output','action':'write','arguments':{}},
        idempotency_key='command-'+str(index), created_at=now, expires_at=now+timedelta(seconds=10)) for index in (1, 2)]
    permits, invocations, receipts = [], [], []
    available = [True]
    class Transport:
        device_id = DEVICE
        def receive_command(self, *, timeout_seconds):return commands.pop(0)
        def authorize_execution(self, command_id, *, timeout_seconds):
            permits.append(command_id)
            return {'command_id':command_id, 'authorized':True}
    runtime = SimpleNamespace(capability_healthy=lambda _: available[0], validate_invocation=lambda _: None,
        invoke=lambda *args, **kwargs: invocations.append(True) or {'accepted':True})
    subject = publisher(tmp_path, module_runtime=runtime, capability_availability=True, transport=Transport())
    def forbidden(_):raise AssertionError('Command receiver entered optional telemetry I/O')
    monkeypatch.setattr(CorePublisher, '_publish_capability_states', forbidden)
    monkeypatch.setattr(CorePublisher, '_submit_result', lambda _, result: receipts.append(result))
    subject._poll_command()
    available[0] = False
    subject._poll_command()
    assert len(permits) == 2 and invocations == [True]
    assert receipts[0].status == 'succeeded'
    assert receipts[1].status == 'failed' and receipts[1].output['execution_state'] == 'not_executed'


def test_offline_edges_remain_durable_in_fifo_order_without_telemetry_work(monkeypatch, tmp_path):
    subject = publisher(tmp_path)
    def offline(*args):raise DeviceTransportError('offline')
    def forbidden(_):raise AssertionError('Event lane entered optional telemetry I/O')
    monkeypatch.setattr(CorePublisher, '_post', offline)
    monkeypatch.setattr(CorePublisher, '_publish_capability_states', forbidden)
    for value in (True, False):
        subject.publish_event({'event_type':'gpio.input.changed','payload':{'value':value}})
        subject._deliver_event(subject._event_queue.get_nowait())
    saved = OutboxStore(tmp_path).load()
    assert [entry.payload['payload']['value'] for entry in saved] == [True, False]
    assert len({entry.payload['event_id'] for entry in saved}) == 2
    resent = []
    monkeypatch.setattr(CorePublisher, '_post', lambda _, suffix, payload: resent.append(payload['payload']['value']))
    subject._flush_outbox()
    assert resent == [True, False] and subject.outbox.load() == []


def test_continuous_snapshot_requests_do_not_starve_periodic_maintenance(monkeypatch, tmp_path):
    now = [0.0]
    heartbeats, maintenance, snapshots, flushes = [], [], [], []
    subject = publisher(tmp_path, interval_seconds=30,
        module_runtime=SimpleNamespace(maintain_services=lambda: maintenance.append(True)))
    monkeypatch.setattr('agent.core_client.time', SimpleNamespace(monotonic=lambda: now[0]))
    monkeypatch.setattr('agent.core_client.CAPABILITY_PUBLICATION_MIN_SECONDS', 0)
    monkeypatch.setattr(CorePublisher, '_negotiated_inventory_version', lambda _: 1)
    monkeypatch.setattr(CorePublisher, '_publish_inventory', lambda _: None)
    monkeypatch.setattr(CorePublisher, '_flush_outbox', lambda _: flushes.append(True))
    monkeypatch.setattr(CorePublisher, '_reconcile_state', lambda _: None)
    monkeypatch.setattr(CorePublisher, '_node_execution', lambda _: None)
    monkeypatch.setattr(CorePublisher, '_send_or_queue', lambda *args: heartbeats.append(True))
    def state(_):
        snapshots.append(True)
        subject._request_capability_publication()
        if len(snapshots) in (2, 3):
            now[0] += 15
        if len(snapshots) == 4:
            subject._stop.set()
    monkeypatch.setattr(CorePublisher, '_publish_capability_states', state)
    subject._run()
    assert len(snapshots) == 4
    assert heartbeats == maintenance == flushes == [True, True]


def test_stop_wakes_the_existing_publisher_wait_without_another_worker(tmp_path):
    subject = publisher(tmp_path, interval_seconds=30)
    entered = threading.Event()
    wake = threading.Event()
    class ObservedWake:
        def wait(self, timeout):
            entered.set()
            return wake.wait(timeout)
        def set(self):wake.set()
    subject._capability_wake = ObservedWake()
    subject._thread = threading.Thread(target=subject._wait_with_capability_updates, daemon=True)
    subject._thread.start()
    assert entered.wait(1)
    subject.stop()
    assert not subject._thread.is_alive()
