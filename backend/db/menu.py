from sqlalchemy import Column, Integer, String
from .base import Base
from pydantic import BaseModel, ConfigDict

class Menu(Base):
    __tablename__ = "menus"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True)
    path = Column(String)
    order = Column(Integer)

class Page(Base):
    __tablename__ = "pages"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, unique=True)
    content = Column(String)

class MenuSchema(BaseModel):
    id: int
    name: str
    path: str
    order: int

    model_config = ConfigDict(from_attributes=True)

class MenuCreateSchema(BaseModel):
    name: str
    path: str
    order: int

    model_config = ConfigDict(from_attributes=True)
