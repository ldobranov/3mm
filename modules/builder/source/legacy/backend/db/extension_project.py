"""Persistent editable projects and immutable build history for AI extensions."""

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.db.base import Base


class ExtensionProject(Base):
    __tablename__ = "extension_projects"

    id = Column(Integer, primary_key=True)
    project_id = Column(String(64), nullable=False, unique=True, index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    slug = Column(String(120), nullable=False, unique=True, index=True)
    project_type = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False, default="draft", index=True)
    spec = Column(JSON, nullable=False, default=dict)
    current_version = Column(String(64), nullable=False, default="0.0.0")
    revision = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    files = relationship("ExtensionProjectFile", back_populates="project", cascade="all, delete-orphan")
    builds = relationship("ExtensionProjectBuild", back_populates="project", cascade="all, delete-orphan")


class ExtensionProjectFile(Base):
    __tablename__ = "extension_project_files"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("extension_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    path = Column(String(300), nullable=False)
    content = Column(Text, nullable=False)
    sha256 = Column(String(64), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    project = relationship("ExtensionProject", back_populates="files")
    __table_args__ = (UniqueConstraint("project_id", "path", name="uq_extension_project_file_path"),)


class ExtensionProjectBuild(Base):
    __tablename__ = "extension_project_builds"

    id = Column(Integer, primary_key=True)
    build_id = Column(String(64), nullable=False, unique=True, index=True)
    project_id = Column(Integer, ForeignKey("extension_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, index=True)
    change_kind = Column(String(32), nullable=False)
    change_request = Column(Text, nullable=True)
    spec_snapshot = Column(JSON, nullable=False)
    files_snapshot = Column(JSON, nullable=False)
    report = Column(JSON, nullable=False, default=dict)
    artifact_sha256 = Column(String(64), nullable=True, index=True)
    artifact_path = Column(Text, nullable=True)
    package_kind = Column(String(32), nullable=True)
    installed_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    project = relationship("ExtensionProject", back_populates="builds")
