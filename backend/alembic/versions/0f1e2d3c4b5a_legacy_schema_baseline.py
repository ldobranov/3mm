"""create the legacy Core schema baseline

Revision ID: 0f1e2d3c4b5a
Revises:

The project originally used ``Base.metadata.create_all()`` before introducing
Alembic.  This baseline captures those pre-device tables so a clean database
can now be built entirely through the migration history.
"""

from alembic import op
from sqlalchemy import MetaData

import backend.database  # noqa: F401 - populate model metadata
from backend.db.base import Base


revision = "0f1e2d3c4b5a"
down_revision = None
branch_labels = None
depends_on = None


POST_BASELINE_TABLES = {
    "devices",
    "device_credentials",
    "device_pairing_requests",
    "device_inventory_snapshots",
    "device_heartbeats",
    "device_commands",
    "device_states",
    "device_events",
    "device_capability_states",
    "module_packages",
    "module_installations",
    "application_extension_installations",
    "application_permission_grants",
    "application_kiosk_enrollments",
    "application_kiosk_terminals",
    "application_event_deliveries",
    "application_event_cursors",
    "application_secret_references",
    "application_connector_bindings",
    "application_connector_attempts",
    "application_job_states",
    "application_sync_checkpoints",
    "automation_proposals",
    "automation_revisions",
    "automation_audit_events",
    "ai_credit_accounts",
    "ai_jobs",
    "ai_usage_ledger",
    "runtime_extension_definitions",
    "runtime_entity_records",
    "extension_projects",
    "extension_project_files",
    "extension_project_builds",
}


def _baseline_metadata() -> MetaData:
    metadata = MetaData()
    for table in Base.metadata.sorted_tables:
        if table.name not in POST_BASELINE_TABLES:
            table.to_metadata(metadata)
    return metadata


def upgrade() -> None:
    _baseline_metadata().create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    metadata = _baseline_metadata()
    metadata.drop_all(bind=op.get_bind(), checkfirst=True)
