"""ai_usage: one row per model call (tenant, user, characters in and out). Idempotent."""
revision = "0009"
down_revision = "0008"
import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    if "ai_usage" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "ai_usage",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.Integer, sa.ForeignKey("tenants.id"), index=True),
        sa.Column("at", sa.DateTime(timezone=True), index=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("task", sa.String(30)),
        sa.Column("model", sa.String(120)),
        sa.Column("chars_in", sa.Integer),
        sa.Column("chars_out", sa.Integer),
        sa.Column("ok", sa.Boolean),
        sa.Column("ms", sa.Integer),
    )


def downgrade() -> None:
    op.drop_table("ai_usage")
