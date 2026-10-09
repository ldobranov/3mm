"""Core-only sealed native reviews, permission plans, grants and action receipts.

No cascading owner FKs: uninstall/account deletion retain review attribution.
Existing installations receive NO rows or permission escalation on migration.
"""

from sqlalchemy import BigInteger, CheckConstraint, Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from backend.db.base import Base


class SealedRecord:
    payload = Column(Text, nullable=False)
    key_id = Column(String(39), nullable=False)
    seal = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ApplicationNativeReview(SealedRecord, Base):
    __tablename__ = "application_native_reviews"
    review_id = Column(String(32), primary_key=True)
    installation_id = Column(Integer, nullable=False)
    __table_args__ = (
        CheckConstraint("length(review_id) = 32 AND installation_id > 0", name="ck_native_review_identity"),
        CheckConstraint("length(payload) <= 131072 AND length(seal) = 64", name="ck_native_review_seal"),
    )


class ApplicationAuthorityPlan(SealedRecord, Base):
    __tablename__ = "application_authority_plans"
    plan_id = Column(String(32), primary_key=True)
    installation_id = Column(Integer, nullable=False)
    __table_args__ = (
        CheckConstraint("length(plan_id) = 32 AND installation_id > 0", name="ck_authority_plan_identity"),
        CheckConstraint("length(payload) <= 131072 AND length(seal) = 64", name="ck_authority_plan_seal"),
    )


class ApplicationAuthorityGrant(SealedRecord, Base):
    __tablename__ = "application_authority_grants"
    installation_id = Column(Integer, primary_key=True)
    revision = Column(BigInteger, nullable=False)
    __table_args__ = (
        CheckConstraint("installation_id > 0 AND revision >= 1 AND revision <= 9007199254740990", name="ck_authority_grant_revision"),
        CheckConstraint("length(payload) <= 131072 AND length(seal) = 64", name="ck_authority_grant_seal"),
    )


class ApplicationAuthorityAction(SealedRecord, Base):
    __tablename__ = "application_authority_actions"
    request_id = Column(String(32), primary_key=True)
    installation_id = Column(Integer, nullable=False)
    __table_args__ = (
        CheckConstraint("length(request_id) = 32 AND installation_id > 0", name="ck_authority_action_identity"),
        CheckConstraint("length(payload) <= 131072 AND length(seal) = 64", name="ck_authority_action_seal"),
    )
