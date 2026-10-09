"""Add inactive authority metadata without adopting or enforcing grants."""

import secrets

from alembic import op
import sqlalchemy as sa


revision = "b8c017c8d9e0"
down_revision = "a7bf06b7c8d9"
branch_labels = None
depends_on = None


def _backfill(table_name, primary_key, columns):
    connection = op.get_bind()
    table = sa.table(
        table_name,
        sa.column(primary_key, sa.Integer()),
        *(sa.column(name, sa.String(32)) for name in columns),
    )
    statement = table.update().where(table.c[primary_key] == sa.bindparam("row_key"))
    # Independent random identities for each row, bounded batches on large DBs.
    for ids in (
        connection.execute(sa.select(table.c[primary_key])).scalars().partitions(256)
    ):
        connection.execute(
            statement,
            [
                dict(row_key=key, **{name: secrets.token_hex(16) for name in columns})
                for key in ids
            ],
        )


def upgrade():
    connection = op.get_bind()
    # Legacy create_all may have created the new singleton table, but never
    # silently replace an already persisted generation or revision.
    existing_guard = sa.inspect(connection).has_table("core_authority_guard")
    guard = (
        sa.Table("core_authority_guard", sa.MetaData(), autoload_with=connection)
        if existing_guard
        else op.create_table(
            "core_authority_guard",
            sa.Column("singleton_id", sa.Integer(), primary_key=True),
            sa.Column("generation", sa.String(32), nullable=False),
            sa.Column("revision", sa.BigInteger(), nullable=False),
            sa.CheckConstraint("singleton_id = 1", name="ck_authority_guard_singleton"),
            sa.CheckConstraint(
                "length(generation) = 32", name="ck_authority_guard_generation"
            ),
            sa.CheckConstraint(
                "revision >= 1 AND revision <= 9007199254740991",
                name="ck_authority_guard_revision",
            ),
        )
    )
    if (
        connection.execute(
            sa.select(guard.c.singleton_id).where(guard.c.singleton_id == 1)
        ).first()
        is None
    ):
        connection.execute(
            guard.insert().values(
                singleton_id=1, generation=secrets.token_hex(16), revision=1
            )
        )
    changes = (
        (
            "application_extension_installations",
            "id",
            {
                "authority_incarnation": "ck_application_authority_incarnation",
                "authority_epoch": "ck_application_authority_epoch",
            },
        ),
        (
            "application_connector_bindings",
            "id",
            {
                "authority_revision": "ck_connector_authority_revision",
            },
        ),
        (
            "device_platform_states",
            "device_id",
            {
                "control_generation": "ck_device_control_generation",
            },
        ),
    )
    op.add_column(
        "application_extension_installations",
        sa.Column(
            "authority_mode",
            sa.String(16),
            nullable=False,
            server_default="compatibility",
        ),
    )
    for table_name, primary_key, columns in changes:
        for name in columns:
            op.add_column(table_name, sa.Column(name, sa.String(32), nullable=True))
        if table_name == "device_platform_states":
            # Older approved devices may never have requested a platform snapshot.
            # Materialize the same legacy default once during upgrade, not in an
            # authority reader/writer. Existing release/recovery state is untouched.
            connection.execute(sa.text(
                "INSERT INTO device_platform_states(device_id,authority_status,lifecycle,revision) "
                "SELECT devices.id,'bound','active',0 FROM devices "
                "WHERE NOT EXISTS (SELECT 1 FROM device_platform_states "
                "WHERE device_platform_states.device_id=devices.id)"
            ))
        _backfill(table_name, primary_key, columns)
        with op.batch_alter_table(table_name) as batch:
            for name, constraint in columns.items():
                batch.alter_column(name, existing_type=sa.String(32), nullable=False)
                batch.create_check_constraint(constraint, f"length({name}) = 32")
            if table_name == "application_extension_installations":
                batch.create_check_constraint(
                    "ck_application_authority_mode",
                    "authority_mode IN ('compatibility', 'review_required')",
                )


def downgrade():
    connection = op.get_bind()
    # Once used by a participating caller, metadata must not be silently erased.
    if (
        connection.execute(
            sa.text("SELECT revision FROM core_authority_guard WHERE singleton_id = 1")
        ).scalar_one()
        != 1
        or connection.execute(
            sa.text(
                "SELECT 1 FROM application_extension_installations WHERE authority_mode != 'compatibility' LIMIT 1"
            )
        ).first()
    ):
        raise RuntimeError(
            "Authority metadata has been used; restore the verified pre-upgrade backup instead"
        )
    for table_name, columns in (
        (
            "device_platform_states",
            {"control_generation": "ck_device_control_generation"},
        ),
        (
            "application_connector_bindings",
            {"authority_revision": "ck_connector_authority_revision"},
        ),
        (
            "application_extension_installations",
            {
                "authority_incarnation": "ck_application_authority_incarnation",
                "authority_epoch": "ck_application_authority_epoch",
            },
        ),
    ):
        with op.batch_alter_table(table_name) as batch:
            for name, constraint in columns.items():
                batch.drop_constraint(constraint, type_="check")
                batch.drop_column(name)
            if table_name == "application_extension_installations":
                batch.drop_constraint("ck_application_authority_mode", type_="check")
                batch.drop_column("authority_mode")
    op.drop_table("core_authority_guard")
