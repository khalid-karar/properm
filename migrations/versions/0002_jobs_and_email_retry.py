"""Scheduler job log and e-mail retry counters. Idempotent: a database created from the current models already has them."""
revision = "0002"
down_revision = "0001"
import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "job_runs" not in insp.get_table_names():
        op.create_table("job_runs", sa.Column("id", sa.Integer, primary_key=True), sa.Column("name", sa.String(40), nullable=False),
                        sa.Column("run_date", sa.Date, nullable=False), sa.Column("status", sa.String(10)), sa.Column("detail", sa.JSON),
                        sa.Column("started_at", sa.DateTime(timezone=True)), sa.UniqueConstraint("name", "run_date"))
    cols = {c["name"] for c in insp.get_columns("notifications")}
    if "email_attempts" not in cols:
        op.add_column("notifications", sa.Column("email_attempts", sa.Integer, server_default="0"))
    if "email_error" not in cols:
        op.add_column("notifications", sa.Column("email_error", sa.String(300), nullable=True))


def downgrade() -> None:
    op.drop_column("notifications", "email_error")
    op.drop_column("notifications", "email_attempts")
    op.drop_table("job_runs")
