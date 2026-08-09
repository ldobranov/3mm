from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func
from backend.db.base import Base

class ModulePackage(Base):
    __tablename__ = "module_packages"
    id = Column(Integer, primary_key=True)
    module_id = Column(String(160), nullable=False, index=True)
    version = Column(String(64), nullable=False)
    manifest = Column(JSON, nullable=False)
    sha256 = Column(String(64), nullable=False, unique=True)
    size_bytes = Column(Integer, nullable=False)
    file_path = Column(Text, nullable=False)
    registrations = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (UniqueConstraint("module_id", "version", name="uq_module_package_version"),)

class ModuleInstallation(Base):
    __tablename__ = "module_installations"
    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    module_package_id = Column(Integer, ForeignKey("module_packages.id"), nullable=False)
    module_id = Column(String(160), nullable=False)
    installed_version = Column(String(64), nullable=True)
    desired_version = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, default="queued")
    enabled = Column(Boolean, nullable=False, default=True)
    command_id = Column(String(64), nullable=True, index=True)
    error = Column(Text, nullable=True)
    data_retained = Column(Boolean, nullable=False, default=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    __table_args__ = (UniqueConstraint("device_id", "module_id", name="uq_device_module_installation"),)
