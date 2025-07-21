from sqlalchemy.orm import declarative_base

Base = declarative_base()

# Dynamically register models during initialization
import backend.db.user
import backend.db.role
import backend.db.menu
import backend.db.page
import backend.db.settings
import backend.db.extension
import backend.db.notification
import backend.db.audit_log

__all__ = [
    "User", "Role", "Menu", "Page", "Settings", "Extension", "Notification", "AuditLog"
]
