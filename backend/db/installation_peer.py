"""Installation-to-installation trust state. Never shares the Agent registry."""

from sqlalchemy import JSON, Column, DateTime, Integer, String, UniqueConstraint
from backend.db.base import Base


class InstallationPeerOrigin(Base):
    __tablename__ = "installation_peer_origin"
    singleton_id = Column(Integer, primary_key=True)
    origin = Column(String(255), nullable=False)


class InstallationPeerInbound(Base):
    __tablename__ = "installation_peer_inbound"
    binding_id = Column(String(37), primary_key=True)
    # Retain tombstones across uninstall; IDs cannot regain trust on reinstall.
    module_id = Column(String(160), nullable=False)
    application_instance_id = Column(String(24), nullable=False)
    sender_id = Column(String(37), nullable=False)
    sender_identity = Column(JSON, nullable=False)
    receiver_identity = Column(JSON, nullable=False)
    origin = Column(String(255), nullable=False)
    request_id = Column(String(37), nullable=False)
    start_request = Column(JSON, nullable=False)
    sender_challenge = Column(JSON, nullable=False)
    state = Column(String(24), nullable=False)
    generation = Column(Integer, nullable=False, default=1)
    completed_digest = Column(String(64), nullable=True)
    credential = Column(JSON, nullable=True)
    rotation_digest = Column(String(64), nullable=True)
    approval_expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        UniqueConstraint("module_id", "sender_id", name="uq_installation_peer_sender"),
    )


class InstallationPeerOutbound(Base):
    __tablename__ = "installation_peer_outbound"
    link_id = Column(String(37), primary_key=True)
    module_id = Column(String(160), nullable=False)
    application_instance_id = Column(String(24), nullable=False)
    sender_identity = Column(JSON, nullable=False)
    receiver_identity = Column(JSON, nullable=False)
    origin = Column(String(255), nullable=False)
    target_module_id = Column(String(160), nullable=False)
    consent = Column(JSON, nullable=False)
    consent_revision = Column(Integer, nullable=False, default=1)
    state = Column(String(24), nullable=False)
    start_request = Column(JSON, nullable=True)
    complete_request = Column(JSON, nullable=True)
    remote_binding_id = Column(String(37), nullable=True)
    credential = Column(JSON, nullable=True)
    rotation_request = Column(JSON, nullable=True)
    report_id = Column(String(39), nullable=True)
    report_projection = Column(JSON, nullable=True)
    report_result = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class InstallationPeerNonce(Base):
    __tablename__ = "installation_peer_nonces"
    binding_id = Column(String(37), primary_key=True)
    generation = Column(Integer, primary_key=True)
    nonce = Column(String(43), primary_key=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)


class InstallationPeerAudit(Base):
    """Machine/system audit without fabricating a human user identity."""

    __tablename__ = "installation_peer_audit"
    event_id = Column(String(32), primary_key=True)
    peer_id = Column(String(37), nullable=False, index=True)
    action = Column(String(64), nullable=False)
    actor_kind = Column(String(24), nullable=False)
    actor_id = Column(String(64), nullable=True)
    generation = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
