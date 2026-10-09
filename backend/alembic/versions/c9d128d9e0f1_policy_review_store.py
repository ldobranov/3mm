"""Add non-authorizing policy review history; never backfill approvals."""

from alembic import op
import sqlalchemy as sa


revision = "c9d128d9e0f1"
down_revision = "b8c017c8d9e0"
branch_labels = None
depends_on = None


def _tables():
    # Frozen DDL: old upgrades must never import a future runtime model.
    metadata = sa.MetaData()
    names = ("application_policy_reviews", "application_policy_review_decisions")
    review = sa.Table(
        names[0],
        metadata,
        sa.Column("review_id", sa.String(32), primary_key=True),
        sa.Column("core_installation_id", sa.String(37), nullable=False),
        sa.Column("recovery_generation", sa.String(32), nullable=False),
        sa.Column("application_installation_id", sa.Integer(), nullable=False),
        sa.Column("incarnation", sa.String(32), nullable=False),
        sa.Column("module_id", sa.String(160), nullable=False),
        sa.Column("artifact_sha256", sa.String(64), nullable=False),
        sa.Column("subject_json", sa.Text(), nullable=False),
        sa.Column("subject_sha256", sa.String(64), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("revision", sa.String(32), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("length(review_id) = 32", name="ck_policy_review_id"),
        sa.CheckConstraint("length(recovery_generation) = 32", name="ck_policy_review_recovery"),
        sa.CheckConstraint("application_installation_id > 0", name="ck_policy_review_application"),
        sa.CheckConstraint("length(incarnation) = 32", name="ck_policy_review_incarnation"),
        sa.CheckConstraint("length(artifact_sha256) = 64", name="ck_policy_review_artifact"),
        sa.CheckConstraint("length(subject_sha256) = 64", name="ck_policy_review_subject_hash"),
        sa.CheckConstraint("length(subject_json) <= 131072", name="ck_policy_review_subject_size"),
        sa.CheckConstraint("state IN ('review_required', 'denied', 'revoked')", name="ck_policy_review_state"),
        sa.CheckConstraint("length(revision) = 32", name="ck_policy_review_revision"),
    )
    decision = sa.Table(
        names[1],
        metadata,
        sa.Column("decision_id", sa.String(32), primary_key=True),
        sa.Column("review_id", sa.String(32), sa.ForeignKey(names[0] + ".review_id"), nullable=False),
        sa.Column("request_id", sa.String(32), nullable=False, unique=True),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=False),
        sa.Column("actor_session_id", sa.Integer(), nullable=False),
        sa.Column("actor_session_sha256", sa.String(64), nullable=False),
        sa.Column("recovery_generation", sa.String(32), nullable=False),
        sa.Column("previous_revision", sa.String(32), nullable=True),
        sa.Column("revision", sa.String(32), nullable=False, unique=True),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("review_id", "previous_revision", name="uq_policy_review_successor"),
        sa.CheckConstraint("length(decision_id) = 32 AND length(request_id) = 32", name="ck_policy_decision_ids"),
        sa.CheckConstraint("length(request_sha256) = 64 AND length(actor_session_sha256) = 64", name="ck_policy_decision_hashes"),
        sa.CheckConstraint("actor_user_id > 0 AND actor_session_id > 0", name="ck_policy_decision_actor"),
        sa.CheckConstraint("length(recovery_generation) = 32 AND length(revision) = 32", name="ck_policy_decision_generations"),
        sa.CheckConstraint("previous_revision IS NULL OR length(previous_revision) = 32", name="ck_policy_decision_previous"),
        sa.CheckConstraint(
            "(decision = 'recorded' AND reason = 'review_required' AND previous_revision IS NULL) OR "
            "(decision = 'denied' AND reason = 'operator_denied' AND previous_revision IS NOT NULL) OR "
            "(decision = 'revoked' AND reason = 'operator_revoked' AND previous_revision IS NOT NULL)",
            name="ck_policy_decision_kind",
        ),
    )
    return review, decision


def _shape(table, dialect):
    def sql(value):
        return " ".join(str(value.compile(dialect=dialect)).split())

    return (
        tuple((column.name, sql(column.type), column.nullable, column.primary_key,
               sql(column.server_default.arg) if column.server_default is not None else None)
              for column in table.columns),
        {" ".join(str(constraint.sqltext).split()) for constraint in table.constraints
         if isinstance(constraint, sa.CheckConstraint)},
        {tuple(column.name for column in constraint.columns) for constraint in table.constraints
         if isinstance(constraint, sa.UniqueConstraint)},
        {(tuple(element.parent.name for element in constraint.elements),
          tuple(element.target_fullname for element in constraint.elements),
          constraint.ondelete, constraint.onupdate)
         for constraint in table.constraints if isinstance(constraint, sa.ForeignKeyConstraint)},
    )


def upgrade():
    # Legacy create_all is supported only when BOTH complete tables already exist.
    # Never silently replace existing review or audit history or accept missing
    # non-authorizing-state/idempotency/retention constraints.
    connection = op.get_bind()
    existing = sa.inspect(connection)
    tables = _tables()
    present = [existing.has_table(table.name) for table in tables]
    if any(present):
        if not all(present):
            raise RuntimeError("Partial policy review schema; explicit recovery required")
        for expected in tables:
            actual = sa.Table(expected.name, sa.MetaData(), autoload_with=connection)
            if _shape(actual, connection.dialect) != _shape(expected, connection.dialect):
                raise RuntimeError("Unexpected policy review schema; explicit recovery required")
        return
    for table in tables:
        table.create(connection)


def downgrade():
    connection = op.get_bind()
    for name in ("application_policy_reviews", "application_policy_review_decisions"):
        if connection.execute(sa.text(f"SELECT 1 FROM {name} LIMIT 1")).first():
            raise RuntimeError("Policy review history exists; restore a verified pre-upgrade backup")
    op.drop_table("application_policy_review_decisions")
    op.drop_table("application_policy_reviews")
