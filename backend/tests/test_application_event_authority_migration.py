"""Populated event queue survives upgrade; legacy NULL is not an opt-in grant."""

import subprocess

import pytest
from sqlalchemy import create_engine, text

from backend.tests.test_migration_history import _alembic
from backend.tests.test_authority_metadata_migration import seed


def test_event_queue_preserved_without_grant_backfill_and_pin_blocks_downgrade(tmp_path):
    url = f"sqlite:///{(tmp_path / 'event-migration.db').as_posix()}"
    _alembic(url, 'upgrade', 'a7bf06b7c8d9')
    engine = create_engine(url)
    seed(engine)
    with engine.begin() as db:
        db.execute(text("INSERT INTO device_events(id,device_id,event_id,event_type,payload,occurred_at) VALUES (1,1,:event,'example.changed.v1','{}','2026-10-09')"), {'event': 'evt_' + 'e' * 32})
        db.execute(text("INSERT INTO application_event_deliveries(id,application_installation_id,subscription_id,device_event_id,status,attempts) VALUES (1,1,'changes',1,'pending',2)"))
    engine.dispose()
    _alembic(url, 'upgrade', 'head')
    _alembic(url, 'check')
    engine = create_engine(url)
    with engine.begin() as db:
        assert db.execute(text('SELECT subscription_id,status,attempts,authority_epoch FROM application_event_deliveries')).one() == ('changes', 'pending', 2, None)
        assert not db.execute(text('PRAGMA foreign_key_check')).all()
    engine.dispose()
    _alembic(url, 'downgrade', 'dab239e0f1a2')
    _alembic(url, 'upgrade', 'head')
    engine = create_engine(url)
    with engine.begin() as db:
        db.execute(text("UPDATE application_event_deliveries SET authority_epoch=:epoch"), {'epoch': 'f' * 32})
    engine.dispose()
    with pytest.raises(subprocess.CalledProcessError):
        _alembic(url, 'downgrade', 'dab239e0f1a2')
    engine = create_engine(url)
    with engine.connect() as db:
        assert db.scalar(text('SELECT version_num FROM alembic_version')) == 'fcd45b0213c4'
        assert db.scalar(text('SELECT authority_epoch FROM application_event_deliveries')) == 'f' * 32
    engine.dispose()
