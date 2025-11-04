# backend/db/extension.py
import os
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from backend.db.base import Base

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///backend/mega_monitor.db")
if DATABASE_URL.startswith("postgresql"):
    from sqlalchemy.dialects.postgresql import JSONB as JSON
else:
    from sqlalchemy.dialects.sqlite import JSON

class Extension(Base):
    __tablename__ = "extensions"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)  # 'widget', 'theme', 'backend-api', etc.
    version = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    author = Column(String, nullable=True)
    manifest = Column(JSON, nullable=False)  # Full manifest JSON
    file_path = Column(String, nullable=False)  # Path to uploaded extension file
    status = Column(String, default="inactive")  # 'active', 'inactive', 'error', 'quarantined'
    error_message = Column(Text, nullable=True)
    is_enabled = Column(Boolean, default=False)
    integrity_hash = Column(String, nullable=True)  # SHA256 hash for integrity checking
    security_status = Column(String, default="unknown")  # 'safe', 'warning', 'dangerous', 'quarantined'
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="extensions")