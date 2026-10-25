"""
Language Pack database model
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from backend.db.base import Base
from datetime import datetime
import json


class LanguagePack(Base):
    __tablename__ = "language_packs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    code = Column(String(10), nullable=False, unique=True)  # e.g., 'en', 'bg', 'fr'
    native_name = Column(String(255), nullable=False)  # e.g., 'English', 'Български'
    locale = Column(String(20), nullable=False)  # e.g., 'en-US', 'bg-BG'
    direction = Column(String(10), default='ltr')  # 'ltr' or 'rtl'
    
    # Translation coverage percentages
    frontend_coverage = Column(Integer, default=0)
    backend_coverage = Column(Integer, default=0)
    extensions_coverage = Column(Integer, default=0)
    
    # Additional metadata
    currency = Column(String(3))  # ISO currency code
    date_format = Column(String(50))
    time_format = Column(String(20))
    number_format = Column(JSON)  # Store number format settings as JSON
    
    # Translation files as JSON
    frontend_translations = Column(JSON)
    backend_translations = Column(JSON)
    extensions_translations = Column(JSON)
    
    # Extension association
    extension_id = Column(Integer, ForeignKey("extensions.id"), nullable=True)
    module_package_id = Column(Integer, ForeignKey("module_packages.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    # extension = relationship("Extension", foreign_keys=[extension_id], back_populates="language_pack")

    def __repr__(self):
        return f"<LanguagePack(name='{self.name}', code='{self.code}')>"

    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "name": self.name,
            "code": self.code,
            "native_name": self.native_name,
            "locale": self.locale,
            "direction": self.direction,
            "coverage": {
                "frontend": self.frontend_coverage,
                "backend": self.backend_coverage,
                "extensions": self.extensions_coverage
            },
            "currency": self.currency,
            "date_format": self.date_format,
            "time_format": self.time_format,
            "number_format": self.number_format,
            "is_active": self.is_active,
            "is_default": self.is_default,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
