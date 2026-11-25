"""consultation_requests: demo / consultation requests from the public landing page. Idempotent."""
revision = "0010"
down_revision = "0009"
import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    if "consultation_requests" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "consultation_requests",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), index=True),
        sa.Column("name", sa.String(120)),
        sa.Column("organization", sa.String(160)),
        sa.Column("job_title", sa.String(120)),
        sa.Column("email", sa.String(200)),
        sa.Column("phone", sa.String(40)),
        sa.Column("team_size", sa.String(20)),
        sa.Column("interest", sa.String(20)),
        sa.Column("message", sa.Text),
        sa.Column("lang", sa.String(5)),
        sa.Column("status", sa.String(20), index=True),
    )


def downgrade() -> None:
    op.drop_table("consultation_requests")
