"""Opt-in sealed application authority; no inferred trust or grant backfill."""

import importlib

from alembic import op
import sqlalchemy as sa

revision = "dab239e0f1a2"
down_revision = "c9d128d9e0f1"
branch_labels = None
depends_on = None


def _tables():
    metadata = sa.MetaData()
    result = []
    for name, identifier, constraint, id_constraint in (
        ("application_native_reviews", "review_id", "native_review", "length(review_id) = 32 AND installation_id > 0"),
        ("application_authority_plans", "plan_id", "authority_plan", "length(plan_id) = 32 AND installation_id > 0"),
        ("application_authority_grants", None, "authority_grant", "installation_id > 0 AND revision >= 1 AND revision <= 9007199254740990"),
        ("application_authority_actions", "request_id", "authority_action", "length(request_id) = 32 AND installation_id > 0"),
    ):
        columns = [sa.Column("installation_id", sa.Integer(), primary_key=identifier is None, nullable=False)]
        if identifier:
            columns.insert(0, sa.Column(identifier, sa.String(32), primary_key=True))
        else:
            columns.append(sa.Column("revision", sa.BigInteger(), nullable=False))
        columns.extend([
            sa.Column("payload", sa.Text(), nullable=False),
            sa.Column("key_id", sa.String(39), nullable=False),
            sa.Column("seal", sa.String(64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint(id_constraint, name="ck_" + constraint + ("_revision" if identifier is None else "_identity")),
            sa.CheckConstraint("length(payload) <= 131072 AND length(seal) = 64", name="ck_" + constraint + "_seal"),
        ])
        result.append(sa.Table(name, metadata, *columns))
    return result


def _mode(enforced):
    checks = sa.inspect(op.get_bind()).get_check_constraints("application_extension_installations")
    current = next((item["sqltext"] for item in checks if item["name"] == "ck_application_authority_mode"), None)
    expected = "authority_mode IN ('compatibility', 'review_required', 'enforced')" if enforced else "authority_mode IN ('compatibility', 'review_required')"
    if current == expected:
        return
    alternate = "authority_mode IN ('compatibility', 'review_required')" if enforced else "authority_mode IN ('compatibility', 'review_required', 'enforced')"
    if current != alternate:
        raise RuntimeError("Unexpected application authority mode schema")
    with op.batch_alter_table("application_extension_installations") as batch:
        batch.drop_constraint("ck_application_authority_mode", type_="check")
        batch.create_check_constraint("ck_application_authority_mode", expected)


def upgrade():
    connection = op.get_bind()
    tables = _tables()
    present = [sa.inspect(connection).has_table(table.name) for table in tables]
    if any(present):
        if not all(present):
            raise RuntimeError("Partial authority grant schema; explicit recovery required")
        shape = importlib.import_module("backend.alembic.versions.c9d128d9e0f1_policy_review_store")._shape
        for expected in tables:
            actual = sa.Table(expected.name, sa.MetaData(), autoload_with=connection)
            # Column order differs between inherited ORM columns and frozen DDL.
            left, right = shape(actual, connection.dialect), shape(expected, connection.dialect)
            if sorted(left[0]) != sorted(right[0]) or left[1:] != right[1:]:
                raise RuntimeError("Unexpected authority grant schema; explicit recovery required")
    _mode(True)
    if not any(present):
        for table in tables:
            table.create(connection)


def downgrade():
    connection = op.get_bind()
    for table in _tables():
        if connection.execute(sa.select(table).limit(1)).first():
            raise RuntimeError("Authority history exists; restore a verified pre-upgrade backup")
    if connection.execute(sa.text("SELECT 1 FROM application_extension_installations WHERE authority_mode = 'enforced' LIMIT 1")).first():
        raise RuntimeError("Enforced installations require verified recovery")
    _mode(False)
    for table in reversed(_tables()):
        table.drop(connection)
