"""Current data-package selection; translations stay in immutable packages."""
from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, false
from backend.db.base import Base


class LanguageExtensionInstallation(Base):
    __tablename__ = 'language_extension_installations'
    code = Column(String(10), primary_key=True)
    module_package_id = Column(Integer, ForeignKey('module_packages.id', ondelete='RESTRICT'), nullable=False, unique=True)
    enabled = Column(Boolean, nullable=False, default=False, server_default=false())
