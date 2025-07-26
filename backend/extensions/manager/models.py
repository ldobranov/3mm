from sqlalchemy import Column, Integer, String, JSON
from backend.db.base import Base

class ManagerTask(Base):
    __tablename__ = "manager_tasks"

    id = Column(Integer, primary_key=True, index=True)
    task_name = Column(String, nullable=False)
    parameters = Column(JSON, nullable=True)
    status = Column(String, nullable=False, default="pending")
