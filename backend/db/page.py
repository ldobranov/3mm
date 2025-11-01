from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from backend.db.base import Base

class Page(Base):
    __tablename__ = "pages"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True)
    title = Column(String, unique=True)
    content = Column(Text)  # Updated to support HTML content
    slug = Column(String, unique=True, nullable=False, default="")
    is_public = Column(Boolean, nullable=False, default=True)
    allowed_roles = Column(JSON, nullable=False, default=list)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Relationship to User
    owner = relationship("User", backref="pages", lazy="joined")

    def generate_slug(self):
        if not self.slug and self.title:
            self.slug = self.title.lower().replace(" ", "-")

    @staticmethod
    def get_by_slug(session, slug):
        page = session.query(Page).filter_by(slug=slug).first()
        if not page:
            # Dynamically generate slug from title if not found
            page = session.query(Page).filter(Page.title.ilike(slug.replace('-', ' '))).first()
        return page
