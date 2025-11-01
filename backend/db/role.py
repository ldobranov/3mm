from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from backend.db.base import Base
# from backend.db.association_tables import user_roles  # Commented out for now

class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    # users = relationship("User", secondary=user_roles, back_populates="roles", lazy="dynamic")  # Commented out

    __table_args__ = {"extend_existing": True}