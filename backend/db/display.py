from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from backend.db.base import Base


class Display(Base):
    __tablename__ = "displays"
    __table_args__ = (UniqueConstraint('user_id', 'slug', name='uq_user_slug'),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    owner_id = property(lambda self: self.user_id)  # Alias for compatibility
    title = Column(String, nullable=False)
    slug = Column(String, nullable=False)
    is_public = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    widgets = relationship("Widget", back_populates="display", cascade="all, delete-orphan")
