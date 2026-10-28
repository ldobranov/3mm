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
from backend.db.menu import Menu
from backend.db.settings import Settings
from backend.db.role import Role
from backend.db.installation_identity import CoreInstallationIdentity
from backend.db.installation_peer import InstallationPeerOrigin, InstallationPeerInbound, InstallationPeerOutbound, InstallationPeerNonce, InstallationPeerAudit
from backend.db.application_command import ApplicationCommandEpoch, ApplicationCommandRequest
from backend.db.application_task import ApplicationTaskRun, ApplicationTaskSchedule
from backend.db.authority import CoreAuthorityGuard
from backend.db.application_policy_review import ApplicationPolicyReview, ApplicationPolicyReviewDecision
from backend.db.application_authority_grant import ApplicationNativeReview, ApplicationAuthorityPlan, ApplicationAuthorityGrant, ApplicationAuthorityAction
from backend.db.notification import Notification
from backend.db.language_extension import LanguageExtensionInstallation
from backend.db.device import (
    Device,
    DeviceCredential,
    DeviceHeartbeat,
    DeviceInventorySnapshot,
    DevicePairingRequest,
    DeviceCommand,
    DeviceEvent,
    DeviceState,
    DeviceCapabilityState,
    DeviceCapabilityProvider,
    DeviceRuntimeFeatures,
)
from backend.db.module_reference import ModulePackageRetainedReference
from backend.db.module import (
    ApplicationEventCursor,
    ApplicationEventDelivery,
    ApplicationConnectorAttempt,
    ApplicationConnectorBinding,
    ApplicationExtensionInstallation,
    ApplicationJobState,
    ApplicationKioskEnrollment,
    ApplicationKioskTerminal,
    ApplicationPermissionGrant,
    ApplicationRetainedData,
    ApplicationSecretReference,
    ApplicationSyncCheckpoint,
    ModuleInstallation,
    ModulePackage,
)
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
