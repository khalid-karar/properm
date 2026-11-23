"""Indexes for the busiest queries (timesheets by person/project/status, audit log, FK look-ups). Idempotent."""
revision = "0003"
down_revision = "0002"
import sqlalchemy as sa
from alembic import op

from app.models import HOT_INDEXES


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    for name, table, cols in HOT_INDEXES:
        if table in insp.get_table_names() and name not in {i["name"] for i in insp.get_indexes(table)}:
            op.create_index(name, table, list(cols))


def downgrade() -> None:
    for name, table, _ in HOT_INDEXES:
        op.drop_index(name, table_name=table)
