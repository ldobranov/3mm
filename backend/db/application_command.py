"""Persistent physical command authority, separate from user permissions."""
from sqlalchemy import Column, Integer, String, ForeignKey, Boolean
from backend.db.base import Base


class ApplicationCommandEpoch(Base):
    __tablename__ = 'application_command_epochs'
    installation_id = Column(Integer, ForeignKey('application_extension_installations.id', ondelete='CASCADE'), primary_key=True)
    generation = Column(String(32), nullable=False)


class ApplicationCommandRequest(Base):
    __tablename__ = 'application_command_requests'
    command_id = Column(String(64), ForeignKey('device_commands.command_id', ondelete='CASCADE'), primary_key=True)
    installation_id = Column(Integer, ForeignKey('application_extension_installations.id', ondelete='CASCADE'), nullable=False)
    generation = Column(String(32), nullable=False)
    package_id = Column(Integer, ForeignKey('module_packages.id'), nullable=False)
    claimed = Column(Boolean, nullable=False, default=False)
    passage_event_id = Column(String(64), nullable=True)
