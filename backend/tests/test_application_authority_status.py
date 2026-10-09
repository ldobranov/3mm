"""Read-only UI status never supplies or resurrects executable authority."""
import os
import json

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.db.application_authority_grant import ApplicationNativeReview as Native, ApplicationAuthorityGrant as Grant
from backend.tests.test_application_authority_management import (
    installed, source_subject, source_installed, native, activate_grant, command, identity,
)
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.services.application_commands import submit_command

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
