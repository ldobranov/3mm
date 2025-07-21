import os
import sys

# Add the backend directory to the system path for resolving imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from backend.db.base import Base
from typing import Generator

# Ensure the database file is created inside the backend folder
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///backend/mega_monitor.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    """Initialize the database schema."""
    Base.metadata.create_all(bind=engine)

# Fixed the `get_db` function to work correctly with FastAPI's `Depends`.
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

