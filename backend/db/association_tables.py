"""
Association tables for role and group permissions
"""
from sqlalchemy import Table, Column, Integer, String, ForeignKey
from backend.db.base import Base

# User roles association
user_roles = Table(
    'user_roles',
    Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id'), primary_key=True),
    Column('role_id', Integer, ForeignKey('roles.id'), primary_key=True)
)

# User groups association
user_groups = Table(
    'user_groups',
    Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id'), primary_key=True),
    Column('group_id', Integer, ForeignKey('groups.id'), primary_key=True)
)

# Role permissions association
role_permissions = Table(
    'role_permissions',
    Base.metadata,
    Column('role_id', Integer, ForeignKey('roles.id'), primary_key=True),
    Column('entity_type', String(50), nullable=False),
    Column('entity_id', Integer, nullable=False),
    Column('permission_level', String(20), default="view")
)

# Group permissions association
group_permissions = Table(
    'group_permissions',
    Base.metadata,
    Column('group_id', Integer, ForeignKey('groups.id'), primary_key=True),
    Column('entity_type', String(50), nullable=False),
    Column('entity_id', Integer, nullable=False),
    Column('permission_level', String(20), default="view")
)

# Scoped grants are separate from the legacy single-row permission tables.
group_roles = Table(
    'group_roles', Base.metadata,
    Column('group_id', Integer, ForeignKey('groups.id', ondelete='CASCADE'), primary_key=True),
    Column('role_id', Integer, ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True),
)
role_application_grants = Table(
    'role_application_grants', Base.metadata,
    Column('role_id', Integer, ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True),
    Column('installation_id', Integer, ForeignKey('application_extension_installations.id', ondelete='CASCADE'), primary_key=True),
    Column('permission_id', String(100), primary_key=True),
)
role_dashboard_grants = Table(
    'role_dashboard_grants', Base.metadata,
    Column('role_id', Integer, ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True),
    Column('display_id', Integer, ForeignKey('displays.id', ondelete='CASCADE'), primary_key=True),
    Column('permission_level', String(20), nullable=False),
)
