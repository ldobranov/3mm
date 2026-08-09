"""add module catalog and installation lifecycle
Revision ID: b274fa0b1243
Revises: a164fa0b1242
"""
from alembic import op
import sqlalchemy as sa
revision="b274fa0b1243"; down_revision="a164fa0b1242"; branch_labels=None; depends_on=None
def upgrade():
    op.create_table("module_packages",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("module_id",sa.String(160),nullable=False),sa.Column("version",sa.String(64),nullable=False),sa.Column("manifest",sa.JSON(),nullable=False),sa.Column("sha256",sa.String(64),nullable=False,unique=True),sa.Column("size_bytes",sa.Integer(),nullable=False),sa.Column("file_path",sa.Text(),nullable=False),sa.Column("registrations",sa.JSON(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),sa.UniqueConstraint("module_id","version",name="uq_module_package_version"))
    op.create_index("ix_module_packages_module_id","module_packages",["module_id"])
    op.create_table("module_installations",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("device_id",sa.Integer(),sa.ForeignKey("devices.id",ondelete="CASCADE"),nullable=False),sa.Column("module_package_id",sa.Integer(),sa.ForeignKey("module_packages.id"),nullable=False),sa.Column("module_id",sa.String(160),nullable=False),sa.Column("installed_version",sa.String(64)),sa.Column("desired_version",sa.String(64),nullable=False),sa.Column("status",sa.String(32),nullable=False),sa.Column("enabled",sa.Boolean(),nullable=False),sa.Column("command_id",sa.String(64)),sa.Column("error",sa.Text()),sa.Column("data_retained",sa.Boolean(),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),sa.UniqueConstraint("device_id","module_id",name="uq_device_module_installation"))
    op.create_index("ix_module_installations_device_id","module_installations",["device_id"]); op.create_index("ix_module_installations_command_id","module_installations",["command_id"])
def downgrade():
    op.drop_table("module_installations"); op.drop_table("module_packages")
