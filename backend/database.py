import os
import sys
from pathlib import Path

# Add the backend directory to the system path for resolving imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from backend.db.base import Base
from typing import Generator
import json

# Load config from root config.json
config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
with open(config_path, 'r') as f:
    config = json.load(f)

# Import all models to ensure they're registered with SQLAlchemy
from backend.db.user import User
from backend.db.session import UserSession
from backend.db.audit_log import AuditLog
from backend.db.permission import Permission
from backend.db.page import Page
from backend.db.display import Display
from backend.db.widget import Widget
from backend.db.universal_translation import Menu
from backend.db.settings import Settings
from backend.db.role import Role
from backend.db.notification import Notification
from backend.db.extension import Extension
import logging

logger = logging.getLogger(__name__)

# PostgreSQL connection string with proper Unicode support
DATABASE_URL = os.getenv("DATABASE_URL", config['backend']['database_url'])

def get_db_url():
    """Get database URL for async operations"""
    return DATABASE_URL

# Configure engine with proper Unicode support
engine = create_engine(
    DATABASE_URL,
    json_serializer=lambda obj: json.dumps(obj, ensure_ascii=False),
    json_deserializer=lambda obj: json.loads(obj)
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    """Initialize the database schema."""
    logger.info("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created successfully")

# Fixed the `get_db` function to work correctly with FastAPI's `Depends`.
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
