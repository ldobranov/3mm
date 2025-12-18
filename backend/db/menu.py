from sqlalchemy import Column, Integer, String, Boolean, JSON
from .base import Base
from pydantic import BaseModel, ConfigDict

class Menu(Base):
    __tablename__ = "menus"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    items = Column(JSON, nullable=True)
    is_active = Column(Boolean, nullable=True, default=False)


class MenuSchema(BaseModel):
    id: int
    name: str
    items: list | None = []
    is_active: bool = False

    model_config = ConfigDict(from_attributes=True)

class MenuCreateSchema(BaseModel):
    name: str
    items: list | None = []
    is_active: bool = False

    model_config = ConfigDict(from_attributes=True)