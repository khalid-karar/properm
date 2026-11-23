"""Tender (bid) stage. Idempotent."""
revision = "0006"
down_revision = "0005"
import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    if "tenders" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "tenders",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id"), nullable=False, unique=True),
        sa.Column("deadline", sa.Date),
        sa.Column("scores", sa.JSON, nullable=False),
        sa.Column("checklist", sa.JSON, nullable=False),
        sa.Column("margin_pct", sa.Float, nullable=False, server_default="20"),
        sa.Column("decision", sa.String(10), nullable=False, server_default="open"),
        sa.Column("decision_note", sa.Text),
        sa.Column("decided_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("outcome", sa.String(10), nullable=False, server_default="pending"),
        sa.Column("outcome_note", sa.Text),
        sa.Column("outcome_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table("tenders")
