from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Enum
from sqlalchemy.orm import relationship
from backend.db.base import Base
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from typing import Optional
import enum

class PermissionLevel(enum.Enum):
    NONE = "none"
    VIEW = "view"
    EDIT = "edit"
    DELETE = "delete"
    ADMIN = "admin"

class Permission(Base):
    __tablename__ = "permissions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    entity_type = Column(String(50), nullable=False)  # dashboard, page, widget
    entity_id = Column(Integer, nullable=False)
    permission_level = Column(Enum(PermissionLevel), default=PermissionLevel.VIEW)
    granted_by = Column(Integer, ForeignKey("users.id"))
    granted_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id], back_populates="permissions")
    granter = relationship("User", foreign_keys=[granted_by])

class PermissionSchema(BaseModel):
    id: int
    user_id: int
    entity_type: str
    entity_id: int
    permission_level: str
    granted_by: Optional[int] = None
    granted_at: datetime
    expires_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)

class PermissionCreateSchema(BaseModel):
    user_id: int
    entity_type: str
    entity_id: int
    permission_level: str
    granted_by: Optional[int] = None
    expires_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)