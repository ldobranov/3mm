from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from backend.db.audit_log import AuditLog
from backend.db.device import Device
from backend.db.user import User
from backend.devices import hardware_interfaces as routes
from backend.tests.test_system_control_routes import make_client
from components.system_runtime.update_helper_client import UpdateHelperError
from backend.accounts import tokens as jwt_utils

DEVICE = 'dev_'+'a'*32
PATH = '/api/v1/devices/'+DEVICE+'/hardware-interfaces'


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(jwt_utils, 'SECRET_KEY', 'test-only-hardware-key-with-at-least-32-bytes')
    client, db, admin, viewer = make_client(tmp_path, monkeypatch)
    client.app.include_router(routes.router)
    db.add(Device(device_id=DEVICE, role='standalone', protocol_version='1.0',
                  approved_at=datetime.now(timezone.utc)))
    db.commit()
    monkeypatch.setattr(routes, 'get_settings', lambda: SimpleNamespace(updates=SimpleNamespace(helper_socket=tmp_path/'sock')))
    calls = []
    class Helper:
        def __init__(self, *_): pass
        def hardware_interfaces_status(self, device, user):
            calls.append(('inspect', device, user)); return {'device_id': device, 'supported': False}
        def enable_i2c(self, device, user, **request):
            calls.append(('enable', device, user, request)); return request['request_id']
        def restart_after_i2c(self, device, user, **request):
            calls.append(('restart', device, user, request)); return request['request_id']
    monkeypatch.setattr(routes, 'UpdateHelperClient', Helper)
    yield client, db, {'Authorization': 'Bearer '+admin}, {'Authorization': 'Bearer '+viewer}, calls
    db.close()


def payload(restart=False):
    return {'request_id': 'b'*32, 'expected_revision': 'c'*64,
        'confirmation': ('RESTART ' if restart else 'ENABLE I2C ')+DEVICE,
        **({'source_request_id': 'd'*32} if restart else {})}


def test_all_hardware_routes_require_a_current_administrator(api):
    client, db, admin, viewer, calls = api
    for suffix in ('', '/i2c/enable', '/restart'):
        for headers, status in (({}, 401), (viewer, 403)):
            response = client.get(PATH, headers=headers) if not suffix else client.post(PATH+suffix, headers=headers, json=payload(suffix == '/restart'))
            assert response.status_code == status
    assert calls == []
    user = db.get(User, 1); user.is_blocked = True; db.commit()
    assert client.get(PATH, headers=admin).status_code == 401
    assert calls == []


@pytest.mark.parametrize('suffix', ['', '/i2c/enable', '/restart'])
@pytest.mark.parametrize('revocation', ['demoted', 'blocked', 'token_version'])
def test_current_admin_revocation_prevents_helper_and_success_audit(api, suffix, revocation):
    client, db, admin, _, calls = api
    user = db.get(User, 1)
    if revocation == 'demoted':
        user.role = 'user'
    elif revocation == 'blocked':
        user.is_blocked = True
    else:
        user.token_version += 1
    db.commit()
    response = (client.post(PATH+suffix, headers=admin, json=payload(suffix == '/restart'))
                if suffix else client.get(PATH, headers=admin))
    assert response.status_code == (403 if revocation == 'demoted' else 401)
    assert calls == []
    assert db.scalars(select(AuditLog)).first() is None


def test_inspection_enable_and_restart_are_separate_and_audited(api):
    client, db, admin, _, calls = api
    assert client.get(PATH, headers=admin).status_code == 200
    assert [c[0] for c in calls] == ['inspect']
    assert client.post(PATH+'/i2c/enable', headers=admin, json=payload()).status_code == 202
    assert [c[0] for c in calls] == ['inspect', 'enable']
    assert client.post(PATH+'/restart', headers=admin, json=payload(True)).status_code == 202
    assert [c[0] for c in calls] == ['inspect', 'enable', 'restart']
    assert [a.action for a in db.scalars(select(AuditLog)).all()] == ['HARDWARE_I2C_ENABLE_REQUESTED', 'HARDWARE_RESTART_REQUESTED']
    assert all(c[1] == DEVICE for c in calls)


def test_wrong_confirmation_unknown_fields_and_revoked_device_do_not_reach_helper(api):
    client, db, admin, _, calls = api
    assert client.post(PATH+'/i2c/enable', headers=admin, json={**payload(), 'confirmation': 'yes'}).status_code == 409
    assert client.post(PATH+'/i2c/enable', headers=admin, json={**payload(), 'path': '/etc/passwd'}).status_code == 422
    device = db.scalar(select(Device)); device.revoked_at = datetime.now(timezone.utc); db.commit()
    assert client.get(PATH, headers=admin).status_code == 409
    assert calls == []


@pytest.mark.parametrize('restarting', [False, True])
def test_helper_loss_reports_unconfirmed_without_retry_or_reboot(api, monkeypatch, restarting):
    client, db, admin, _, calls = api
    class Helper:
        def __init__(self, *_): pass
        def enable_i2c(self, *args, **kwargs):
            calls.append('one'); raise UpdateHelperError('lost response')
        restart_after_i2c = enable_i2c
    monkeypatch.setattr(routes, 'UpdateHelperClient', Helper)
    response = client.post(PATH+('/restart' if restarting else '/i2c/enable'),
                           headers=admin, json=payload(restarting))
    assert response.status_code == 409 and 'do not resend' in response.json()['detail']
    assert calls == ['one'] and db.scalars(select(AuditLog)).all() == []
