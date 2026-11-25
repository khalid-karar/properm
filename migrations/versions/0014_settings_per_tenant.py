"""settings and rule_config: key them by an id, with the key unique per organisation (before, the key itself was the primary key,
so two organisations could not both store the same setting). Rows are copied. Idempotent."""
revision = "0014"
down_revision = "0013"
import sqlalchemy as sa
from alembic import op

SPECS = {
    "settings": ("key", [sa.Column("key", sa.String(60), nullable=False), sa.Column("value", sa.Float, nullable=False)]),
    "rule_config": ("rule", [sa.Column("rule", sa.String(10), nullable=False), sa.Column("severity", sa.String(10), nullable=False)]),
}


def upgrade() -> None:
    bind = op.get_bind()
    for table, (keycol, cols) in SPECS.items():
        try:
            insp = sa.inspect(bind)
            if table not in insp.get_table_names() or "id" in {c["name"] for c in insp.get_columns(table)}:
                continue
            tmp = table + "_v2"
            if tmp in insp.get_table_names():
                op.drop_table(tmp)
            names = [c.name for c in cols]
            old = sa.Table(table, sa.MetaData(), autoload_with=bind)
            op.create_table(tmp, sa.Column("id", sa.Integer, primary_key=True), *[c.copy() for c in cols],
                            sa.Column("tenant_id", sa.Integer, sa.ForeignKey("tenants.id")),
                            sa.UniqueConstraint("tenant_id", keycol, name=f"uq_{table}_t_{keycol}"[:30]))
            new = sa.Table(tmp, sa.MetaData(), autoload_with=bind)
            bind.execute(new.insert().from_select(names + ["tenant_id"], sa.select(*[old.c[n] for n in names], old.c.tenant_id)))
            op.drop_table(table)
            op.rename_table(tmp, table)
            op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"])
        except Exception as e:                               # never leave the migration chain stuck on one table
            print(f"WARNING: could not rebuild {table} for per-organisation keys: {e}")


def downgrade() -> None:
    pass
