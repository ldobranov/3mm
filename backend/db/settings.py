from sqlalchemy import Column, Integer, JSON, String
from backend.db.base import Base
from pydantic import BaseModel, ConfigDict

class Settings(Base):
    __tablename__ = "settings"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    language = Column(String, unique=True, index=True)
    data = Column(JSON, default={})

class SettingsSchema(BaseModel):
    id: int
    name: str
    language: str
    data: dict

    model_config = ConfigDict(from_attributes=True)