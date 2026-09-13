from datetime import UTC, datetime, timedelta
import pytest
from agent.physical_command_journal import PhysicalCommandJournal
from three_mm_protocol import AgentCommand


def command():
    now = datetime.now(UTC)
    return AgentCommand(command_id='cmd_' + 'a'*32, device_id='dev_' + 'b'*32,
        command_type='capability.invoke', payload={'capability_id': 'gpio.digital.output', 'action': 'pulse', 'arguments': {}},
        idempotency_key='pulse-1', created_at=now, expires_at=now+timedelta(seconds=10))


@pytest.mark.parametrize('after_effect', [False, True])
def test_crash_leaves_unknown_and_never_repeats(tmp_path, after_effect):
    request = command(); effects = []
    def crash():
        if after_effect:
            effects.append('pulse')
        raise SystemExit('process crash')
    with pytest.raises(SystemExit):
        PhysicalCommandJournal(tmp_path).execute(request, crash)
    result = PhysicalCommandJournal(tmp_path).execute(request, lambda: effects.append('retry'))
    assert result.output['execution_state'] == 'unknown'
    assert effects == (['pulse'] if after_effect else [])


def test_success_replay_and_payload_conflict(tmp_path):
    request = command(); calls = []
    def invoke():
        calls.append(1)
        return {'active': False}
    journal = PhysicalCommandJournal(tmp_path)
    assert journal.execute(request, invoke).status == 'succeeded'
    assert PhysicalCommandJournal(tmp_path).execute(request, invoke).status == 'succeeded'
    changed = request.model_copy(update={'payload': {'action': 'different'}})
    assert journal.execute(changed, invoke).output['execution_state'] == 'conflict'
    assert calls == [1]


def test_expiry_after_authorization_and_offline_never_invoke(tmp_path):
    request = command(); calls = []
    clock = iter([request.created_at, request.expires_at])
    result = PhysicalCommandJournal(tmp_path).execute(request, lambda: calls.append(1), now=lambda: next(clock))
    assert result.output['execution_state'] == 'not_executed'
    request = request.model_copy(update={'idempotency_key': 'offline'})
    def offline():
        raise ConnectionError('offline')
    result = PhysicalCommandJournal(tmp_path).execute(request, lambda: calls.append(1), authorize=offline)
    assert result.output['execution_state'] == 'not_executed'
    assert calls == []


def test_argument_schema_rejects_ignored_or_ambiguous_constraints():
    from three_mm_protocol.application_commands import validate_argument_schema
    for field in (
        {'type': 'boolean', 'minimum': 0},
        {'type': 'boolean', 'enum': [0]},
        {'type': 'string', 'maxLength': True},
        {'type': 'integer', 'minimum': 0, 'maximum': 10, 'enum': [11]},
    ):
        with pytest.raises(ValueError):
            validate_argument_schema({'type': 'object', 'properties': {'value': field}, 'additionalProperties': False})
