from sqlalchemy import Table, Column, Integer, ForeignKey
from backend.db.base import Base
import logging

logging.basicConfig(level=logging.INFO)
logging.info("Creating user_roles table with dependencies on users and roles.")

user_roles = Table(
    'user_roles', Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id')),
    Column('role_id', Integer, ForeignKey('roles.id'))
)
