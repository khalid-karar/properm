"""api_keys: keys for the read-only data feeds. Idempotent."""
revision = "0011"
down_revision = "0010"
import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    if "api_keys" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.Integer, sa.ForeignKey("tenants.id"), index=True),
        sa.Column("name", sa.String(120)),
        sa.Column("prefix", sa.String(12)),
        sa.Column("key_hash", sa.String(64), unique=True),
        sa.Column("active", sa.Boolean),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table("api_keys")
