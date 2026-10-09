"""Existing journal IDs, FK queues/cursors and producers survive migration."""

import subprocess
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.schema import CreateTable

from backend.db.device import DeviceEvent
from backend.tests.test_authority_metadata_migration import seed
from backend.tests.test_migration_history import _alembic


def test_device_journal_ids_backlog_cursor_and_legacy_writer_preserved(tmp_path):
    url = f"sqlite:///{(tmp_path / 'journal.db').as_posix()}"
    _alembic(url, 'upgrade', 'a7bf06b7c8d9')
    engine = create_engine(url)
    seed(engine)
    with engine.begin() as db:
        db.execute(text("INSERT INTO device_events(id,device_id,event_id,event_type,payload,occurred_at) VALUES (37,1,'evt_old','example.old.v1','{}','2026-10-09')"))
        db.execute(text("INSERT INTO application_event_deliveries(id,application_installation_id,subscription_id,device_event_id,status,attempts) VALUES (25,1,'changes',37,'pending',3)"))
        db.execute(text("INSERT INTO application_event_cursors(id,application_installation_id,subscription_id,last_device_event_id,last_event_id,acknowledged_count,dead_letter_count,dropped_dead_letter_count) VALUES (12,1,'changes',36,'evt_previous',4,2,1)"))
    engine.dispose()
    _alembic(url, 'upgrade', 'head')
    _alembic(url, 'check')
    engine = create_engine(url)
    with engine.begin() as db:
        assert db.execute(text('SELECT id,device_id,event_id,producer_kind,application_producer,publication_receipt FROM device_events')).one() == (37, 1, 'evt_old', 'device', None, None)
        assert db.execute(text('SELECT id,device_event_id,status,attempts,authority_epoch FROM application_event_deliveries')).one() == (25, 37, 'pending', 3, None)
        assert db.execute(text('SELECT id,last_device_event_id,last_event_id,acknowledged_count,dead_letter_count,dropped_dead_letter_count FROM application_event_cursors WHERE id=12')).one() == (12, 36, 'evt_previous', 4, 2, 1)
        db.execute(text("INSERT INTO device_events(device_id,event_id,event_type,payload,occurred_at) VALUES (1,'evt_legacy_new','example.old.v1','{}','2026-10-09')"))
        assert not db.execute(text('PRAGMA foreign_key_check')).all()
    engine.dispose()
    _alembic(url, 'downgrade', 'ebc34af102b3')
    engine = create_engine(url)
    with engine.connect() as db:
        assert db.execute(text('SELECT id,device_event_id,status,attempts FROM application_event_deliveries')).one() == (25, 37, 'pending', 3)
        assert not db.execute(text('PRAGMA foreign_key_check')).all()
    engine.dispose()


def test_application_history_blocks_downgrade_before_any_ddl(tmp_path):
    url = f"sqlite:///{(tmp_path / 'history.db').as_posix()}"
    _alembic(url, 'upgrade', 'head')
    engine = create_engine(url)
    with engine.begin() as db:
        db.execute(DeviceEvent.__table__.insert().values(device_id=None, producer_kind='application',
            application_producer={'kind': 'application'}, publication_declaration={}, publication_receipt={},
            authority_epoch='a' * 32, event_id='evt_app', event_type='example.event.v1', payload={},
            occurred_at=datetime.now(UTC)))
    engine.dispose()
    with pytest.raises(subprocess.CalledProcessError):
        _alembic(url, 'downgrade', 'ebc34af102b3')
    engine = create_engine(url)
    with engine.connect() as db:
        assert db.scalar(text('SELECT version_num FROM alembic_version')) == 'fcd45b0213c4'
        assert db.scalar(text('SELECT event_id FROM device_events')) == 'evt_app'
    engine.dispose()


def test_partial_precreated_producer_schema_is_refused_without_guessing(tmp_path):
    url = f"sqlite:///{(tmp_path / 'partial.db').as_posix()}"
    _alembic(url, 'upgrade', 'ebc34af102b3')
    engine = create_engine(url)
    with engine.begin() as db:
        db.execute(text("ALTER TABLE device_events ADD COLUMN producer_kind VARCHAR(16) NOT NULL DEFAULT 'device'"))
    engine.dispose()
    with pytest.raises(subprocess.CalledProcessError):
        _alembic(url, 'upgrade', 'head')
    engine = create_engine(url)
    assert 'publication_receipt' not in {item['name'] for item in inspect(engine).get_columns('device_events')}
    engine.dispose()


def test_used_authority_fence_blocks_multi_revision_downgrade_before_journal_ddl(tmp_path):
    url = f"sqlite:///{(tmp_path / 'fenced.db').as_posix()}"
    _alembic(url, 'upgrade', 'head')
    engine = create_engine(url)
    with engine.begin() as db:
        db.execute(text('UPDATE core_authority_guard SET revision=2 WHERE singleton_id=1'))
    engine.dispose()
    with pytest.raises(subprocess.CalledProcessError):
        _alembic(url, 'downgrade', 'base')
    engine = create_engine(url)
    with engine.connect() as db:
        assert db.scalar(text('SELECT version_num FROM alembic_version')) == 'fcd45b0213c4'
    assert 'publication_receipt' in {item['name'] for item in inspect(engine).get_columns('device_events')}
    engine.dispose()


@pytest.mark.parametrize('damage', [None, 'check', 'default', 'index', 'foreign_key'])
def test_complete_precreated_schema_requires_actual_constraint_and_legacy_default(tmp_path, damage):
    url = f"sqlite:///{(tmp_path / 'precreated.db').as_posix()}"
    _alembic(url, 'upgrade', 'ebc34af102b3')
    engine = create_engine(url)
    ddl = str(CreateTable(DeviceEvent.__table__).compile(dialect=engine.dialect))
    if damage == 'check':
        check = next(item for item in DeviceEvent.__table__.constraints if item.name == 'ck_event_producer')
        ddl = ddl.replace(f'CHECK ({check.sqltext})', 'CHECK (1=1)')
    elif damage == 'default':
        ddl = ddl.replace("DEFAULT 'device'", "DEFAULT 'application'")
    elif damage == 'foreign_key':
        ddl = ddl.replace('ON DELETE CASCADE', '')
    with engine.begin() as db:
        db.exec_driver_sql('DROP TABLE device_events')  # Disposable empty fixture only.
        db.exec_driver_sql(ddl)
        if damage != 'index':
            for index in DeviceEvent.__table__.indexes:
                index.create(db)
    engine.dispose()
    if damage:
        with pytest.raises(subprocess.CalledProcessError):
            _alembic(url, 'upgrade', 'head')
    else:
        _alembic(url, 'upgrade', 'head')
    engine = create_engine(url)
    with engine.connect() as db:
        assert db.scalar(text('SELECT version_num FROM alembic_version')) == (
            'ebc34af102b3' if damage else 'fcd45b0213c4')
    engine.dispose()
