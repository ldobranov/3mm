from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func
from backend.db.base import Base

class ModulePackage(Base):
    __tablename__ = "module_packages"
    id = Column(Integer, primary_key=True)
    module_id = Column(String(160), nullable=False, index=True)
    version = Column(String(64), nullable=False)
    manifest = Column(JSON, nullable=False)
    sha256 = Column(String(64), nullable=False, unique=True)
    size_bytes = Column(Integer, nullable=False)
    file_path = Column(Text, nullable=False)
    registrations = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (UniqueConstraint("module_id", "version", name="uq_module_package_version"),)

class ModuleInstallation(Base):
    __tablename__ = "module_installations"
    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    module_package_id = Column(Integer, ForeignKey("module_packages.id"), nullable=False)
    module_id = Column(String(160), nullable=False)
    installed_version = Column(String(64), nullable=True)
    desired_version = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, default="queued")
    enabled = Column(Boolean, nullable=False, default=True)
    command_id = Column(String(64), nullable=True, index=True)
    error = Column(Text, nullable=True)
    data_retained = Column(Boolean, nullable=False, default=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    __table_args__ = (UniqueConstraint("device_id", "module_id", name="uq_device_module_installation"),)


class ApplicationExtensionInstallation(Base):
    """Core-side record for one supervised application service."""

    __tablename__ = "application_extension_installations"
    id = Column(Integer, primary_key=True)
    module_id = Column(String(160), nullable=False, unique=True, index=True)
    module_package_id = Column(Integer, ForeignKey("module_packages.id"), nullable=False)
    previous_package_id = Column(Integer, ForeignKey("module_packages.id"), nullable=True)
    instance_id = Column(String(24), nullable=False, unique=True)
    active_version = Column(String(64), nullable=True)
    status = Column(String(32), nullable=False, default="staged", index=True)
    enabled = Column(Boolean, nullable=False, default=False, index=True)
    socket_path = Column(Text, nullable=False)
    configuration = Column(JSON, nullable=False, default=dict)
    error = Column(Text, nullable=True)
    activated_at = Column(DateTime(timezone=True), nullable=True)
    health_checked_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ApplicationPermissionGrant(Base):
    """One extension-scoped permission assigned to one normal user."""

    __tablename__ = "application_permission_grants"
    id = Column(Integer, primary_key=True)
    application_installation_id = Column(
        Integer,
        ForeignKey("application_extension_installations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    permission_id = Column(String(96), nullable=False)
    granted_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (
        UniqueConstraint(
            "application_installation_id",
            "user_id",
            "permission_id",
            name="uq_application_permission_grant",
        ),
    )


class ApplicationKioskEnrollment(Base):
    """Short-lived, one-use administrator-issued kiosk enrollment code."""

    __tablename__ = "application_kiosk_enrollments"
    id = Column(Integer, primary_key=True)
    application_installation_id = Column(
        Integer,
        ForeignKey("application_extension_installations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code_hash = Column(String(64), nullable=False, unique=True)
    label = Column(String(120), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ApplicationKioskTerminal(Base):
    """Revocable kiosk identity; the plaintext credential is never persisted."""

    __tablename__ = "application_kiosk_terminals"
    id = Column(Integer, primary_key=True)
    terminal_id = Column(String(64), nullable=False, unique=True, index=True)
    enrollment_id = Column(
        Integer,
        ForeignKey("application_kiosk_enrollments.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )
    application_installation_id = Column(
        Integer,
        ForeignKey("application_extension_installations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label = Column(String(120), nullable=False)
    credential_hash = Column(String(64), nullable=False)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)


class ApplicationEventDelivery(Base):
    """Durable, idempotent delivery of one device event to one subscription."""

    __tablename__ = "application_event_deliveries"
    id = Column(Integer, primary_key=True)
    application_installation_id = Column(
        Integer,
        ForeignKey("application_extension_installations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    subscription_id = Column(String(96), nullable=False)
    device_event_id = Column(
        Integer,
        ForeignKey("device_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status = Column(String(24), nullable=False, default="pending", index=True)
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        UniqueConstraint(
            "application_installation_id",
            "subscription_id",
            "device_event_id",
            name="uq_application_event_delivery",
        ),
        Index(
            "ix_application_event_delivery_queue",
            "application_installation_id",
            "subscription_id",
            "status",
            "device_event_id",
        ),
    )


class ApplicationEventCursor(Base):
    """Observable durable progress for one declared event subscription."""

    __tablename__ = "application_event_cursors"
    id = Column(Integer, primary_key=True)
    application_installation_id = Column(
        Integer,
        ForeignKey("application_extension_installations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    subscription_id = Column(String(96), nullable=False)
    last_device_event_id = Column(Integer, nullable=True)
    last_event_id = Column(String(64), nullable=True)
    acknowledged_count = Column(Integer, nullable=False, default=0)
    dead_letter_count = Column(Integer, nullable=False, default=0)
    dropped_dead_letter_count = Column(Integer, nullable=False, default=0)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    __table_args__ = (
        UniqueConstraint(
            "application_installation_id",
            "subscription_id",
            name="uq_application_event_cursor",
        ),
    )


class ApplicationSecretReference(Base):
    """Encrypted application-scoped credential; plaintext is never returned."""

    __tablename__ = "application_secret_references"
    id = Column(Integer, primary_key=True)
    secret_ref = Column(String(64), nullable=False, unique=True, index=True)
    application_installation_id = Column(
        Integer,
        ForeignKey("application_extension_installations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label = Column(String(120), nullable=False)
    credential_kind = Column(String(24), nullable=False)
    encrypted_value = Column(Text, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    rotated_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)


class ApplicationConnectorBinding(Base):
    __tablename__ = "application_connector_bindings"
    id = Column(Integer, primary_key=True)
    application_installation_id = Column(
        Integer,
        ForeignKey("application_extension_installations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    connector_id = Column(String(96), nullable=False)
    destination_origin = Column(String(512), nullable=False)
    secret_reference_id = Column(
        Integer,
        ForeignKey("application_secret_references.id", ondelete="SET NULL"),
        nullable=True,
    )
    enabled = Column(Boolean, nullable=False, default=True)
    last_outcome = Column(String(32), nullable=True)
    last_http_status = Column(Integer, nullable=True)
    last_checked_at = Column(DateTime(timezone=True), nullable=True)
    last_error_category = Column(String(64), nullable=True)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    __table_args__ = (
        UniqueConstraint(
            "application_installation_id",
            "connector_id",
            name="uq_application_connector_binding",
        ),
    )


class ApplicationConnectorAttempt(Base):
    __tablename__ = "application_connector_attempts"
    id = Column(Integer, primary_key=True)
    request_id = Column(String(64), nullable=False, unique=True, index=True)
    application_installation_id = Column(
        Integer,
        ForeignKey("application_extension_installations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    connector_id = Column(String(96), nullable=False)
    method = Column(String(12), nullable=False)
    path_hash = Column(String(64), nullable=False)
    outcome = Column(String(32), nullable=False, index=True)
    http_status = Column(Integer, nullable=True)
    error_category = Column(String(64), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)


class ApplicationJobState(Base):
    __tablename__ = "application_job_states"
    id = Column(Integer, primary_key=True)
    application_installation_id = Column(
        Integer,
        ForeignKey("application_extension_installations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_id = Column(String(96), nullable=False)
    next_run_at = Column(DateTime(timezone=True), nullable=False, index=True)
    lease_until = Column(DateTime(timezone=True), nullable=True, index=True)
    last_started_at = Column(DateTime(timezone=True), nullable=True)
    last_completed_at = Column(DateTime(timezone=True), nullable=True)
    last_outcome = Column(String(32), nullable=True)
    last_error = Column(Text, nullable=True)
    run_count = Column(Integer, nullable=False, default=0)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    __table_args__ = (
        UniqueConstraint(
            "application_installation_id", "job_id", name="uq_application_job_state"
        ),
    )


class ApplicationSyncCheckpoint(Base):
    __tablename__ = "application_sync_checkpoints"
    id = Column(Integer, primary_key=True)
    application_installation_id = Column(
        Integer,
        ForeignKey("application_extension_installations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    checkpoint_id = Column(String(96), nullable=False)
    revision = Column(Integer, nullable=False, default=0)
    value = Column(JSON, nullable=False, default=dict)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    __table_args__ = (
        UniqueConstraint(
            "application_installation_id",
            "checkpoint_id",
            name="uq_application_sync_checkpoint",
        ),
    )
