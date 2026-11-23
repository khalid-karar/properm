"""Baseline: the schema as of 2026-11-23. Later changes are real migrations (alembic revision --autogenerate)."""
revision = "0001"
down_revision = None
from alembic import op

from app.models import Base


def upgrade() -> None:
    Base.metadata.create_all(op.get_bind())


def downgrade() -> None:
    raise RuntimeError("The baseline is not reversible; restore from a backup instead.")
