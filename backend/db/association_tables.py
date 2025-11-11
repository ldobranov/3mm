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
