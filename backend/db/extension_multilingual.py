"""
Extension Multilingual Content Database Models
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class ExtensionMultilingualContent(Base):
    """Table for storing multilingual content created by extensions"""

    __tablename__ = "extension_multilingual_content"

    id = Column(Integer, primary_key=True, index=True)
    extension_id = Column(Integer, ForeignKey("extensions.id"), nullable=False)
    content_key = Column(String(255), nullable=False)  # Unique key for this content within extension
    language_code = Column(String(10), nullable=False)  # Language code (en, bg, es, etc.)
    content_data = Column(JSON, nullable=False)  # JSON object with field translations
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship to extension
    extension = relationship("Extension", back_populates="multilingual_content")

    def to_dict(self):
        return {
            "id": self.id,
            "extension_id": self.extension_id,
            "content_key": self.content_key,
            "language_code": self.language_code,
            "content_data": self.content_data,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# Update Extension model to include relationship (this would be added to extension.py)
# extension.multilingual_content = relationship("ExtensionMultilingualContent", back_populates="extension")