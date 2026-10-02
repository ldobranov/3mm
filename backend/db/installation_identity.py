"""Whole-Core installation identity, independent of Agent/application instances."""

from sqlalchemy import CheckConstraint, Column, DateTime, Integer, String, Text

from backend.db.base import Base


class CoreInstallationIdentity(Base):
    __tablename__ = "core_installation_identity"
    __table_args__ = (
        CheckConstraint("singleton_id = 1", name="ck_installation_identity_singleton"),
    )

    singleton_id = Column(Integer, primary_key=True)
    installation_id = Column(String(37), nullable=False, unique=True)
    identity_version = Column(Integer, nullable=False)
    key_generation = Column(Integer, nullable=False)
    key_id = Column(String(64), nullable=False)
    public_key = Column(String(44), nullable=False)
    encrypted_private_key = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
