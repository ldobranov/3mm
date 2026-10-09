"""Core-private review history, deliberately unable to represent an approval."""

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from backend.db.base import Base


class ApplicationPolicyReview(Base):
    __tablename__ = "application_policy_reviews"

    review_id = Column(String(32), primary_key=True)
    # Historical snapshots, NOT cascading FKs to mutable/deletable live objects.
    core_installation_id = Column(String(37), nullable=False)
    recovery_generation = Column(String(32), nullable=False)
    application_installation_id = Column(Integer, nullable=False)
    incarnation = Column(String(32), nullable=False)
    module_id = Column(String(160), nullable=False)
    artifact_sha256 = Column(String(64), nullable=False)
    subject_json = Column(Text, nullable=False)
    subject_sha256 = Column(String(64), nullable=False)
    state = Column(String(24), nullable=False)
    revision = Column(String(32), nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (
        CheckConstraint("length(review_id) = 32", name="ck_policy_review_id"),
        CheckConstraint("length(recovery_generation) = 32", name="ck_policy_review_recovery"),
        CheckConstraint("application_installation_id > 0", name="ck_policy_review_application"),
        CheckConstraint("length(incarnation) = 32", name="ck_policy_review_incarnation"),
        CheckConstraint("length(artifact_sha256) = 64", name="ck_policy_review_artifact"),
        CheckConstraint("length(subject_sha256) = 64", name="ck_policy_review_subject_hash"),
        CheckConstraint("length(subject_json) <= 131072", name="ck_policy_review_subject_size"),
        CheckConstraint("state IN ('review_required', 'denied', 'revoked')", name="ck_policy_review_state"),
        CheckConstraint("length(revision) = 32", name="ck_policy_review_revision"),
    )


class ApplicationPolicyReviewDecision(Base):
    """Append-only via the service; deleting users/apps must retain attribution."""

    __tablename__ = "application_policy_review_decisions"

    decision_id = Column(String(32), primary_key=True)
    review_id = Column(String(32), ForeignKey("application_policy_reviews.review_id"), nullable=False)
    request_id = Column(String(32), nullable=False, unique=True)
    request_sha256 = Column(String(64), nullable=False)
    actor_user_id = Column(Integer, nullable=False)
    actor_session_id = Column(Integer, nullable=False)
    actor_session_sha256 = Column(String(64), nullable=False)
    recovery_generation = Column(String(32), nullable=False)
    previous_revision = Column(String(32), nullable=True)
    revision = Column(String(32), nullable=False, unique=True)
    decision = Column(String(16), nullable=False)
    reason = Column(String(32), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (
        UniqueConstraint("review_id", "previous_revision", name="uq_policy_review_successor"),
        CheckConstraint("length(decision_id) = 32 AND length(request_id) = 32", name="ck_policy_decision_ids"),
        CheckConstraint("length(request_sha256) = 64 AND length(actor_session_sha256) = 64", name="ck_policy_decision_hashes"),
        CheckConstraint("actor_user_id > 0 AND actor_session_id > 0", name="ck_policy_decision_actor"),
        CheckConstraint("length(recovery_generation) = 32 AND length(revision) = 32", name="ck_policy_decision_generations"),
        CheckConstraint("previous_revision IS NULL OR length(previous_revision) = 32", name="ck_policy_decision_previous"),
        CheckConstraint(
            "(decision = 'recorded' AND reason = 'review_required' AND previous_revision IS NULL) OR "
            "(decision = 'denied' AND reason = 'operator_denied' AND previous_revision IS NOT NULL) OR "
            "(decision = 'revoked' AND reason = 'operator_revoked' AND previous_revision IS NOT NULL)",
            name="ck_policy_decision_kind",
        ),
    )
