from sqlalchemy import Column, Integer, String, Boolean
from .base import Base
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from backend.utils.db_utils import get_db
from pydantic import BaseModel

class Extension(Base):
    __tablename__ = "extensions"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    version = Column(String)
    description = Column(String)
    enabled = Column(Boolean, default=True)
    backend_path = Column(String)
    frontend_path = Column(String)

class ExtensionBase(BaseModel):
    name: str
    version: str
    description: str
    enabled: bool
    backend_path: str
    frontend_path: str

    class Config:
        orm_mode = True