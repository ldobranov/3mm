"""Persistent Core registry models for managed devices."""

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.db.base import Base


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True)
    device_id = Column(String(64), nullable=False, unique=True, index=True)
    display_name = Column(String(255), nullable=True)
    role = Column(String(32), nullable=False)
    protocol_version = Column(String(32), nullable=False)
    approved_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    credentials = relationship(
        "DeviceCredential", back_populates="device", cascade="all, delete-orphan"
    )
    pairing_requests = relationship("DevicePairingRequest", back_populates="device")
    inventory_snapshots = relationship(
        "DeviceInventorySnapshot",
        back_populates="device",
        cascade="all, delete-orphan",
    )
    heartbeats = relationship(
        "DeviceHeartbeat", back_populates="device", cascade="all, delete-orphan"
    )


class DeviceCredential(Base):
    __tablename__ = "device_credentials"

    id = Column(Integer, primary_key=True)
    device_id = Column(
        Integer,
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    credential_id = Column(String(64), nullable=False, unique=True, index=True)
    secret_hash = Column(String(255), nullable=False)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    device = relationship("Device", back_populates="credentials")


class DevicePairingRequest(Base):
    __tablename__ = "device_pairing_requests"

    id = Column(Integer, primary_key=True)
    code_hash = Column(String(255), nullable=False, unique=True, index=True)
    requested_device_id = Column(String(64), nullable=True, index=True)
    public_key = Column(Text, nullable=True)
    requested_metadata = Column(JSON, nullable=False, default=dict)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=True, index=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    approved_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    claimed_at = Column(DateTime(timezone=True), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    device = relationship("Device", back_populates="pairing_requests")


class DeviceInventorySnapshot(Base):
    __tablename__ = "device_inventory_snapshots"

    id = Column(Integer, primary_key=True)
    device_id = Column(
        Integer,
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    inventory = Column(JSON, nullable=False)
    received_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    device = relationship("Device", back_populates="inventory_snapshots")

    __table_args__ = (
        Index("ix_inventory_device_received", "device_id", "received_at"),
    )


class DeviceHeartbeat(Base):
    __tablename__ = "device_heartbeats"

    id = Column(Integer, primary_key=True)
    device_id = Column(
        Integer,
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    protocol_version = Column(String(32), nullable=False)
    payload = Column(JSON, nullable=False, default=dict)
    received_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    device = relationship("Device", back_populates="heartbeats")

    __table_args__ = (
        Index("ix_heartbeat_device_received", "device_id", "received_at"),
    )


class DeviceCommand(Base):
    __tablename__ = "device_commands"

    id = Column(Integer, primary_key=True)
    command_id = Column(String(64), nullable=False, unique=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    command_type = Column(String(100), nullable=False)
    payload = Column(JSON, nullable=False, default=dict)
    idempotency_key = Column(String(128), nullable=False)
    status = Column(String(32), nullable=False, default="queued", index=True)
    result = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    delivery_attempts = Column(Integer, nullable=False, default=0)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_command_device_status_created", "device_id", "status", "created_at"),
        Index("ux_command_device_idempotency", "device_id", "idempotency_key", unique=True),
    )


class DeviceState(Base):
    __tablename__ = "device_states"

    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    desired_revision = Column(Integer, nullable=False, default=0)
    desired_state = Column(JSON, nullable=False, default=dict)
    desired_updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    reported_revision = Column(Integer, nullable=False, default=0)
    reported_state = Column(JSON, nullable=False, default=dict)
    reported_at = Column(DateTime(timezone=True), nullable=True)
