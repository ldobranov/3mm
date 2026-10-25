"""Pin data-only language packs to manifest-v2 packages; preserve existing data."""
from alembic import op
import sqlalchemy as sa
revision = "0ae56c1324d5"
down_revision = "fcd45b0213c4"
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table("language_packs") as batch:
        batch.add_column(sa.Column("module_package_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_language_pack_module", "module_packages", ["module_package_id"], ["id"])

def downgrade():
    with op.batch_alter_table("language_packs") as batch:
        batch.drop_constraint("fk_language_pack_module", type_="foreignkey")
        batch.drop_column("module_package_id")
