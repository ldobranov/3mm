"""Read-only UI status never supplies or resurrects executable authority."""
import os
import json

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from backend.db.application_authority_grant import ApplicationNativeReview as Native, ApplicationAuthorityGrant as Grant
from backend.tests.test_application_authority_management import (
    installed, source_subject, source_installed, native, activate_grant, command, identity,
)
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.services.application_commands import submit_command
from backend.db.authority import CoreAuthorityGuard
from backend.services.application_authority_keys import KEY_NAME, AuthorityReviewKeyError
from backend.services.application_authority_management import ApplicationAuthorityManager, AuthorityManagementError
from backend.services.authority_metadata import AuthorityMetadataError

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Requires real POSIX Core key ownership')


def test_status_lists_only_authentic_current_native_reviews_and_actual_lifecycle(installed):
    s = installed
    assert s.manager.inspect(1)['native_reviews'] == []
    valid, corrupt, revoked = native(s), native(s), native(s)
    s.manager.revoke_native_review(1, actor_token=s.token, request_id=identity(),
        native_review_id=revoked['native_review_id'], expected_revision=revoked['native_revision'])
    with s.engine.begin() as db:
        db.execute(update(Native).where(Native.review_id == corrupt['native_review_id']).values(payload='{}'))
        db.execute(update(Installation).values(status='disabled', enabled=False))
    status = s.manager.inspect(1)
    assert status['native_reviews'] == [{'native_review_id': valid['native_review_id'], 'revision': valid['native_revision']}]
    assert status['installation_status'] == 'disabled' and not status['installation_enabled']
    assert not status['grant_effective']


@pytest.mark.parametrize('fault', ['rotation', 'tamper'])
def test_unreadable_grants_remain_denied_but_do_not_block_fresh_review_chooser(installed, fault):
    s = installed
    activate_grant(s)
    if fault == 'rotation':
        s.keys.rotate(expected_key_id=s.keys.identity().key_id)
    else:
        with s.engine.begin() as db:
            db.execute(update(Grant).values(payload='{}'))
    n = native(s)
    status = s.manager.inspect(1)
    assert status['grant_state'] == 'unavailable' and not status['grant_effective']
    assert status['grant_record_revision'] is None
    assert n['native_review_id'] in [entry['native_review_id'] for entry in status['native_reviews']]
    with Session(s.engine) as db:
        with pytest.raises(ValueError):
            submit_command(db, db.get(Installation, 1), command())
        assert db.scalars(select(Grant)).one().revision == 2


@pytest.mark.parametrize('mode', ['compatibility', 'review_required', 'enforced'])
@pytest.mark.parametrize('fault', ['missing', 'corrupt', 'recovery'])
def test_status_only_preserves_actual_mode_and_never_repairs_or_authorizes(installed, mode, fault):
    s = installed
    activate_grant(s)
    with s.engine.begin() as db:
        db.execute(update(Installation).values(authority_mode=mode))
    path = s.key_directory / KEY_NAME
    if fault == 'missing':
        path.unlink()  # Disposable fixture only, never a live Core key.
    elif fault == 'corrupt':
        path.write_text('{}')
    else:
        with s.engine.begin() as db:
            db.execute(update(CoreAuthorityGuard).values(generation=identity()))
    before = path.read_bytes() if path.exists() else None
    with s.engine.connect() as db:
        dump_before = list(db.connection.driver_connection.iterdump())
    result = s.manager.inspect(1)
    assert result['mode'] == mode and result['installation_enabled'] is True
    assert result['artifact_sha256'] == s.validated.sha256
    assert result['review_available'] is False
    assert result['review_blockers'] == ['review_key_unavailable']
    assert not result['grant_effective'] and result['grant_record_revision'] is None
    assert result['grant_state'] == 'unavailable'
    assert result['scopes'] == result['native_reviews'] == []
    assert (path.read_bytes() if path.exists() else None) == before
    with s.engine.connect() as db:
        assert list(db.connection.driver_connection.iterdump()) == dump_before
    with pytest.raises((AuthorityReviewKeyError, AuthorityManagementError)):
        native(s)
    if mode != 'compatibility':
        with Session(s.engine) as db, pytest.raises(ValueError):
            submit_command(db, db.get(Installation, 1), command())


def test_unsupported_frontend_has_read_only_status_not_an_adoption_prompt(source_subject):
    s = source_subject
    assert s.validated.compiled_ui is not None
    Grant.__table__.create(s.engine, checkfirst=True)
    s.keys.provision()
    manager = ApplicationAuthorityManager(s.engine, uploads_root=s.root,
        core_version='0.3.0', review_key_directory=s.key_directory)
    result = manager.inspect(1)
    assert result['mode'] == 'compatibility' and result['installation_status'] == 'active'
    assert result['review_blockers'] == ['unsupported_authority']
    assert result['review_available'] is False and not result['grant_effective']
    assert result['scopes'] == result['native_reviews'] == []


@pytest.mark.parametrize('fault', ['artifact', 'guard'])
def test_status_only_still_refuses_invalid_artifact_and_missing_recovery_metadata(installed, fault):
    s = installed
    (s.key_directory / KEY_NAME).unlink()
    if fault == 'artifact':
        s.archive.write_bytes(b'not a package')
    else:
        with s.engine.begin() as db:
            db.execute(delete(CoreAuthorityGuard))
    with pytest.raises((AuthorityManagementError, AuthorityMetadataError)):
        s.manager.inspect(1)


def test_status_only_api_still_requires_real_administrator_and_never_enables_mutations(installed):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.routes.application_authority import router
    from backend.utils.db_utils import get_db
    s = installed
    (s.key_directory / KEY_NAME).unlink()
    app = FastAPI()
    app.include_router(router)
    def database():
        with Session(s.engine) as db:
            yield db
    app.dependency_overrides[get_db] = database
    base = '/api/v1/application-extensions/' + s.validated.manifest.module_id + '/authority'
    with TestClient(app) as client:
        assert client.get(base).status_code == 401
        assert client.get(base, headers={'Authorization': 'Bearer ' + s.user_token}).status_code == 403
        headers = {'Authorization': 'Bearer ' + s.token}
        response = client.get(base, headers=headers)
        assert response.status_code == 200
        assert response.headers['cache-control'] == 'no-store'
        assert response.json()['review_available'] is False
        response = client.post(base + '/reviews', headers=headers,
            json={'request_id': identity(), 'native_review_id': identity(), 'scopes': []})
        assert response.status_code == 409
