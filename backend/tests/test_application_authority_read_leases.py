"""Real read-only grant discovery overlaps UI trust, not key replacement/writes.

Only provider readiness is doubled. Package/native/grant verification, file
locks, transaction boundaries and revocation use the actual Core adapters.
"""
from concurrent.futures import ThreadPoolExecutor
import os

import pytest
from sqlalchemy import event, select, update
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from backend.db.authority import CoreAuthorityGuard
from backend.db.device import DeviceCommand
from backend.applications.authority import management as authority
from backend.applications.resources import providers as application_resource_providers
from backend.applications.authority.keys import AuthorityReviewKeyError, KEY_NAME
from backend.applications.commands.discovery import discover_selected_command
from backend.applications.resources.discovery import discover_resources
from backend.tests.test_application_ui_authority import (
    ui_app, managed_installed, source_subject, source_installed, adopt, identity,
)


pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Real POSIX review-key locks and SQLite snapshots')
VIEWS = ('status', 'command', 'resources')


@pytest.fixture
def read_app(ui_app, monkeypatch):
    s = ui_app
    s.reviewed = adopt(s)
    # No Runtime/host probe, process, physical command or device is needed.
    monkeypatch.setattr(application_resource_providers, 'observe', lambda kind, settings: 'ready')
    return s


def observe(s, view):
    if view == 'status':
        return s.manager.inspect(1)
    if view == 'command':
        return discover_selected_command(s.engine, 1, 'a' * 24, 'pulse')
    return discover_resources(s.engine, 1, 'a' * 24, ['command:pulse', 'connector:business_api'])


def granted(s, view, value):
    if view == 'status':
        assert value['grant_effective'] is True and value['review_available'] is True
    elif view == 'command':
        assert value['access'] == 'granted'
        assert value['selected_device_id'] == s.configuration['TARGET_DEVICE_ID']
        assert len(value['candidates']) == 1
    else:
        command, connector = value['resources']
        assert command['access'] == connector['access'] == 'granted'
        assert command['selected_resource_id'] == s.configuration['TARGET_DEVICE_ID']


def denied(view, value):
    if view == 'status':
        assert value['grant_effective'] is False
    elif view == 'command':
        assert value['access'] == 'required'
        assert value['selected_device_id'] is None and value['candidates'] == []
    else:
        assert all(row['access'] == 'required' and row['provider'] is None
            and row['selected_resource_id'] is None for row in value['resources'])


def change_authority(s, change):
    if change == 'grant':
        current = s.manager.inspect(1)
        s.manager.revoke(1, actor_token=s.token, request_id=identity(),
            expected_revision=current['grant_record_revision'])
    elif change == 'native':
        s.manager.revoke_native_review(1, actor_token=s.token, request_id=identity(),
            native_review_id=s.reviewed['native_review_id'], expected_revision=s.reviewed['native_revision'])
    elif change == 'key':
        s.keys.rotate(expected_key_id=s.keys.identity().key_id)
    else:
        with s.engine.begin() as db:
            db.execute(update(CoreAuthorityGuard).values(generation=identity()))


@pytest.mark.parametrize('view', VIEWS)
def test_discovery_completes_while_a_real_ui_reader_still_owns_the_key(read_app, monkeypatch, view):
    s = read_app
    statements, checked = [], []
    subject = s.manager._subject
    key_before = (s.key_directory / KEY_NAME).read_bytes()

    def read_only_subject(db, key, *args, **kwargs):
        assert key.read_only is True, 'Read-only discovery acquired an exclusive signing lease'
        # _read_snapshot has already opened the transaction on its Connection.
        # The bound ORM Session joins it lazily on the first actual query.
        snapshot = db.get_bind()
        assert isinstance(snapshot, Connection) and snapshot.in_transaction()
        assert snapshot.connection.driver_connection.in_transaction is True
        assert snapshot.exec_driver_sql('PRAGMA query_only').scalar_one() == 1
        result = subject(db, key, *args, **kwargs)
        assert db.in_transaction()
        checked.append(True)
        return result

    def sql(_connection, _cursor, statement, *_args):
        if statement.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE', 'CREATE')):
            statements.append(statement)

    monkeypatch.setattr(s.manager, '_subject', read_only_subject)
    event.listen(s.engine, 'before_cursor_execute', sql)
    try:
        with ThreadPoolExecutor(max_workers=1) as workers:
            # An actual compiled-UI/native-trust snapshot holds SH in this
            # thread until the other thread's complete discovery has returned.
            with s.manager.ui_trust_snapshot(1, s.build.built_ui_sha256):
                result = workers.submit(observe, s, view).result(timeout=10)
                granted(s, view, result)
                with pytest.raises(AuthorityReviewKeyError):
                    with s.keys.locked():
                        pytest.fail('Exclusive SDK/administration lease overlapped a current UI reader')
    finally:
        event.remove(s.engine, 'before_cursor_execute', sql)
    assert len(checked) >= (2 if view == 'resources' else 1)
    assert statements == [] and (s.key_directory / KEY_NAME).read_bytes() == key_before
    with Session(s.engine) as db:
        assert db.scalar(select(DeviceCommand.id)) is None


@pytest.mark.parametrize('view', VIEWS)
def test_exclusive_maintenance_still_fences_readers_without_cached_authority(read_app, view):
    s = read_app
    granted(s, view, observe(s, view))
    with s.keys.locked():
        # A separate real flock, not a fake exception or an increased timeout.
        denied(view, observe(s, view))
    granted(s, view, observe(s, view))


@pytest.mark.parametrize('view', VIEWS)
@pytest.mark.parametrize('change', ('grant', 'native', 'key', 'recovery'))
def test_completed_reads_never_cache_authority_across_revocation_or_replacement(read_app, view, change):
    s = read_app
    granted(s, view, observe(s, view))
    change_authority(s, change)
    denied(view, observe(s, view))


@pytest.mark.parametrize('change', ('grant', 'native', 'key', 'recovery'))
def test_resource_probe_has_no_key_or_sql_lease_and_post_probe_authority_wins(read_app, monkeypatch, change):
    s = read_app
    calls = []

    def probe(kind, settings):
        assert kind == 'connector'
        # Key EX and a separate committed SQLite writer must both be possible
        # here. The new SH lease must not stretch across even metadata IPC.
        with s.keys.locked(), s.engine.begin() as db:
            db.execute(update(CoreAuthorityGuard).values(revision=CoreAuthorityGuard.revision))
        change_authority(s, change)
        calls.append(kind)
        return 'ready'

    monkeypatch.setattr(application_resource_providers, 'observe', probe)
    with pytest.raises((authority.AuthorityManagementError, AuthorityReviewKeyError)):
        observe(s, 'resources')
    assert calls == ['connector']
