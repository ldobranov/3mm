"""preserve the selected runtime extension version while disabled

Revision ID: 18d2e3f4a5b6
Revises: 07c9d1e2f3a4
"""

from alembic import op
import sqlalchemy as sa


revision = "18d2e3f4a5b6"
down_revision = "07c9d1e2f3a4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "runtime_extension_definitions",
        sa.Column("is_selected", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute(
        "UPDATE runtime_extension_definitions SET is_selected = enabled"
    )
    op.create_index(
        "uq_runtime_extension_active_module",
        "runtime_extension_definitions",
        ["module_id"],
        unique=True,
        sqlite_where=sa.text("enabled = 1"),
        postgresql_where=sa.text("enabled"),
    )
    op.create_index(
        "uq_runtime_extension_selected_module",
        "runtime_extension_definitions",
        ["module_id"],
        unique=True,
        sqlite_where=sa.text("is_selected = 1"),
        postgresql_where=sa.text("is_selected"),
    )


def downgrade():
    op.drop_index(
        "uq_runtime_extension_selected_module",
        table_name="runtime_extension_definitions",
    )
    op.drop_index(
        "uq_runtime_extension_active_module",
        table_name="runtime_extension_definitions",
    )
    with op.batch_alter_table("runtime_extension_definitions") as batch_op:
        batch_op.drop_column("is_selected")
