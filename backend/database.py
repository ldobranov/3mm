import os
import sys
from pathlib import Path

# Add the backend directory to the system path for resolving imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from backend.db.base import Base
from typing import Generator

# Import all models to ensure they're registered with SQLAlchemy
from backend.db.user import User
from backend.db.session import UserSession
from backend.db.audit_log import AuditLog
from backend.db.permission import Permission
from backend.db.page import Page
from backend.db.display import Display
from backend.db.widget import Widget
from backend.db.menu import Menu
from backend.db.settings import Settings
from backend.db.role import Role
from backend.db.notification import Notification

# Get the absolute path to the backend directory
BACKEND_DIR = Path(__file__).parent.absolute()
DB_PATH = BACKEND_DIR / "mega_monitor.db"

# Use absolute path for the database
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")
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
