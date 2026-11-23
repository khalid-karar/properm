"""Closure notes for risks and issues. Idempotent."""
revision = "0004"
down_revision = "0003"
import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    if "closure_notes" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "closure_notes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("item_id", sa.Integer, nullable=False),
        sa.Column("event", sa.String(10), nullable=False),
        sa.Column("what_happened", sa.Text),
        sa.Column("how_handled", sa.Text),
        sa.Column("outcome", sa.Text),
        sa.Column("reason", sa.Text),
        sa.Column("lesson", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("by_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_closure_notes_item", "closure_notes", ["project_id", "kind", "item_id"])


def downgrade() -> None:
    op.drop_table("closure_notes")
