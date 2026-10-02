"""Generic installation peer consent, trust generations and replay ledger."""

from alembic import op
import sqlalchemy as sa

revision = "526ab1c2d3e4"
down_revision = "4159a0b1c2d3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "installation_peer_origin",
        sa.Column("singleton_id", sa.Integer(), primary_key=True),
        sa.Column("origin", sa.String(255), nullable=False),
    )
    op.create_table(
        "installation_peer_inbound",
        sa.Column("binding_id", sa.String(37), primary_key=True),
        sa.Column("module_id", sa.String(160), nullable=False),
        sa.Column("application_instance_id", sa.String(24), nullable=False),
        sa.Column("sender_id", sa.String(37), nullable=False),
        sa.Column("sender_identity", sa.JSON(), nullable=False),
        sa.Column("receiver_identity", sa.JSON(), nullable=False),
        sa.Column("origin", sa.String(255), nullable=False),
        sa.Column("request_id", sa.String(37), nullable=False),
        sa.Column("start_request", sa.JSON(), nullable=False),
        sa.Column("sender_challenge", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("completed_digest", sa.String(64)),
        sa.Column("credential", sa.JSON()),
        sa.Column("rotation_digest", sa.String(64)),
        sa.Column("approval_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "module_id", "sender_id", name="uq_installation_peer_sender"
        ),
    )
    op.create_table(
        "installation_peer_outbound",
        sa.Column("link_id", sa.String(37), primary_key=True),
        sa.Column("module_id", sa.String(160), nullable=False),
        sa.Column("application_instance_id", sa.String(24), nullable=False),
        sa.Column("sender_identity", sa.JSON(), nullable=False),
        sa.Column("receiver_identity", sa.JSON(), nullable=False),
        sa.Column("origin", sa.String(255), nullable=False),
        sa.Column("target_module_id", sa.String(160), nullable=False),
        sa.Column("consent", sa.JSON(), nullable=False),
        sa.Column("consent_revision", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("start_request", sa.JSON()),
        sa.Column("complete_request", sa.JSON()),
        sa.Column("remote_binding_id", sa.String(37)),
        sa.Column("credential", sa.JSON()),
        sa.Column("rotation_request", sa.JSON()),
        sa.Column("report_id", sa.String(39)),
        sa.Column("report_projection", sa.JSON()),
        sa.Column("report_result", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "installation_peer_nonces",
        sa.Column("binding_id", sa.String(37), primary_key=True),
        sa.Column("generation", sa.Integer(), primary_key=True),
        sa.Column("nonce", sa.String(43), primary_key=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_installation_peer_nonces_expires_at",
        "installation_peer_nonces",
        ["expires_at"],
    )
    op.create_table(
        "installation_peer_audit",
        sa.Column("event_id", sa.String(32), primary_key=True),
        sa.Column("peer_id", sa.String(37), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("actor_kind", sa.String(24), nullable=False),
        sa.Column("actor_id", sa.String(64)),
        sa.Column("generation", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_installation_peer_audit_peer_id", "installation_peer_audit", ["peer_id"]
    )


def downgrade():
    op.drop_table("installation_peer_audit")
    op.drop_table("installation_peer_nonces")
    op.drop_table("installation_peer_outbound")
    op.drop_table("installation_peer_inbound")
    op.drop_table("installation_peer_origin")
