# backend/db/widget.py
import os
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from backend.db.base import Base

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///backend/mega_monitor.db")
if DATABASE_URL.startswith("postgresql"):
    from sqlalchemy.dialects.postgresql import JSONB as JSON
else:
    from sqlalchemy.dialects.sqlite import JSON

class Widget(Base):
    __tablename__ = "widgets"
    id = Column(Integer, primary_key=True)
    display_id = Column(Integer, ForeignKey("displays.id", ondelete="CASCADE"), nullable=False)
    type = Column(String, nullable=False)  # CLOCK | TEXT | RSS | extension:extension_id
    config = Column(JSON, nullable=False, default=dict)
    x = Column(Integer, nullable=False, default=0)
    y = Column(Integer, nullable=False, default=0)
    width = Column(Integer, nullable=False, default=2)
    height = Column(Integer, nullable=False, default=2)
    z_index = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    display = relationship("Display", back_populates="widgets")