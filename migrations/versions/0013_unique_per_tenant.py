"""Make codes unique per organisation instead of across the whole database (project number, program code, rate card, holidays, templates,
strategic objectives, compliance codes, list items). Before this, a second organisation could not reuse a number the first one had used.
Idempotent: each table is looked at first and only changed if it still has the old single-organisation constraint."""
revision = "0013"
down_revision = "0012"
import sqlalchemy as sa
from alembic import op

TARGETS = {
    "programs": ("code",),
    "projects": ("number",),
    "rate_card": ("grade", "effective_from"),
    "holidays": ("day",),
    "project_templates": ("code",),
    "strategic_objectives": ("code",),
    "compliance_requirements": ("code",),
    "config_items": ("list_key", "code"),
}


def _name(table: str, cols) -> str:
    return f"uq_{table}_t_{'_'.join(cols)}"[:30]          # Oracle names are limited to 30 characters on older versions


def _old_constraints(insp, table, cols):
    """Unique constraints/indexes on exactly `cols` (without tenant_id): [(kind, name)]."""
    out = []
    for u in insp.get_unique_constraints(table):
        if set(u["column_names"]) == set(cols):
            out.append(("constraint", u.get("name")))
    for ix in insp.get_indexes(table):
        if ix.get("unique") and set(ix["column_names"]) == set(cols) and not any(n == ix["name"] for _, n in out) and not ix.get("duplicates_constraint"):
            out.append(("index", ix["name"]))
    return out


def _has_new(insp, table, cols) -> bool:
    want = {"tenant_id", *cols}
    return any(set(u["column_names"]) == want for u in insp.get_unique_constraints(table)) or \
        any(ix.get("unique") and set(ix["column_names"]) == want for ix in insp.get_indexes(table))


def upgrade() -> None:
    bind = op.get_bind()
    sqlite = bind.dialect.name == "sqlite"
    for table, cols in TARGETS.items():
        insp = sa.inspect(bind)
        if table not in insp.get_table_names():
            continue
        old = _old_constraints(insp, table, cols)
        if not old and _has_new(insp, table, cols):
            continue
        new_name = _name(table, cols)
        if sqlite:                                            # SQLite cannot alter constraints: rebuild the table, naming the unnamed old constraint first
            conv = {"uq": "uq_%(table_name)s_%(column_0_N_name)s"}
            with op.batch_alter_table(table, recreate="always", naming_convention=conv) as b:
                for kind, name in old:
                    if kind == "constraint":
                        b.drop_constraint(name or "uq_%s_%s" % (table, "_".join(cols)), type_="unique")
                    else:
                        b.drop_index(name)
                b.create_unique_constraint(new_name, ["tenant_id", *cols])
        else:
            for kind, name in old:
                if kind == "constraint" and name:
                    op.drop_constraint(name, table, type_="unique")
                elif kind == "index":
                    op.drop_index(name, table_name=table)
            op.create_unique_constraint(new_name, table, ["tenant_id", *cols])


def downgrade() -> None:
    pass        # going back would re-break organisations that already share a number; keep the per-organisation constraints
