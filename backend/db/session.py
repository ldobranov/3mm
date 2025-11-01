from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from backend.db.base import Base
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from typing import Optional

class UserSession(Base):
    __tablename__ = "sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token = Column(String(500), unique=True, nullable=False, index=True)
    ip_address = Column(String(45))  # Support IPv6
    user_agent = Column(Text)
    device_name = Column(String(100))  # e.g., "Chrome on Windows"
    location = Column(String(100))  # e.g., "New York, US"
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_activity = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)
    
    # Relationship
    user = relationship("User", back_populates="sessions")

# Keep Session as an alias for backward compatibility
Session = UserSession

class SessionSchema(BaseModel):
    id: int
    user_id: int
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    device_name: Optional[str] = None
    location: Optional[str] = None
    is_active: bool
    created_at: datetime
    last_activity: datetime
    expires_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)

class SessionCreateSchema(BaseModel):
    user_id: int
    token: str
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    device_name: Optional[str] = None
    location: Optional[str] = None
    expires_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)