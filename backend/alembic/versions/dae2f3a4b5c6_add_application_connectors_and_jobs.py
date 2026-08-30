"""add application connector, secret, job and checkpoint state

Revision ID: dae2f3a4b5c6
Revises: c9e1f2a3b4c5
"""

from alembic import op
import sqlalchemy as sa


revision = "dae2f3a4b5c6"
down_revision = "c9e1f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "application_secret_references",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("secret_ref", sa.String(64), nullable=False),
        sa.Column("application_installation_id", sa.Integer(), sa.ForeignKey("application_extension_installations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("credential_kind", sa.String(24), nullable=False),
        sa.Column("encrypted_value", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_application_secret_references_secret_ref", "application_secret_references", ["secret_ref"], unique=True)
    op.create_index("ix_application_secret_references_application_installation_id", "application_secret_references", ["application_installation_id"])
    op.create_table(
        "application_connector_bindings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("application_installation_id", sa.Integer(), sa.ForeignKey("application_extension_installations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connector_id", sa.String(96), nullable=False),
        sa.Column("destination_origin", sa.String(512), nullable=False),
        sa.Column("secret_reference_id", sa.Integer(), sa.ForeignKey("application_secret_references.id", ondelete="SET NULL"), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_outcome", sa.String(32), nullable=True),
        sa.Column("last_http_status", sa.Integer(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_category", sa.String(64), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("application_installation_id", "connector_id", name="uq_application_connector_binding"),
    )
    op.create_index("ix_application_connector_bindings_application_installation_id", "application_connector_bindings", ["application_installation_id"])
    op.create_table(
        "application_connector_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("application_installation_id", sa.Integer(), sa.ForeignKey("application_extension_installations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connector_id", sa.String(96), nullable=False),
        sa.Column("method", sa.String(12), nullable=False),
        sa.Column("path_hash", sa.String(64), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("error_category", sa.String(64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_application_connector_attempts_request_id", "application_connector_attempts", ["request_id"], unique=True)
    op.create_index("ix_application_connector_attempts_application_installation_id", "application_connector_attempts", ["application_installation_id"])
    op.create_index("ix_application_connector_attempts_outcome", "application_connector_attempts", ["outcome"])
    op.create_table(
        "application_job_states",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("application_installation_id", sa.Integer(), sa.ForeignKey("application_extension_installations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.String(96), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_outcome", sa.String(32), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("run_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("application_installation_id", "job_id", name="uq_application_job_state"),
    )
    op.create_index("ix_application_job_states_application_installation_id", "application_job_states", ["application_installation_id"])
    op.create_index("ix_application_job_states_next_run_at", "application_job_states", ["next_run_at"])
    op.create_index("ix_application_job_states_lease_until", "application_job_states", ["lease_until"])
    op.create_table(
        "application_sync_checkpoints",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("application_installation_id", sa.Integer(), sa.ForeignKey("application_extension_installations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("checkpoint_id", sa.String(96), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("application_installation_id", "checkpoint_id", name="uq_application_sync_checkpoint"),
    )
    op.create_index("ix_application_sync_checkpoints_application_installation_id", "application_sync_checkpoints", ["application_installation_id"])


def downgrade():
    op.drop_table("application_sync_checkpoints")
    op.drop_table("application_job_states")
    op.drop_table("application_connector_attempts")
    op.drop_table("application_connector_bindings")
    op.drop_table("application_secret_references")
