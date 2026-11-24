"""Tenants, per-tenant AI settings, users.tenant_id. Idempotent."""
revision = "0007"
down_revision = "0006"
import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    tables = insp.get_table_names()
    if "tenants" not in tables:
        op.create_table(
            "tenants",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("name", sa.String(120), nullable=False, unique=True),
            sa.Column("slug", sa.String(40), nullable=False, unique=True),
            sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True)),
        )
    if "ai_settings" not in tables:
        op.create_table(
            "ai_settings",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("scope", sa.String(40), nullable=False, unique=True),
            sa.Column("tenant_id", sa.Integer, sa.ForeignKey("tenants.id")),
            sa.Column("base_url", sa.String(300), nullable=False),
            sa.Column("model", sa.String(100), nullable=False, server_default="qwen"),
            sa.Column("api_key_enc", sa.Text),
            sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
            sa.Column("updated_by", sa.Integer, sa.ForeignKey("users.id")),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
        )
    if "tenant_id" not in {c["name"] for c in insp.get_columns("users")}:
        with op.batch_alter_table("users") as b:
            b.add_column(sa.Column("tenant_id", sa.Integer, sa.ForeignKey("tenants.id")))


def downgrade() -> None:
    with op.batch_alter_table("users") as b:
        b.drop_column("tenant_id")
    op.drop_table("ai_settings")
    op.drop_table("tenants")
