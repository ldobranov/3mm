"""Live, additive resource grants. Custom role names never confer system authority."""
from datetime import datetime
from sqlalchemy import select, or_
from sqlalchemy.orm import Session
from backend.db.association_tables import (
    user_roles, user_groups, group_roles, role_application_grants, role_dashboard_grants,
)
from backend.db.role import Role, Group
from backend.db.user import User
from backend.db.permission import Permission
from backend.db.module import ApplicationPermissionGrant

LEVELS = {'none': 0, 'view': 1, 'edit': 2, 'delete': 3, 'admin': 4}


def role_sources(db: Session, user_id: int) -> dict[int, list[str]]:
    user = db.get(User, user_id)
    if user is None or user.is_blocked:
        return {}
    sources: dict[int, list[str]] = {}
    for role_id, name in db.execute(select(Role.id, Role.name).join(
        user_roles, user_roles.c.role_id == Role.id).where(user_roles.c.user_id == user_id)):
        sources.setdefault(role_id, []).append(f'Role: {name}')
    for role_id, name, group_name in db.execute(select(Role.id, Role.name, Group.name)
        .join(group_roles, group_roles.c.role_id == Role.id)
        .join(Group, Group.id == group_roles.c.group_id)
        .join(user_groups, user_groups.c.group_id == Group.id)
        .where(user_groups.c.user_id == user_id)):
        sources.setdefault(role_id, []).append(f'Group: {group_name} / Role: {name}')
    return sources


def application_sources(db: Session, installation_id: int, user_id: int) -> dict[str, list[str]]:
    user = db.get(User, user_id)
    if user is None or user.is_blocked:
        return {}
    result = {p: ['Direct'] for p in db.scalars(select(ApplicationPermissionGrant.permission_id).where(
        ApplicationPermissionGrant.application_installation_id == installation_id,
        ApplicationPermissionGrant.user_id == user_id))}
    sources = role_sources(db, user_id)
    for role_id, permission_id in db.execute(select(
        role_application_grants.c.role_id, role_application_grants.c.permission_id).where(
        role_application_grants.c.installation_id == installation_id,
        role_application_grants.c.role_id.in_(sources))):
        result.setdefault(permission_id, []).extend(sources[role_id])
    return result


def dashboard_levels(db: Session, user_id: int) -> dict[int, int]:
    user = db.get(User, user_id)
    if user is None or user.is_blocked:
        return {}
    result: dict[int, int] = {}
    for display_id, level in db.execute(select(Permission.entity_id, Permission.permission_level).where(
        Permission.user_id == user_id, Permission.entity_type == 'dashboard',
        or_(Permission.expires_at.is_(None), Permission.expires_at > datetime.utcnow()))):
        result[display_id] = max(result.get(display_id, 0), LEVELS.get(level.value, 0))
    sources = role_sources(db, user_id)
    for display_id, level in db.execute(select(role_dashboard_grants.c.display_id,
        role_dashboard_grants.c.permission_level).where(role_dashboard_grants.c.role_id.in_(sources))):
        result[display_id] = max(result.get(display_id, 0), LEVELS.get(level, 0))
    return {key: level for key, level in result.items() if level > 0}
