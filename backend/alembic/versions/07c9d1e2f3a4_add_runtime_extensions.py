"""add declarative runtime extension definitions and records

Revision ID: 07c9d1e2f3a4
Revises: f6b8c9d0e1f2
"""

from alembic import op
import sqlalchemy as sa


revision = "07c9d1e2f3a4"
down_revision = "f6b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "runtime_extension_definitions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("module_id", sa.String(160), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("module_id", "version", name="uq_runtime_extension_version"),
    )
    op.create_index("ix_runtime_extension_definitions_module_id", "runtime_extension_definitions", ["module_id"])
    op.create_index("ix_runtime_extension_definitions_enabled", "runtime_extension_definitions", ["enabled"])
    op.create_table(
        "runtime_entity_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("module_id", sa.String(160), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("record_id", sa.String(32), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("module_id", "entity_id", "record_id", name="uq_runtime_entity_record"),
    )
    op.create_index("ix_runtime_entity_records_module_id", "runtime_entity_records", ["module_id"])
    op.create_index("ix_runtime_entity_records_entity_id", "runtime_entity_records", ["entity_id"])


def downgrade():
    op.drop_table("runtime_entity_records")
    op.drop_table("runtime_extension_definitions")
