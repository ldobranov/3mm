"""Guest proofs carry no reusable Core or cross-form authority."""
from dataclasses import asdict
from types import SimpleNamespace
import time

import pytest

from backend.applications.public_web import guests as public_form_guests
from packages.application_sdk import OperationContext
from packages.protocol.public_forms import GUEST_TTL_SECONDS


SCOPE = ('core', 'instance', 'incarnation', 'epoch', 'artifact', 'form', '/guest', 'https://forms.example')


@pytest.mark.parametrize('index', range(len(SCOPE)))
def test_cookie_fences_every_identity_axis(index):
    guest, cookie = public_form_guests.issue(SCOPE)
    assert public_form_guests.resolve(SCOPE, cookie) == guest
    changed = (*SCOPE[:index], 'changed', *SCOPE[index+1:])
    assert public_form_guests.resolve(changed, cookie) is None


def test_cookie_has_fixed_expiry_and_invalid_signatures_do_not_parse(monkeypatch):
    now = 1800000000
    monkeypatch.setattr(public_form_guests, 'time', SimpleNamespace(time=lambda: now))
    guest, cookie = public_form_guests.issue(SCOPE)
    assert guest.expires_at == now + GUEST_TTL_SECONDS
    assert public_form_guests.resolve(SCOPE, cookie + 'a') is None
    assert public_form_guests.resolve(SCOPE, cookie.replace(guest.guest_id, '0'*32, 1)) is None
    now += GUEST_TTL_SECONDS - 1
    assert public_form_guests.resolve(SCOPE, cookie) == guest
    now += 1
    assert public_form_guests.resolve(SCOPE, cookie) is None


def test_sdk_guest_is_anonymous_and_refuses_non_public_or_credential_context():
    guest, cookie = public_form_guests.issue(SCOPE)
    context = {'audience': 'public', 'correlation_id': 'reference', 'public_guest': asdict(guest)}
    parsed = OperationContext.from_platform(context)
    assert parsed.public_guest == guest and parsed.actor.kind == 'anonymous'
    assert not parsed.has_application_permission('configure')
    for change in ({'audience': 'internal'}, {'permission_ids': ['configure']},
                   {'public_guest': {**asdict(guest), 'cookie': cookie}},
                   {'public_guest': {**asdict(guest), 'expires_at': int(time.time())-1}}):
        with pytest.raises(ValueError):
            OperationContext.from_platform({**context, **change})
