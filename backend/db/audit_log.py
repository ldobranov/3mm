from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from backend.db.base import Base
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from typing import Optional, Dict, Any

class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action = Column(String(50), nullable=False)  # CREATE, UPDATE, DELETE, LOGIN, LOGOUT
    entity_type = Column(String(50))  # page, widget, dashboard, user, settings
    entity_id = Column(Integer)  # ID of the affected entity
    entity_name = Column(String(255))  # Human-readable name
    changes = Column(JSON)  # Store before/after values for updates
    ip_address = Column(String(45))
    user_agent = Column(Text)
    session_id = Column(Integer, ForeignKey("sessions.id"))
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Relationships
    user = relationship("User", back_populates="audit_logs")
    session = relationship("UserSession")

class AuditLogSchema(BaseModel):
    id: int
    user_id: int
    action: str
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    entity_name: Optional[str] = None
    changes: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    session_id: Optional[int] = None
    timestamp: datetime
    
    model_config = ConfigDict(from_attributes=True)

class AuditLogCreateSchema(BaseModel):
    user_id: int
    action: str
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    entity_name: Optional[str] = None
    changes: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    session_id: Optional[int] = None
    
    model_config = ConfigDict(from_attributes=True)