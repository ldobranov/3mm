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
    title = Column(JSON, nullable=False, default={})  # Store as {"en": "Title", "bg": "Заглавие"}
    content = Column(JSON, nullable=True)  # Store as {"en": "Content", "bg": "Съдържание"}
    slug = Column(String, unique=True, nullable=False, default="")  # Slug remains single-language
    is_public = Column(Boolean, nullable=False, default=True)
    allowed_roles = Column(JSON, nullable=False, default=list)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Relationship to User
    owner = relationship("User", backref="pages", lazy="joined")

    def get_localized_title(self, language: str = "bg") -> str:
        """Get the page title in the specified language, with fallback"""
        if isinstance(self.title, dict):
            return self.title.get(language, self.title.get("bg", self.title.get("en", "")))
        return str(self.title) if self.title else ""

    def get_localized_content(self, language: str = "bg") -> str:
        """Get the page content in the specified language, with fallback"""
        if isinstance(self.content, dict):
            return self.content.get(language, self.content.get("bg", self.content.get("en", "")))
        return str(self.content) if self.content else ""

    def generate_slug(self, language: str = "bg"):
        """Generate slug from the localized title"""
        title = self.get_localized_title(language)
        if title:
            self.slug = title.lower().replace(" ", "-").replace("ъ", "a").replace("ьо", "yo")

    def to_dict(self, language: str = "bg") -> dict:
        """Convert to dictionary with localized content"""
        return {
            "id": self.id,
            "title": self.get_localized_title(language),
            "title_translations": self.title,
            "content": self.get_localized_content(language),
            "content_translations": self.content,
            "slug": self.slug,
            "is_public": self.is_public,
            "allowed_roles": self.allowed_roles,
            "owner_id": self.owner_id
        }

    @staticmethod
    def get_by_slug(session, slug, language: str = "bg"):
        """Get a page by slug, using the current language for title lookup"""
        page = session.query(Page).filter_by(slug=slug).first()
        if not page:
            # Try to find page by matching the localized title
            # This handles cases where slug generation might have differences
            for page_candidate in session.query(Page).all():
                if page_candidate.get_localized_title(language).lower().replace(" ", "-").replace("ъ", "a").replace("ьо", "yo") == slug:
                    return page_candidate
        return page
