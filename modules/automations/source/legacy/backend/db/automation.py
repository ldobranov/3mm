"""Persistent AI automation proposals; applying them belongs to a later stage."""

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from backend.db.base import Base


class AutomationProposal(Base):
    __tablename__ = "automation_proposals"

    id = Column(Integer, primary_key=True)
    proposal_id = Column(String(64), nullable=False, unique=True, index=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    intent = Column(Text, nullable=False)
    candidate = Column(JSON, nullable=False)
    candidate_hash = Column(String(64), nullable=False)
    context_hash = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, index=True)
    validation_issues = Column(JSON, nullable=False, default=list)
    diff = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    validated_at = Column(DateTime(timezone=True), nullable=False)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approved_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)


class AutomationRevision(Base):
    __tablename__ = "automation_revisions"

    id = Column(Integer, primary_key=True)
    revision_id = Column(String(64), nullable=False, unique=True, index=True)
    automation_id = Column(String(64), nullable=False, index=True)
    revision = Column(Integer, nullable=False)
    proposal_id = Column(String(64), nullable=True, index=True)
    definition = Column(JSON, nullable=True)
    definition_hash = Column(String(64), nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    operation = Column(String(32), nullable=False)
    command_ids = Column(JSON, nullable=False, default=list)
    applied_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (UniqueConstraint("automation_id", "revision", name="uq_automation_revision_number"),)


class AutomationAuditEvent(Base):
    __tablename__ = "automation_audit_events"

    id = Column(Integer, primary_key=True)
    event_id = Column(String(64), nullable=False, unique=True, index=True)
    automation_id = Column(String(64), nullable=False, index=True)
    proposal_id = Column(String(64), nullable=True, index=True)
    revision_id = Column(String(64), nullable=True, index=True)
    actor_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    event_type = Column(String(64), nullable=False, index=True)
    details = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AiCreditAccount(Base):
    __tablename__ = "ai_credit_accounts"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True)
    available_microcredits = Column(Integer, nullable=False, default=0)
    reserved_microcredits = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class AiJob(Base):
    __tablename__ = "ai_jobs"
    id = Column(Integer, primary_key=True)
    job_id = Column(String(64), nullable=False, unique=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    purpose = Column(String(64), nullable=False)
    request_hash = Column(String(64), nullable=False, index=True)
    provider = Column(String(32), nullable=False)
    model = Column(String(160), nullable=False)
    payment_mode = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False, index=True)
    estimated_input_tokens = Column(Integer, nullable=False)
    estimated_output_tokens = Column(Integer, nullable=False)
    estimated_max_microcredits = Column(Integer, nullable=False)
    approved_max_microcredits = Column(Integer, nullable=True)
    reserved_microcredits = Column(Integer, nullable=False, default=0)
    actual_input_tokens = Column(Integer, nullable=True)
    actual_output_tokens = Column(Integer, nullable=True)
    actual_microcredits = Column(Integer, nullable=True)
    artifact_hash = Column(String(64), nullable=True, index=True)
    proposal_id = Column(String(64), nullable=True, index=True)
    error_code = Column(String(80), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)


class AiUsageLedger(Base):
    __tablename__ = "ai_usage_ledger"
    id = Column(Integer, primary_key=True)
    entry_id = Column(String(64), nullable=False, unique=True, index=True)
    job_id = Column(String(64), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    entry_type = Column(String(32), nullable=False)
    microcredits = Column(Integer, nullable=False)
    details = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
