from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.sql import func

from backend.db.base import Base


class RuntimeExtensionDefinition(Base):
    __tablename__ = "runtime_extension_definitions"

    id = Column(Integer, primary_key=True)
    module_id = Column(String(160), nullable=False, index=True)
    version = Column(String(64), nullable=False)
    definition = Column(JSON, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    is_selected = Column(Boolean, nullable=False, default=True, index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("module_id", "version", name="uq_runtime_extension_version"),
        Index(
            "uq_runtime_extension_active_module",
            "module_id",
            unique=True,
            sqlite_where=text("enabled = 1"),
            postgresql_where=text("enabled"),
        ),
        Index(
            "uq_runtime_extension_selected_module",
            "module_id",
            unique=True,
            sqlite_where=text("is_selected = 1"),
            postgresql_where=text("is_selected"),
        ),
    )


class RuntimeEntityRecord(Base):
    __tablename__ = "runtime_entity_records"

    id = Column(Integer, primary_key=True)
    module_id = Column(String(160), nullable=False, index=True)
    entity_id = Column(String(64), nullable=False, index=True)
    record_id = Column(String(32), nullable=False)
    data = Column(JSON, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "module_id", "entity_id", "record_id", name="uq_runtime_entity_record"
        ),
    )
