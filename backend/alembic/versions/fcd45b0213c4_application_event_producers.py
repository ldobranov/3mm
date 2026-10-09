"""Add application producers to the existing event journal; preserve queue IDs."""

from alembic import op
import sqlalchemy as sa

revision = "fcd45b0213c4"
down_revision = "ebc34af102b3"
branch_labels = None
depends_on = None

PRODUCER_CHECK = (
    "(producer_kind = 'device' AND device_id IS NOT NULL AND application_producer IS NULL "
    "AND publication_declaration IS NULL AND publication_receipt IS NULL AND authority_epoch IS NULL) OR "
    "(producer_kind = 'application' AND device_id IS NULL AND application_producer IS NOT NULL "
    "AND publication_declaration IS NOT NULL AND publication_receipt IS NOT NULL "
    "AND authority_epoch IS NOT NULL AND length(authority_epoch) = 32)"
)


def upgrade():
    connection = op.get_bind()
    columns = {item['name']: item for item in sa.inspect(connection).get_columns('device_events')}
    # No partial-schema guessing. ORM-precreated complete schemas must match too.
    added = {'producer_kind', 'application_producer', 'publication_declaration', 'publication_receipt', 'authority_epoch'}
    if added & columns.keys():
        if not added <= columns.keys():
            raise RuntimeError('Partial event producer schema; explicit recovery required')
        inspector = sa.inspect(connection)
        checks = {item['name']: item['sqltext'] for item in inspector.get_check_constraints('device_events')}
        unique_event = any(item['column_names'] == ['event_id'] and not item.get('dialect_options')
            for item in inspector.get_unique_constraints('device_events')) or any(
            item.get('unique') and item['column_names'] == ['event_id'] and not item.get('dialect_options')
            for item in inspector.get_indexes('device_events'))
        device_fk = any(item['constrained_columns'] == ['device_id'] and item['referred_table'] == 'devices'
            and item['referred_columns'] == ['id'] and item.get('options', {}).get('ondelete') == 'CASCADE'
            for item in inspector.get_foreign_keys('device_events'))
        if (columns['device_id']['nullable'] is not True or columns['event_type']['type'].length != 160
                or columns['producer_kind']['nullable'] or columns['producer_kind']['type'].length != 16
                or columns['producer_kind'].get('default') != "'device'"
                or checks.get('ck_event_producer', '').strip() != PRODUCER_CHECK or not unique_event or not device_fk
                or any(not columns[name]['nullable'] or not isinstance(columns[name]['type'], sa.JSON)
                    or columns[name].get('default') is not None
                    for name in ('application_producer', 'publication_declaration', 'publication_receipt'))
                or not columns['authority_epoch']['nullable'] or columns['authority_epoch']['type'].length != 32
                or columns['authority_epoch'].get('default') is not None):
            raise RuntimeError('Unexpected event producer schema; explicit recovery required')
        return
    if connection.dialect.name == 'sqlite' and connection.exec_driver_sql('PRAGMA foreign_keys').scalar():
        # Batch DROP with enabled cascading FKs could delete pending deliveries.
        # Alembic's dedicated connection normally has FKs off; never guess here.
        raise RuntimeError('Event journal migration requires a dedicated FK-disabled migration connection')
    with op.batch_alter_table('device_events') as batch:
        batch.alter_column('device_id', existing_type=sa.Integer(), nullable=True)
        batch.alter_column('event_type', existing_type=sa.String(120), type_=sa.String(160), nullable=False)
        batch.add_column(sa.Column('producer_kind', sa.String(16), nullable=False, server_default='device'))
        for name in ('application_producer', 'publication_declaration', 'publication_receipt'):
            batch.add_column(sa.Column(name, sa.JSON(none_as_null=True), nullable=True))
        batch.add_column(sa.Column('authority_epoch', sa.String(32), nullable=True))
        batch.create_check_constraint('ck_event_producer', PRODUCER_CHECK)


def downgrade():
    connection = op.get_bind()
    # Refuse all unsafe multi-revision downgrade before any SQLite DDL.
    if connection.execute(sa.text("SELECT 1 FROM device_events WHERE producer_kind <> 'device' LIMIT 1")).first():
        raise RuntimeError('Application event history exists; restore a verified pre-upgrade backup')
    for table in ('application_native_reviews', 'application_authority_plans', 'application_authority_grants',
            'application_authority_actions', 'application_policy_reviews', 'application_policy_review_decisions'):
        if connection.execute(sa.text(f'SELECT 1 FROM {table} LIMIT 1')).first():
            raise RuntimeError('Authority history exists; restore a verified pre-upgrade backup')
    if (connection.execute(sa.text('SELECT revision FROM core_authority_guard WHERE singleton_id=1')).scalar_one() != 1
            or connection.execute(sa.text("SELECT 1 FROM application_extension_installations WHERE authority_mode <> 'compatibility' LIMIT 1")).first()):
        raise RuntimeError('Used authority metadata requires verified recovery')
    if (connection.execute(sa.text('SELECT 1 FROM application_event_deliveries WHERE authority_epoch IS NOT NULL LIMIT 1')).first()
            or connection.execute(sa.text("SELECT 1 FROM application_extension_installations WHERE authority_mode = 'enforced' LIMIT 1")).first()):
        raise RuntimeError('Enforced authority history requires verified recovery')
    if connection.dialect.name == 'sqlite' and connection.exec_driver_sql('PRAGMA foreign_keys').scalar():
        raise RuntimeError('Event journal migration requires a dedicated FK-disabled migration connection')
    with op.batch_alter_table('device_events') as batch:
        batch.drop_constraint('ck_event_producer', type_='check')
        for name in ('producer_kind', 'application_producer', 'publication_declaration', 'publication_receipt', 'authority_epoch'):
            batch.drop_column(name)
        batch.alter_column('device_id', existing_type=sa.Integer(), nullable=False)
        batch.alter_column('event_type', existing_type=sa.String(160), type_=sa.String(120), nullable=False)
