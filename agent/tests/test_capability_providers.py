from datetime import UTC, datetime

import pytest
from agent.capability_providers import AdapterProvider, AgentProviderRegistry
from agent.hardware.identifier import MockIdentifierAdapter
from three_mm_protocol.device_capabilities import CapabilityAdvertisementV1, CapabilityProviderSnapshotV2
from three_mm_protocol.capability_availability import CapabilityHealthV1

DEVICE = 'dev_' + 'a' * 32


class OtherAdapter:
    def provider_declaration(self):
        return AdapterProvider(provider_id='example.sensor', provider_version='1.0',
            capabilities=(CapabilityAdvertisementV1(capability_id='example.measurement.v1'),))

    def provider_health(self):
        return (CapabilityHealthV1(capability_id='example.measurement.v1', healthy=True),)


class Transport:
    def __init__(self):
        self.rows = {}; self.health = []; self.writes = 0; self.lost_ack = False

    def provider(self, *identity):
        return self.rows.get(identity)

    def report_provider(self, report):
        current = self.rows.get((report.provider_type, report.provider_id))
        assert report.expected_revision == (current.revision if current else 0)
        row = CapabilityProviderSnapshotV2(device_id=report.device_id,
            provider_type=report.provider_type, provider_id=report.provider_id,
            provider_version=report.provider_version, revision=report.expected_revision+1,
            capabilities=report.capabilities, configured_capability_ids=current.configured_capability_ids if current else (),
            enabled=current.enabled if current else True, reported_at=datetime.now(UTC))
        self.rows[(row.provider_type, row.provider_id)] = row; self.writes += 1
        if self.lost_ack:
            self.lost_ack = False
            from three_mm_protocol.transport import DeviceTransportError
            raise DeviceTransportError('Acknowledgement lost')
        return row

    def publish(self, report):
        self.health.append(report)


def test_same_path_registers_unrelated_adapters_without_selecting_or_enabling(tmp_path):
    transport = Transport()
    registry = AgentProviderRegistry(tmp_path, DEVICE, (MockIdentifierAdapter(tmp_path/'scan.json'), OtherAdapter()))
    registry.synchronize(transport, availability=True)
    assert len(transport.rows) == len(transport.health) == 2
    assert all(row.configured_capability_ids == () for row in transport.rows.values())
    identity = ('agent_adapter', 'identifier.mock')
    selected = transport.rows[identity].model_copy(update={'enabled':False, 'configured_capability_ids':('identifier.scan.v1',)})
    transport.rows[identity] = selected
    registry.synchronize(transport, availability=True)
    assert transport.writes == 2
    assert transport.rows[identity] == selected  # Reports cannot override human choices.


def test_lost_ack_restart_and_removed_adapter_are_reconciled_without_replay_or_adoption(tmp_path):
    transport = Transport(); transport.lost_ack = True
    registry = AgentProviderRegistry(tmp_path, DEVICE, (OtherAdapter(),))
    from three_mm_protocol.transport import DeviceTransportError
    with pytest.raises(DeviceTransportError): registry.synchronize(transport, availability=True)
    registry.synchronize(transport, availability=True)
    assert transport.writes == 1
    foreign = MockIdentifierAdapter(tmp_path/'foreign').provider_declaration()
    transport.report_provider(foreign.report(DEVICE, 0))
    AgentProviderRegistry(tmp_path, DEVICE, ()).synchronize(transport, availability=True)
    assert transport.rows[('agent_adapter','example.sensor')].capabilities == ()
    assert transport.rows[foreign.identity].capabilities  # Never adopts/withdraws unrelated providers.
    writes = transport.writes
    AgentProviderRegistry(tmp_path, DEVICE, ()).synchronize(transport, availability=True)
    assert transport.writes == writes


def test_duplicate_adapters_and_foreign_corrupt_state_never_write(tmp_path):
    transport = Transport()
    with pytest.raises(ValueError, match='Duplicate'):
        AgentProviderRegistry(tmp_path, DEVICE, (OtherAdapter(), OtherAdapter())).synchronize(transport, availability=False)
    registry = AgentProviderRegistry(tmp_path, DEVICE, (OtherAdapter(),))
    registry.synchronize(transport, availability=False)
    assert not transport.health
    with pytest.raises(ValueError, match='identity'):
        AgentProviderRegistry(tmp_path, 'dev_'+'b'*32, ()).synchronize(transport, availability=True)
    registry.path.write_text('invalid json')
    with pytest.raises(ValueError): registry.synchronize(transport, availability=True)
    assert transport.writes == 1


def test_broken_adapter_does_not_starve_another_provider(tmp_path):
    class Broken(MockIdentifierAdapter):
        def provider_health(self): raise RuntimeError('Adapter unavailable')
    transport = Transport()
    registry = AgentProviderRegistry(tmp_path, DEVICE, (Broken(tmp_path/'scan'), OtherAdapter()))
    with pytest.raises(RuntimeError): registry.synchronize(transport, availability=True)
    assert any(item.provider_id == 'example.sensor' for item in transport.health)
