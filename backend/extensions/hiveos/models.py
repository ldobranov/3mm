from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from backend.database import Base

class HiveOSKey(Base):
    __tablename__ = "hiveos_keys"
    __table_args__ = {"extend_existing": True}  # Allow redefinition if the table already exists

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    api_key = Column(String, nullable=False)
    selected_farm_id = Column(String, nullable=True)