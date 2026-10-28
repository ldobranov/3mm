"""Inert retained-resource references protect immutable package recovery data."""
from sqlalchemy import Column, Integer, String, ForeignKey
from backend.db.base import Base


class ModulePackageRetainedReference(Base):
    __tablename__ = "module_package_retained_references"
    reference_id = Column(String(64), primary_key=True)
    package_id = Column(Integer, ForeignKey("module_packages.id", ondelete="RESTRICT"), nullable=False, index=True)
    source = Column(String(64), nullable=False)
    resource_ref = Column(String(160), nullable=False)
