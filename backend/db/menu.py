"""Core navigation menus, independent of the retired translation engine."""
from sqlalchemy import Boolean, Column, Integer, JSON, String
from pydantic import BaseModel, ConfigDict
from backend.db.base import Base

class Menu(Base):
    """Configured navigation with localized item labels."""
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
