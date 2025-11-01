from sqlalchemy import Column, Integer, String, Text
from backend.db.base import Base
from pydantic import BaseModel, ConfigDict

class Settings(Base):
    __tablename__ = "settings"
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, nullable=False)
    value = Column(Text, nullable=True)
    description = Column(String, nullable=True)

class SettingsSchema(BaseModel):
    id: int
    key: str
    value: str | None = None
    description: str | None = None

    model_config = ConfigDict(from_attributes=True)