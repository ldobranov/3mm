from sqlalchemy import select
from backend.tests.test_application_access import environment, headers
from backend.db.user import User
from backend.db.role import Role, Group
from backend.db.display import Display
from backend.db.widget import Widget
from backend.db.association_tables import role_application_grants, role_dashboard_grants
from backend.routes.access_control import router as access_router
from backend.routes.display_routes import router as display_router
from backend.database import get_db as display_db
from backend.utils.jwt_utils import create_access_token
from backend.services.application_access import (
    ApplicationPrincipal, can_access_application_route, can_access_application_operation,
)
from three_mm_protocol import ApplicationRouteV1, ApplicationOperationV1


def test_two_groups_live_inheritance_scoping_revocation_and_blocking(monkeypatch, tmp_path):
    client, db, engine, admin, user, installation, package, admin_token, token = environment(monkeypatch, tmp_path)
    client.app.include_router(access_router, prefix='/api')
    client.app.include_router(display_router)
    client.app.dependency_overrides[display_db] = lambda: db
    other = User(username='other', email='other@example.invalid', role='user')
    role = Role(name='admin')  # A custom name cannot confer system admin.
    group = Group(name='Staff')
    other_group = Group(name='Visitors')
    db.add_all([other, role, group, other_group]); db.commit()
    display = Display(user_id=admin.id, title='Private', slug='private', is_public=False)
    db.add(display); db.commit()
    widget = Widget(display_id=display.id, type='TEXT', config={})
    db.add(widget); db.commit()
    admin_headers = headers(admin_token)
    base = f'/api/v1/application-extensions/{package.module_id}'
    grant_path = f'/api/access/roles/{role.id}/applications/{package.module_id}/permissions/records_manage'
    operation = base + '/operator/operations/approve'
    request = {'payload': {}, 'idempotency_key': 'scope-test-1'}
    try:
        assert client.get('/api/access', headers=headers(token)).status_code == 403
        assert client.put(grant_path, json={'enabled': True}, headers=headers(token)).status_code == 403
        for kind, subject, target in [('group-role', group.id, role.id), ('user-group', user.id, group.id), ('user-group', other.id, other_group.id)]:
            assert client.put('/api/access/bindings', json={'kind': kind, 'subject_id': subject, 'target_id': target, 'enabled': True}, headers=admin_headers).status_code == 200
        assert client.put(grant_path, json={'enabled': True}, headers=admin_headers).status_code == 200
        assert client.put(grant_path.replace('records_manage', 'not_declared'), json={'enabled': True}, headers=admin_headers).status_code == 422
        assert client.post(operation, json=request, headers=headers(token)).status_code == 200
        other_token = create_access_token(str(other.id), {'role': 'admin'})
        assert client.post(operation, json=request, headers=headers(other_token)).status_code == 403
        assert client.post(base + '/operations/approve', json=request, headers=headers(token)).status_code == 403
        assert client.get(base + '/access', headers=headers(token)).json()['allowed_route_ids'] == ['operations']
        sources = client.get(f'/api/access/users/{user.id}/applications/{package.module_id}', headers=admin_headers).json()['sources']
        assert sources['records_manage'] == ['Group: Staff / Role: admin']
        assert client.put(f'/api/access/roles/{role.id}/dashboards/{display.id}', json={'level': 'edit'}, headers=admin_headers).status_code == 200
        assert client.get('/display/read', headers=headers(token)).json()['items']
        assert client.get('/display/read', headers=headers(other_token)).json()['items'] == []
        assert client.patch(f'/api/widgets/{widget.id}', json={'config': {'text': 'ok'}}, headers=headers(token)).status_code == 200
        assert client.delete(f'/api/widgets/{widget.id}', headers=headers(token)).status_code == 403
        user.is_blocked = True; db.commit()
        assert client.post(operation, json=request, headers=headers(token)).status_code == 401
        user.is_blocked = False; db.commit()
        assert client.put('/api/access/bindings', json={'kind': 'user-group', 'subject_id': user.id, 'target_id': group.id, 'enabled': False}, headers=admin_headers).status_code == 200
        assert client.post(operation, json=request, headers=headers(token)).status_code == 403
        assert client.get('/display/read', headers=headers(token)).json()['items'] == []
        assert client.patch(f'/api/widgets/{widget.id}', json={'config': {}}, headers=headers(token)).status_code == 403
        # Direct role assignment uses the same resolver, with no login refresh.
        assert client.put('/api/access/bindings', json={'kind': 'user-role', 'subject_id': user.id, 'target_id': role.id, 'enabled': True}, headers=admin_headers).status_code == 200
        assert client.post(operation, json=request, headers=headers(token)).status_code == 200
        assert client.put(grant_path, json={'enabled': False}, headers=admin_headers).status_code == 200
        assert client.post(operation, json=request, headers=headers(token)).status_code == 403
        # Removing the installation must not leave grants for a recycled SQLite id.
        assert client.put(grant_path, json={'enabled': True}, headers=admin_headers).status_code == 200
        from backend.routes import application_extensions
        monkeypatch.setattr(application_extensions.UpdateHelperClient, 'uninstall_application_extension', lambda *args: None)
        assert client.delete(base, headers=admin_headers).status_code == 200
        assert not db.execute(select(role_application_grants)).all()
        from backend.routes.user import router as user_router
        client.app.include_router(user_router, prefix='/api/user')
        owned = Display(user_id=other.id, title='Deleted owner', slug='owned', is_public=False)
        db.add(owned); db.commit()
        assert client.put(f'/api/access/roles/{role.id}/dashboards/{owned.id}', json={'level': 'view'}, headers=admin_headers).status_code == 200
        owned_id = owned.id
        assert client.delete(f'/api/user/delete/{other.id}', headers=admin_headers).status_code == 200
        assert not db.execute(select(role_dashboard_grants).where(role_dashboard_grants.c.display_id == owned_id)).all()
    finally:
        client.close(); db.close(); engine.dispose()


def test_delegation_is_explicit_and_never_changes_administrator_semantics():
    principal = ApplicationPrincipal(kind='user', user_id=1)
    permissions = frozenset({'configuration_manage'})
    route = ApplicationRouteV1(route_id='management', entrypoint_id='management', audience='operator', required_permissions=('configuration_manage',))
    assert can_access_application_route(route, principal, module_id='org.example.app', permission_ids=permissions)
    assert not can_access_application_route(route, principal, module_id='org.example.app')
    assert not can_access_application_route(route.model_copy(update={'audience': 'administrator'}), principal, module_id='org.example.app', permission_ids=permissions)
    operation = ApplicationOperationV1(operation_id='settings_write', kind='command', audiences=('operator', 'administrator'), required_permission='configuration_manage', idempotency='required')
    assert can_access_application_operation(operation, principal, audience='operator', permission_ids=permissions)
    assert not can_access_application_operation(operation, principal, audience='administrator', permission_ids=permissions)
