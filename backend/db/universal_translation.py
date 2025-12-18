"""
Database models for Extension-Aware Universal Multilingual System
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, JSON, Numeric
from sqlalchemy.orm import relationship
from backend.db.base import Base
from datetime import datetime
import json


class ExtensionTable(Base):
    """Track all extension-created tables and their multilingual capabilities"""
    __tablename__ = "extension_tables"
    
    id = Column(Integer, primary_key=True, index=True)
    extension_id = Column(Integer, ForeignKey("extensions.id"), nullable=False)
    table_name = Column(String(100), nullable=False)
    table_schema = Column(JSON, nullable=False)  # Full table structure definition
    translatable_fields = Column(JSON, nullable=False, default=list)  # Array of field names
    primary_key_field = Column(String(100), nullable=False, default="id")
    is_multilingual = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    extension = relationship("Extension", back_populates="tables")
    
    __table_args__ = (
        {"extend_existing": True},
    )
    
    def __repr__(self):
        return f"<ExtensionTable(table_name='{self.table_name}', multilingual={self.is_multilingual})>"


class TableTranslation(Base):
    """Store translations for any extension table"""
    __tablename__ = "table_translations"
    
    id = Column(Integer, primary_key=True, index=True)
    extension_id = Column(Integer, ForeignKey("extensions.id"), nullable=False)
    table_name = Column(String(100), nullable=False)
    record_id = Column(Integer, nullable=False)  # The ID of the record being translated
    language_code = Column(String(10), nullable=False)
    translation_data = Column(JSON, nullable=False)  # {field_name: translated_value}
    translation_coverage = Column(Numeric(5, 2), default=0.0)  # Percentage coverage
    is_fallback = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    extension = relationship("Extension", back_populates="table_translations")
    
    __table_args__ = (
        {"extend_existing": True},
    )
    
    def __repr__(self):
        return f"<TableTranslation(table='{self.table_name}', lang='{self.language_code}', record={self.record_id})>"


class ExtensionField(Base):
    """Define extension field structures for dynamic multilingual support"""
    __tablename__ = "extension_fields"
    
    id = Column(Integer, primary_key=True, index=True)
    extension_id = Column(Integer, ForeignKey("extensions.id"), nullable=False)
    table_name = Column(String(100), nullable=False)
    field_name = Column(String(100), nullable=False)
    field_type = Column(String(50), nullable=False)  # 'text', 'json', 'richtext', etc.
    is_translatable = Column(Boolean, default=False)
    validation_rules = Column(JSON, default=dict)
    field_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    extension = relationship("Extension")
    
    __table_args__ = (
        {"extend_existing": True},
    )
    
    def __repr__(self):
        return f"<ExtensionField(table='{self.table_name}', field='{self.field_name}', translatable={self.is_translatable})>"


# Enhanced Menu Model for Migration
class Menu(Base):
    """Enhanced Menu model with multilingual support"""
    __tablename__ = "menus"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    structure = Column(JSON, nullable=True)  # Language-agnostic structure
    items = Column(JSON, nullable=True)  # Translated items for current/default language
    default_language = Column(String(10), default='en')
    has_translations = Column(Boolean, default=False)
    is_active = Column(Boolean, nullable=True, default=False)

    __table_args__ = (
        {"extend_existing": True},
    )
    
    def __repr__(self):
        return f"<Menu(name='{self.name}', multilingual={self.has_translations})>"

# SettingTranslation Model for Settings
class SettingTranslation(Base):
    """Store translations for settings"""
    __tablename__ = "setting_translations"
    
    id = Column(Integer, primary_key=True, index=True)
    setting_id = Column(Integer, ForeignKey("settings.id"), nullable=False)
    language_code = Column(String(10), nullable=False)
    translated_value = Column(Text, nullable=True)
    translated_description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    setting = relationship("Settings", back_populates="translations")
    
    __table_args__ = (
        {"extend_existing": True},
    )
    
    def __repr__(self):
        return f"<SettingTranslation(setting_id={self.setting_id}, lang='{self.language_code}')>"



# Migration history tracking
class MigrationHistory(Base):
    """Track migration progress for multilingual system"""
    __tablename__ = "migration_history"
    
    id = Column(Integer, primary_key=True, index=True)
    migration_type = Column(String(50), nullable=False)  # 'menu_data', 'settings_data', etc.
    status = Column(String(20), nullable=False)  # 'pending', 'completed', 'failed'
    records_processed = Column(Integer, default=0)
    total_records = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    def __repr__(self):
        return f"<MigrationHistory(type='{self.migration_type}', status='{self.status}')>"