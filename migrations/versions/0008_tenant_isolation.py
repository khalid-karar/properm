"""Tenant isolation: tenant_id (NULL = platform owner's organisation) on every client-owned table. Idempotent."""
revision = "0008"
down_revision = "0007"
import sqlalchemy as sa
from alembic import op

TABLES = ['account_security', 'activities', 'activity_dependencies', 'activity_forecasts', 'activity_progress', 'activity_staff_limits', 'ai_drafts', 'alert_actions', 'alerts', 'assignments', 'assumptions', 'audit_log', 'backlog_items', 'baseline_rates', 'benefits', 'change_requests', 'closure_items', 'closure_notes', 'comm_items', 'compliance_requirements', 'config_items', 'contract_payments', 'contracts', 'cost_entries', 'decision_records', 'deliverables', 'document_versions', 'documents', 'gate_reviews', 'holidays', 'issues', 'job_runs', 'leave_requests', 'lessons', 'login_events', 'mail_config', 'milestones', 'notifications', 'objective_links', 'opportunities', 'outbox', 'period_locks', 'planned_allocations', 'program_budgets', 'program_issues', 'program_risks', 'programs', 'project_actions', 'project_charters', 'project_compliance', 'project_dependencies', 'project_kpis', 'project_reserves', 'project_scores', 'project_templates', 'projects', 'proposals', 'quality_items', 'raci_entries', 'rate_card', 'report_schedules', 'requirements', 'reserve_drawdowns', 'resource_requests', 'risk_responses', 'risks', 'rule_config', 'rule_violations', 'settings', 'snapshots', 'sprints', 'stakeholder_engagement', 'stakeholders', 'strategic_objectives', 'team_norms', 'tenders', 'timesheet_entries', 'two_factor', 'user_certs', 'user_home', 'user_prefs', 'user_skills', 'vendor_reviews', 'week_submissions', 'weekly_reports']


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    have = set(insp.get_table_names())
    for t in TABLES:
        if t not in have or "tenant_id" in {c["name"] for c in insp.get_columns(t)}:
            continue
        op.add_column(t, sa.Column("tenant_id", sa.Integer, nullable=True))
        op.create_index(f"ix_{t}_tenant_id"[:60], t, ["tenant_id"])
        if op.get_bind().dialect.name != "sqlite":
            op.create_foreign_key(f"fk_{t}_tenant"[:60], t, "tenants", ["tenant_id"], ["id"])


def downgrade() -> None:
    for t in TABLES:
        op.drop_index(f"ix_{t}_tenant_id"[:60], table_name=t)
        op.drop_column(t, "tenant_id")
