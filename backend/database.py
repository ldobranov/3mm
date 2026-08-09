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
from backend.config import get_settings

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
from backend.db.device import (
    Device,
    DeviceCredential,
    DeviceHeartbeat,
    DeviceInventorySnapshot,
    DevicePairingRequest,
    DeviceCommand,
    DeviceState,
)
from backend.db.module import ModulePackage, ModuleInstallation
import logging

logger = logging.getLogger(__name__)

# PostgreSQL connection string with proper Unicode support
DATABASE_URL = get_settings().database_url

if DATABASE_URL.startswith("sqlite:///") and not DATABASE_URL.endswith(":memory:"):
    database_path = Path(DATABASE_URL.removeprefix("sqlite:///"))
    database_path.parent.mkdir(parents=True, exist_ok=True)

def get_db_url():
    """Get database URL for async operations"""
    return DATABASE_URL

# Configure engine with proper Unicode support
engine_options = {
    "json_serializer": lambda obj: json.dumps(obj, ensure_ascii=False),
    "json_deserializer": lambda obj: json.loads(obj),
}
if DATABASE_URL.startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_options)

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
