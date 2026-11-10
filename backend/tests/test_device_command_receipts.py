"""Expiry fences execution; it must not erase an already delivered receipt."""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import backend.database  # noqa: F401
from backend.db.base import Base
from backend.db.device import Device, DeviceCommand
from backend.services.device_commands import (
    DeviceCommandError, deliver_next_command, queue_command, record_command_result,
)
from backend.tests.test_device_commands import DEVICE_ID, _seed_authority
from three_mm_protocol import AgentCommandResult


@pytest.fixture
def attempt():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        now = datetime.now(UTC)
        device = Device(device_id=DEVICE_ID, display_name='receipt-test', role='node',
                        protocol_version='1.0', approved_at=now)
        db.add(device); db.commit(); _seed_authority(db, device)
        command = queue_command(db, device=device, command_type='agent.refresh_inventory',
                                payload={}, idempotency_key='original', ttl_seconds=10, now=now)
        db.commit()
        yield db, device, command, now
    engine.dispose()


@pytest.mark.parametrize('expired_by_poll', [False, True])
@pytest.mark.parametrize('status', ['failed', 'succeeded'])
def test_late_first_receipt_is_durable_acknowledged_and_never_redispatched(attempt, expired_by_poll, status):
    db, device, command, now = attempt
    deliver_next_command(db, device=device, now=now + timedelta(seconds=1))
    if expired_by_poll:
        assert deliver_next_command(db, device=device, now=now + timedelta(seconds=11)) is None
    result = AgentCommandResult(command_id=command.command_id, device_id=DEVICE_ID, status=status,
        completed_at=now + timedelta(seconds=10.026), output={'execution_state':'unknown'},
        error='Uncertain physical outcome')
    deadline = command.expires_at
    saved = record_command_result(db, device=device, result=result)
    assert saved.status == 'expired'  # A late success is not on-time authorization.
    assert saved.result == {'late_completion':result.model_dump(mode='json')}
    assert saved.completed_at is not None and saved.expires_at == deadline
    first_result = saved.result.copy()
    conflicting = result.model_copy(update={'status':'succeeded','output':{'execution_state':'executed'}})
    again = record_command_result(db, device=device, result=conflicting)
    assert again.result == first_result and again.status == 'expired'
    assert deliver_next_command(db, device=device, now=now + timedelta(seconds=12)) is None
    db.refresh(command)
    assert command.delivery_attempts == 1


def test_expiry_without_dispatch_is_not_permission_to_invent_a_receipt(attempt):
    db, device, command, now = attempt
    assert deliver_next_command(db, device=device, now=now + timedelta(seconds=11)) is None
    result = AgentCommandResult(command_id=command.command_id, device_id=DEVICE_ID,
                               status='succeeded', completed_at=now + timedelta(seconds=12))
    with pytest.raises(DeviceCommandError, match='not been delivered'):
        record_command_result(db, device=device, result=result)
    db.rollback(); db.refresh(command)
    assert command.result is None and command.completed_at is None


def test_late_receipt_cannot_cross_device_identity(attempt):
    db, device, command, now = attempt
    deliver_next_command(db, device=device, now=now + timedelta(seconds=1))
    result = AgentCommandResult(command_id=command.command_id, device_id='dev_'+'f'*32,
                               status='failed', completed_at=now + timedelta(seconds=11))
    with pytest.raises(DeviceCommandError, match='identity mismatch'):
        record_command_result(db, device=device, result=result)
    db.rollback()
    assert db.get(DeviceCommand, command.id).result is None
