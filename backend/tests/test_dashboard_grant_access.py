from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
import backend.database
from backend.db.base import Base
from backend.db.user import User
from backend.db.display import Display
from backend.db.widget import Widget
from backend.db.permission import Permission, PermissionLevel
from backend.routes.display_routes import router, get_db
from backend.utils.jwt_utils import create_access_token
from backend.utils.db_utils import get_db as auth_get_db


@pytest.mark.parametrize('level,expired,can_read,can_edit', [
    (PermissionLevel.NONE, False, False, False),
    (PermissionLevel.ADMIN, True, False, False),
    (PermissionLevel.VIEW, False, True, False),
    (PermissionLevel.EDIT, False, True, True),
])
def test_dashboard_grants_apply_to_lists_reads_and_writes(level, expired, can_read, can_edit):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        owner = User(username='owner', email='owner@example.invalid', role='admin')
        viewer = User(username='viewer', email='viewer@example.invalid', role='user')
        db.add_all([owner, viewer])
        db.flush()
        display = Display(user_id=owner.id, title='Private', slug='private', is_public=False)
        db.add(display)
        db.flush()
        widget = Widget(display_id=display.id, type='TEXT', config={})
        db.add(widget)
        db.add(Permission(user_id=viewer.id, entity_type='dashboard', entity_id=display.id,
                          permission_level=level, expires_at=datetime.utcnow() - timedelta(days=1) if expired else None))
        db.commit()
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[auth_get_db] = lambda: db
        # A stale admin claim must not widen the current user's access.
        headers = {'Authorization': 'Bearer ' + create_access_token(str(viewer.id), {'role': 'admin'})}
        with TestClient(app) as client:
            listed = client.get('/display/read', headers=headers)
            assert listed.status_code == 200
            assert bool(listed.json()['items']) == can_read
            assert client.get(f'/api/displays/{display.id}', headers=headers).status_code == (200 if can_read else 403)
            assert client.get(f'/api/displays/{display.id}/widgets', headers=headers).status_code == (200 if can_read else 403)
            assert client.patch(f'/api/widgets/{widget.id}', json={'config': {'text': 'changed'}}, headers=headers).status_code == (200 if can_edit else 403)
            assert client.delete(f'/api/widgets/{widget.id}', headers=headers).status_code == 403
            display.is_public = True
            db.commit()
            assert client.get('/display/read').json()['items']
            assert client.get(f'/api/displays/{display.id}', headers=headers).status_code == 200
            assert client.patch(f'/api/displays/{display.id}', json={'title': 'changed'}, headers=headers).status_code == 403
    engine.dispose()
