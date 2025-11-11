from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from backend.db.base import Base
from backend.db.association_tables import user_roles, user_groups, role_permissions, group_permissions
from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime

class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    description = Column(Text, nullable=True)
    is_system_role = Column(Integer, default=0)  # 0 = custom, 1 = system
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    users = relationship("User", secondary=user_roles, back_populates="roles", lazy="dynamic")
    # Note: role_permissions is now an association table, not a model

    __table_args__ = {"extend_existing": True}

class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    users = relationship("User", secondary=user_groups, back_populates="groups", lazy="dynamic")
    # Note: group_permissions is now an association table, not a model

    __table_args__ = {"extend_existing": True}

# Pydantic schemas
class RoleSchema(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    is_system_role: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class RoleCreateSchema(BaseModel):
    name: str
    description: Optional[str] = None

class RoleUpdateSchema(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

class GroupSchema(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class GroupCreateSchema(BaseModel):
    name: str
    description: Optional[str] = None

class GroupUpdateSchema(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None