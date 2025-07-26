import sys
import os
from datetime import datetime

# Ensure the backend directory is added to the Python path
backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.db.settings import Settings
from backend.db.page import Page
from backend.db.audit_log import AuditLog
from backend.db.extension import Extension
from backend.db.menu import Menu
from backend.db.notification import Notification
from backend.db.role import Role
from backend.db.user import User
from backend.extensions.hiveos.models import HiveOSKey
from backend.utils.db_utils import get_db
from backend.db.base import Base

@pytest.fixture(scope="module")
def db_session():
    # Setup a SQLite in-memory database for testing
    engine = create_engine("sqlite:///:memory:")
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Create all tables
    Base.metadata.create_all(bind=engine)

    session = TestingSessionLocal()
    yield session
    session.close()

# Test Settings model
@pytest.mark.parametrize("data", [
    {"site_name": "Test Site", "languages": ["en"], "menu": [{"name": "Home", "path": "/", "order": 1}]},
    {"site_name": "Another Site", "languages": ["fr"], "menu": []},
])
def test_settings_model(db_session, data):
    settings = Settings(data=data)
    db_session.add(settings)
    db_session.commit()
    assert settings.id is not None
    assert settings.data == data

# Test Page model
@pytest.mark.parametrize("title, content", [
    ("Page Title", "Page Content"),
    ("Another Title", "Another Content"),
])
def test_page_model(db_session, title, content):
    page = Page(title=title, content=content)
    db_session.add(page)
    db_session.commit()
    assert page.id is not None
    assert page.title == title
    assert page.content == content

# Test AuditLog model
@pytest.mark.parametrize("user_id, action, details, timestamp", [
    (1, "Login", "User logged in", datetime(2025, 7, 11)),
    (2, "Logout", "User logged out", datetime(2025, 7, 12)),
])
def test_audit_log_model(db_session, user_id, action, details, timestamp):
    audit_log = AuditLog(user_id=user_id, action=action, details=details, timestamp=timestamp)
    db_session.add(audit_log)
    db_session.commit()
    assert audit_log.id is not None
    assert audit_log.user_id == user_id
    assert audit_log.action == action
    assert audit_log.details == details
    assert audit_log.timestamp == timestamp

# Test Extension model
@pytest.mark.parametrize("name, version, description, enabled", [
    ("Extension1", "1.0", "Test Extension", True),
    ("Extension2", "2.0", "Another Extension", False),
])
def test_extension_model(db_session, name, version, description, enabled):
    extension = Extension(name=name, version=version, description=description, enabled=enabled)
    db_session.add(extension)
    db_session.commit()
    assert extension.id is not None
    assert extension.name == name
    assert extension.version == version
    assert extension.description == description
    assert extension.enabled == enabled

# Test Menu model
@pytest.mark.parametrize("name, path, order", [
    ("Home", "/", 1),
    ("Settings", "/settings", 2),
])
def test_menu_model(db_session, name, path, order):
    menu = Menu(name=name, path=path, order=order)
    db_session.add(menu)
    db_session.commit()
    assert menu.id is not None
    assert menu.name == name
    assert menu.path == path
    assert menu.order == order

# Test Notification model
@pytest.mark.parametrize("user_id, message, is_read, created_at", [
    (1, "Test Message", False, datetime(2025, 7, 11)),
    (2, "Another Message", True, datetime(2025, 7, 12)),
])
def test_notification_model(db_session, user_id, message, is_read, created_at):
    notification = Notification(user_id=user_id, message=message, is_read=is_read, created_at=created_at)
    db_session.add(notification)
    db_session.commit()
    assert notification.id is not None
    assert notification.user_id == user_id
    assert notification.message == message
    assert notification.is_read == is_read
    assert notification.created_at == created_at

# Test Role model
@pytest.mark.parametrize("name", [
    ("Admin"),
    ("User"),
])
def test_role_model(db_session, name):
    role = Role(name=name)
    db_session.add(role)
    db_session.commit()
    assert role.id is not None
    assert role.name == name

# Test User model
@pytest.mark.parametrize("username, email, hashed_password", [
    ("testuser", "test@example.com", "hashedpassword123"),
    ("anotheruser", "another@example.com", "hashedpassword456"),
])
def test_user_model(db_session, username, email, hashed_password):
    user = User(username=username, email=email, hashed_password=hashed_password)
    db_session.add(user)
    db_session.commit()
    assert user.id is not None
    assert user.username == username
    assert user.email == email
    assert user.hashed_password == hashed_password

# Test HiveOSKey model
@pytest.mark.parametrize("user_id, api_key", [
    (1, "test_api_key_123"),
    (2, "another_api_key_456"),
])
def test_hiveos_key_model(db_session, user_id, api_key):
    hiveos_key = HiveOSKey(user_id=user_id, api_key=api_key)
    db_session.add(hiveos_key)
    db_session.commit()
    assert hiveos_key.id is not None
    assert hiveos_key.user_id == user_id
    assert hiveos_key.api_key == api_key
