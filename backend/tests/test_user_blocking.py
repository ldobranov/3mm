from fastapi import Depends
from backend.tests.test_session_lifecycle import make_client, login, use_test_jwt_secret
from backend.utils.auth_dep import guard_user_session
from backend.utils.jwt_utils import create_access_token
from backend.db.session import UserSession
from backend.db.audit_log import AuditLog

def test_block_revoke_unblock_and_legacy_tokens():
    client, db, admin, user = make_client()
    # Mirror Core's global guard, including a route without its own auth check.
    client.app.get('/legacy', dependencies=[Depends(guard_user_session)])(lambda: {'ok': True})
    headers = lambda token: {'Authorization': 'Bearer ' + token}
    admin_token = login(client, admin.email, 'admin-password')
    tokens = [login(client, user.email, 'viewer-password') for _ in range(2)]
    tokens.append(create_access_token(str(user.id)))
    url = f'/api/user/{user.id}/status'
    assert client.put(url, json={'is_blocked': True}, headers=headers(tokens[0])).status_code == 403
    assert client.put(f'/api/user/{admin.id}/status', json={'is_blocked': True}, headers=headers(admin_token)).status_code == 400
    assert client.put(url, json={'is_blocked': True}, headers=headers(admin_token)).status_code == 200
    assert db.query(UserSession).filter_by(user_id=user.id, is_active=True).count() == 0
    assert client.post('/api/user/login', json={'email': user.email, 'password': 'viewer-password'}).status_code == 403
    for token in tokens:
        assert client.get('/legacy', headers=headers(token)).status_code == 401
        assert client.post('/api/user/refresh', headers=headers(token)).status_code == 401
    assert client.put(url, json={'is_blocked': False}, headers=headers(admin_token)).status_code == 200
    for token in tokens:
        assert client.get('/legacy', headers=headers(token)).status_code == 401
    fresh = login(client, user.email, 'viewer-password')
    assert client.get('/legacy', headers=headers(fresh)).status_code == 200
    assert client.post(f'/api/user/{user.id}/revoke-sessions', headers=headers(admin_token)).status_code == 200
    assert client.get('/legacy', headers=headers(fresh)).status_code == 401
    assert client.post('/api/user/refresh', headers=headers(fresh)).status_code == 401
    assert client.get('/legacy', headers=headers(login(client, user.email, 'viewer-password'))).status_code == 200
    assert db.query(AuditLog).filter(AuditLog.action.like('USER_%')).count() == 3
    client.close()
    db.close()

def test_migration_preserves_existing_accounts(tmp_path):
    from backend.tests.test_migration_history import _alembic
    from sqlalchemy import create_engine, text, inspect
    url = f'sqlite:///{(tmp_path / "users.db").as_posix()}'
    _alembic(url, 'upgrade', 'ebf3a4b5c6d7')
    engine = create_engine(url)
    with engine.begin() as connection:
        # Reproduce an actual pre-feature schema, not the dynamic baseline.
        connection.execute(text('ALTER TABLE users DROP COLUMN is_blocked'))
        connection.execute(text('ALTER TABLE users DROP COLUMN token_version'))
        connection.execute(text("INSERT INTO users (username,email,role) VALUES ('existing','existing@example.invalid','admin')"))
    engine.dispose()
    _alembic(url, 'upgrade', 'head')
    with engine.connect() as connection:
        assert connection.execute(text('SELECT is_blocked, token_version FROM users')).one() == (0, 0)
    engine.dispose()
    _alembic(url, 'downgrade', 'ebf3a4b5c6d7')
    assert 'is_blocked' not in {c['name'] for c in inspect(engine).get_columns('users')}
    engine.dispose()
