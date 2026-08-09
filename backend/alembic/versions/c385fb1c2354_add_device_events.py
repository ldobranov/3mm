"""add device events
Revision ID: c385fb1c2354
Revises: b274fa0b1243
"""
from alembic import op
import sqlalchemy as sa
revision="c385fb1c2354"; down_revision="b274fa0b1243"; branch_labels=None; depends_on=None
def upgrade():
    op.create_table("device_events",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("device_id",sa.Integer(),sa.ForeignKey("devices.id",ondelete="CASCADE"),nullable=False),sa.Column("event_id",sa.String(64),nullable=False,unique=True),sa.Column("event_type",sa.String(120),nullable=False),sa.Column("payload",sa.JSON(),nullable=False),sa.Column("occurred_at",sa.DateTime(timezone=True),nullable=False),sa.Column("received_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()))
    op.create_index("ix_device_events_device_id","device_events",["device_id"]);op.create_index("ix_device_events_event_id","device_events",["event_id"],unique=True);op.create_index("ix_device_events_occurred_at","device_events",["occurred_at"])
def downgrade(): op.drop_table("device_events")
