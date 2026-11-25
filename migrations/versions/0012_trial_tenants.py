"""tenants: sandbox trial columns. Idempotent."""
revision = "0012"
down_revision = "0011"
import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    have = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("tenants")}
    for name, col in (("trial_until", sa.Column("trial_until", sa.DateTime(timezone=True), nullable=True)),
                      ("trial_email", sa.Column("trial_email", sa.String(200), nullable=True)),
                      ("seed_state", sa.Column("seed_state", sa.String(10), nullable=True))):
        if name not in have:
            op.add_column("tenants", col)


def downgrade() -> None:
    for name in ("seed_state", "trial_email", "trial_until"):
        op.drop_column("tenants", name)
