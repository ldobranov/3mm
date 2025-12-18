from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from backend.db.base import Base
from pydantic import BaseModel, ConfigDict
from datetime import datetime

class Settings(Base):
    __tablename__ = "settings"
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, nullable=False)
    value = Column(Text, nullable=True)
    description = Column(String, nullable=True)
    language_code = Column(String(10), nullable=True)  # Optional language code for language-specific settings
    is_translatable = Column(Boolean, default=False)
    content_type = Column(String(50), default='setting')
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)  # User-specific settings

    # Translation relationships
    translations = relationship("SettingTranslation", back_populates="setting", cascade="all, delete-orphan")

class SettingsSchema(BaseModel):
    id: int
    key: str
    value: str | None = None
    description: str | None = None
    language_code: str | None = None
    user_id: int | None = None

    model_config = ConfigDict(from_attributes=True)

class SettingsCreateSchema(BaseModel):
    key: str
    value: str | None = None
    description: str | None = None
    language_code: str | None = None
    user_id: int | None = None

    model_config = ConfigDict(from_attributes=True)

class SettingsUpdateSchema(BaseModel):
    id: int
    key: str
    value: str | None = None
    description: str | None = None
    language_code: str | None = None
    user_id: int | None = None

    model_config = ConfigDict(from_attributes=True)