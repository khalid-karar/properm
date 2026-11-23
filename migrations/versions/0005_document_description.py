"""Short description on project documents. Idempotent."""
revision = "0005"
down_revision = "0004"
import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("documents")}
    if "description" not in cols:
        op.add_column("documents", sa.Column("description", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "description")
