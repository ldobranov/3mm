"""add persistent AI extension projects and build history

Revision ID: 29e3f4a5b6c7
Revises: 18d2e3f4a5b6
"""

from alembic import op
import sqlalchemy as sa


revision = "29e3f4a5b6c7"
down_revision = "18d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade():
    # Align the selected-version model index that was omitted by the previous
    # runtime-extension migration. Existing databases receive it here too.
    op.create_index(
        "ix_runtime_extension_definitions_is_selected",
        "runtime_extension_definitions",
        ["is_selected"],
    )
    op.create_table(
        "extension_projects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("slug", sa.String(120), nullable=False),
        sa.Column("project_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("spec", sa.JSON(), nullable=False),
        sa.Column("current_version", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_extension_projects_project_id", "extension_projects", ["project_id"], unique=True)
    op.create_index("ix_extension_projects_owner_user_id", "extension_projects", ["owner_user_id"])
    op.create_index("ix_extension_projects_slug", "extension_projects", ["slug"], unique=True)
    op.create_index("ix_extension_projects_status", "extension_projects", ["status"])

    op.create_table(
        "extension_project_files",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("extension_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("path", sa.String(300), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("project_id", "path", name="uq_extension_project_file_path"),
    )
    op.create_index("ix_extension_project_files_project_id", "extension_project_files", ["project_id"])

    op.create_table(
        "extension_project_builds",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("build_id", sa.String(64), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("extension_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("change_kind", sa.String(32), nullable=False),
        sa.Column("change_request", sa.Text(), nullable=True),
        sa.Column("spec_snapshot", sa.JSON(), nullable=False),
        sa.Column("files_snapshot", sa.JSON(), nullable=False),
        sa.Column("report", sa.JSON(), nullable=False),
        sa.Column("artifact_sha256", sa.String(64), nullable=True),
        sa.Column("artifact_path", sa.Text(), nullable=True),
        sa.Column("package_kind", sa.String(32), nullable=True),
        sa.Column("installed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_extension_project_builds_build_id", "extension_project_builds", ["build_id"], unique=True)
    op.create_index("ix_extension_project_builds_project_id", "extension_project_builds", ["project_id"])
    op.create_index("ix_extension_project_builds_status", "extension_project_builds", ["status"])
    op.create_index("ix_extension_project_builds_artifact_sha256", "extension_project_builds", ["artifact_sha256"])


def downgrade():
    op.drop_table("extension_project_builds")
    op.drop_table("extension_project_files")
    op.drop_table("extension_projects")
    op.drop_index(
        "ix_runtime_extension_definitions_is_selected",
        table_name="runtime_extension_definitions",
    )
