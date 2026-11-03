"""Real key/DB ordering for SDK failure cleanup and non-HTTP relay consumers."""
import asyncio
from contextlib import contextmanager
import os

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.db.authority import CoreAuthorityGuard
from backend.db.module import ApplicationExtensionInstallation as Installation, ModulePackage
from backend.services import application_authority_management as authority, installation_peers
from backend.services.application_authority_keys import AuthorityReviewKeyError
from backend.tests.test_application_ui_concurrency import (
    ui_http, ui_app, managed_installed, source_subject, source_installed, adopt,
)
from backend.tests.test_application_delegations import stack, create, calls


pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Real POSIX key and file-backed SQLite leases')


@pytest.mark.parametrize('exit_kind', ['grant_denied', 'policy_error', 'unexpected', 'rollback_failure', 'uncommitted', 'committed', 'released'])
@pytest.mark.parametrize('scope', ['command:pulse', 'connector:business_api'])
def test_sdk_transaction_ends_before_key_even_on_failure(ui_app, monkeypatch, exit_kind, scope):
    s = ui_app
    adopt(s)
    checked = []
    failures_at_key = []
    injected_failure = {
        'grant_denied': authority.AuthorityManagementError('unsupported_authority'),
        'policy_error': ValueError('private policy text'),
        'unexpected': RuntimeError('private unexpected text'),
        'rollback_failure': RuntimeError('private driver failure'),
    }.get(exit_kind)
    with Session(s.engine) as db:
        # A real clean caller read must end before preparation/key acquisition.
        db.connection().exec_driver_sql('BEGIN')
        db.get(Installation, 1)
        prepare = s.manager._prepare
        def prepare_without_reader(*args, **kwargs):
            assert not db.in_transaction(), 'Routing reader survived into code preparation'
            return prepare(*args, **kwargs)
        monkeypatch.setattr(s.manager, '_prepare', prepare_without_reader)
        locked = s.manager.keys.read_locked
        @contextmanager
        def tracked_key():
            assert not db.in_transaction(), 'Caller acquired key after DB transaction'
            with locked() as key:
                try:
                    yield key
                except BaseException as error:
                    # The actual key lease must retain the caller failure while
                    # still closing this DB transaction before releasing flock.
                    failures_at_key.append(error)
                    raise
                finally:
                    assert not db.in_transaction(), 'Key released before caller transaction ended'
                    # Not just an ORM flag: a separate writer can commit now.
                    with s.engine.begin() as other:
                        other.execute(update(CoreAuthorityGuard).values(revision=CoreAuthorityGuard.revision))
                    checked.append(True)
        monkeypatch.setattr(s.manager.keys, 'read_locked', tracked_key)
        rollback = db.rollback
        fail_rollback = []
        def driver_rollback():
            if fail_rollback:
                fail_rollback.pop()
                raise injected_failure
            rollback()
        monkeypatch.setattr(db, 'rollback', driver_rollback)
        if exit_kind == 'grant_denied':
            def denied(*args, **kwargs):
                assert db.in_transaction()
                raise injected_failure
            monkeypatch.setattr(s.manager, '_require_grant', denied)

        def operation():
            with authority.effect_admission(db, 1, scope) as release:
                # This uses real UI proof verification on a separate DB snapshot,
                # not just a second shared flock with no policy read.
                if exit_kind == 'uncommitted':
                    ui_reader = authority.ApplicationAuthorityManager(
                        s.engine, uploads_root=s.root, core_version=s.manager.core_version,
                        review_key_directory=s.key_directory)
                    ui_reader.require_ui_trust(1, s.build.built_ui_sha256)
                with pytest.raises(AuthorityReviewKeyError):
                    with s.keys.locked():
                        pytest.fail('Exclusive maintenance overlapped SDK admission')
                db.execute(update(Installation).where(Installation.id == 1).values(error='private fixture mutation'))
                if exit_kind == 'rollback_failure':
                    fail_rollback.append(True)
                if exit_kind in {'policy_error', 'unexpected'}:
                    raise injected_failure
                if exit_kind in {'committed', 'released'}:
                    db.commit()
                if exit_kind == 'released':
                    release()
                    assert not db.in_transaction()
                    with s.keys.locked():
                        pass
        if exit_kind in {'grant_denied', 'policy_error'}:
            # The resource boundary still redacts its declared policy failures;
            # this does not depend on misclassifying them as key failures.
            with pytest.raises(ValueError, match='^Application resource grant is unavailable or stale$'):
                operation()
            assert failures_at_key == [injected_failure]
        elif exit_kind in {'unexpected', 'rollback_failure'}:
            with pytest.raises(RuntimeError) as error:
                operation()
            assert error.value is injected_failure
            assert failures_at_key == [injected_failure]
        else:
            operation()
            assert failures_at_key == []
        assert not fail_rollback
        assert checked == [True] and not db.in_transaction()
    with Session(s.engine) as db:
        assert db.get(Installation, 1).error == ('private fixture mutation' if exit_kind in {'committed', 'released'} else None)


def track_fences(s, monkeypatch):
    observed = []
    original = s.manager.invocation_transaction
    @contextmanager
    def tracked(db, installation_id, *, fence=None):
        assert not db.in_transaction()
        def fenced_under_key():
            assert not db.in_transaction(), 'Policy read happened before the write fence'
            with pytest.raises(AuthorityReviewKeyError):
                with s.keys.locked():
                    pytest.fail('Policy fence acquired DB before key')
            fence()
            observed.append(True)
        with original(db, installation_id, fence=fenced_under_key if fence is not None else None) as key:
            yield key
        assert not db.in_transaction()
    monkeypatch.setattr(s.manager, 'invocation_transaction', tracked)
    return observed


@pytest.mark.parametrize('ui_app', ['delegations'], indirect=True)
def test_real_delegation_has_one_key_before_both_relay_fences(stack, monkeypatch):
    s = stack
    observed = track_fences(s, monkeypatch)
    response = create(s)
    assert response.status_code == 200, response.text
    result = s.sdk.execute_delegation('c' * 32)
    assert result['status'] == 'succeeded', result
    assert observed == [True, True] and len(calls(s)) == 1


def test_peer_callback_has_key_before_both_relay_fences(ui_http, monkeypatch):
    s = ui_http
    observed = track_fences(s, monkeypatch)
    # Exercise the real internal peer callback entry, not the HTTP boundary.
    from backend.routes.application_extensions import get_settings
    with Session(s.engine) as db:
        s.sessions.append(db)
        app, package = db.get(Installation, 1), db.get(ModulePackage, 1)
        def still_current():
            return db.scalar(select(Installation.enabled).where(Installation.id == 1)) is True
        result = asyncio.run(installation_peers.invoke_application(app, package, get_settings().applications,
            'pulse_ui', {}, {'audience': 'operator', 'idempotency_key': 'fixture-once'},
            required_audience='operator', before_dispatch=still_current))
        assert result == {} and not db.in_transaction()
    assert observed == [True, True] and len(s.sent) == 1
