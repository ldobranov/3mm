from sqlalchemy import Column, Integer, String
from backend.db.base import Base

class HiveOSKey(Base):
    __tablename__ = "hiveos_keys"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)
    api_key = Column(String, nullable=False)
