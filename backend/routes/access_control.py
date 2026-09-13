"""System-admin management of custom, resource-scoped access."""
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, delete
from sqlalchemy.orm import Session
from backend.utils.auth_dep import require_admin
from backend.utils.db_utils import get_db
from backend.db.user import User
from backend.db.role import Role, Group
from backend.db.display import Display
from backend.db.audit_log import AuditLog
from backend.db.association_tables import (
    user_roles, user_groups, group_roles, role_application_grants, role_dashboard_grants,
)
from backend.routes.application_extensions import _installation, _active_package, _definition
from backend.services.access_control import application_sources

router = APIRouter(prefix='/access', tags=['access'])


class Enabled(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool


class Binding(Enabled):
    kind: Literal['user-role', 'user-group', 'group-role']
    subject_id: int = Field(gt=0)
    target_id: int = Field(gt=0)


class DashboardGrant(BaseModel):
    model_config = ConfigDict(extra='forbid')
    level: Literal['none', 'view', 'edit', 'delete', 'admin']


def require_row(db, model, identifier):
    row = db.get(model, identifier)
    if row is None:
        raise HTTPException(404, 'Access subject or resource was not found')
    return row


def audit(db, admin, action, changes):
    db.add(AuditLog(user_id=admin.id, action=action, entity_type='access', changes=changes))
    db.commit()


@router.get('')
def catalog(response: Response, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    response.headers['Cache-Control'] = 'no-store'
    return {
        'roles': [{'id': r.id, 'name': r.name, 'is_system_role': bool(r.is_system_role)} for r in db.scalars(select(Role).order_by(Role.name))],
        'groups': [{'id': g.id, 'name': g.name} for g in db.scalars(select(Group).order_by(Group.name))],
        'dashboards': [{'id': d.id, 'name': d.title} for d in db.scalars(select(Display).order_by(Display.id))],
        **{name: [dict(row) for row in db.execute(select(table)).mappings()] for name, table in (
            ('user_roles', user_roles), ('user_groups', user_groups), ('group_roles', group_roles),
            ('application_grants', role_application_grants), ('dashboard_grants', role_dashboard_grants))},
    }


@router.put('/bindings')
def set_binding(payload: Binding, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    table, subject, target, subject_model, target_model = {
        'user-role': (user_roles, 'user_id', 'role_id', User, Role),
        'user-group': (user_groups, 'user_id', 'group_id', User, Group),
        'group-role': (group_roles, 'group_id', 'role_id', Group, Role),
    }[payload.kind]
    require_row(db, subject_model, payload.subject_id)
    require_row(db, target_model, payload.target_id)
    values = {subject: payload.subject_id, target: payload.target_id}
    condition = (table.c[subject] == payload.subject_id) & (table.c[target] == payload.target_id)
    if payload.enabled:
        if db.execute(select(table).where(condition)).first() is None:
            db.execute(table.insert().values(**values))
    else:
        db.execute(delete(table).where(condition))
    audit(db, admin, 'ACCESS_BINDING', payload.model_dump())
    return {'saved': True}


@router.put('/roles/{role_id}/applications/{module_id}/permissions/{permission_id}')
def set_application_grant(role_id: int, module_id: str, permission_id: str, payload: Enabled,
                          admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    require_row(db, Role, role_id)
    installation = _installation(db, module_id)
    # Removal also works after an application update retires a permission.
    if payload.enabled:
        definition = _definition(_active_package(db, installation))
        if permission_id not in {p.permission_id for p in definition.permissions}:
            raise HTTPException(422, 'Permission is not declared by the active application')
    table = role_application_grants
    condition = (table.c.role_id == role_id) & (table.c.installation_id == installation.id) & (table.c.permission_id == permission_id)
    db.execute(delete(table).where(condition))
    if payload.enabled:
        db.execute(table.insert().values(role_id=role_id, installation_id=installation.id, permission_id=permission_id))
    audit(db, admin, 'ACCESS_APP_GRANT', {'role_id': role_id, 'module_id': module_id, 'permission_id': permission_id, 'enabled': payload.enabled})
    return {'saved': True}


@router.get('/applications/{module_id}')
def application_catalog(module_id: str, response: Response, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    installation = _installation(db, module_id)
    definition = _definition(_active_package(db, installation))
    response.headers['Cache-Control'] = 'no-store'
    return {'installation_id': installation.id, 'permissions': [p.model_dump() for p in definition.permissions],
            'routes': [r.model_dump() for r in definition.routes]}


@router.get('/users/{user_id}/applications/{module_id}')
def effective_application(user_id: int, module_id: str, response: Response,
                          admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = require_row(db, User, user_id)
    installation = _installation(db, module_id)
    _active_package(db, installation)
    response.headers['Cache-Control'] = 'no-store'
    return {'sources': application_sources(db, installation.id, user_id),
            'system_admin': user.role == 'admin' and not user.is_blocked, 'blocked': user.is_blocked}


@router.put('/roles/{role_id}/dashboards/{display_id}')
def set_dashboard_grant(role_id: int, display_id: int, payload: DashboardGrant,
                        admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    require_row(db, Role, role_id)
    require_row(db, Display, display_id)
    table = role_dashboard_grants
    db.execute(delete(table).where(table.c.role_id == role_id, table.c.display_id == display_id))
    if payload.level != 'none':
        db.execute(table.insert().values(role_id=role_id, display_id=display_id, permission_level=payload.level))
    audit(db, admin, 'ACCESS_DASHBOARD_GRANT', {'role_id': role_id, 'display_id': display_id, 'level': payload.level})
    return {'saved': True}
