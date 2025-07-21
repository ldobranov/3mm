from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.sql import func
from backend.db.base import Base

class Page(Base):
    __tablename__ = "pages"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True)
    title = Column(String, unique=True)
    content = Column(Text)  # Updated to support HTML content
    slug = Column(String, unique=True, nullable=False, default="")

    def generate_slug(self):
        if not self.slug and self.title:
            self.slug = self.title.lower().replace(" ", "-")

    @staticmethod
    def get_by_slug(session, slug):
        return session.query(Page).filter_by(slug=slug).first()
