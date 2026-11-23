from datetime import date, datetime, timezone
from sqlalchemy import (Boolean, Date, DateTime, Float, ForeignKey, Integer, JSON, LargeBinary, String,
                        Text, UniqueConstraint, event)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def now():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    """User and staff master in one record for the MVP (2.1)."""
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    staff_id: Mapped[str] = mapped_column(String(40), unique=True)
    full_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(30))
    is_ccb: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    job_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    department: Mapped[str | None] = mapped_column(String(200), nullable=True)
    capacity_hours_week: Mapped[float] = mapped_column(Float, default=40.0)
    rate_grade: Mapped[str | None] = mapped_column(String(40), nullable=True)   # links to the rate card (restricted data)
    line_manager_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    delegate_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)   # optional; used only for e-mail notifications


class Program(Base):
    """A group of related projects (program/portfolio grouping)."""
    __tablename__ = "programs"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(300))
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(60), unique=True)
    name: Mapped[str] = mapped_column(String(300))
    state: Mapped[str] = mapped_column(String(20))
    previous_state: Mapped[str | None] = mapped_column(String(20), nullable=True)
    pm_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    planned_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    planned_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    budget_ceiling: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="SAR")
    project_type: Mapped[str] = mapped_column(String(20), default="predictive")
    baseline_version: Mapped[int] = mapped_column(Integer, default=0)
    program_id: Mapped[int | None] = mapped_column(ForeignKey("programs.id"), nullable=True)
    client: Mapped[str | None] = mapped_column(String(200), nullable=True)
    sponsor: Mapped[str | None] = mapped_column(String(200), nullable=True)
    scope_statement: Mapped[str | None] = mapped_column(Text, nullable=True)
    pm = relationship("User", foreign_keys=[pm_id])


class Assignment(Base):
    __tablename__ = "assignments"
    __table_args__ = (UniqueConstraint("project_id", "user_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))


class Activity(Base):
    __tablename__ = "activities"
    __table_args__ = (UniqueConstraint("project_id", "code"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    code: Mapped[str] = mapped_column(String(60))
    name: Mapped[str] = mapped_column(String(300))
    phase: Mapped[str] = mapped_column(String(20))      # tendering | planning | execution | closing
    planned_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    locked: Mapped[bool] = mapped_column(Boolean, default=False)  # True once in an approved baseline
    baseline_cost: Mapped[float | None] = mapped_column(Float, nullable=True)  # BAC of this activity (restricted)
    planned_start: Mapped[date | None] = mapped_column(Date, nullable=True)     # used to phase PV
    planned_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    baseline_version: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ActivityStaffLimit(Base):
    """Per-activity max hours for one staff member (overrides the default cap)."""
    __tablename__ = "activity_staff_limits"
    __table_args__ = (UniqueConstraint("activity_id", "user_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    max_hours: Mapped[float] = mapped_column(Float)


class ChangeRequest(Base):
    __tablename__ = "change_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    change_type: Mapped[str] = mapped_column(String(20))
    description: Mapped[str] = mapped_column(Text)
    impact_hours_delta: Mapped[float | None] = mapped_column(Float, nullable=True)
    impact_cost_delta: Mapped[float | None] = mapped_column(Float, nullable=True)
    impact_schedule_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="requested")  # requested|approved|rejected|applied
    requested_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_baseline_version: Mapped[int | None] = mapped_column(Integer, nullable=True)


class TimesheetEntry(Base):
    __tablename__ = "timesheet_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    activity_id: Mapped[int | None] = mapped_column(ForeignKey("activities.id"), nullable=True)
    nonproject_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    entry_date: Mapped[date] = mapped_column(Date)
    hours: Mapped[float] = mapped_column(Float)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="submitted")  # submitted|approved|rejected
    overtime_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    overtime_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    flags: Mapped[list] = mapped_column(JSON, default=list)
    original_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class RateCard(Base):
    """Effective-dated hourly cost rate per grade. Append-only: a change is a new row with a later
    effective_from, so past cost is never repriced (2.1.5)."""
    __tablename__ = "rate_card"
    __table_args__ = (UniqueConstraint("grade", "effective_from"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    grade: Mapped[str] = mapped_column(String(40))
    hourly_rate: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3))
    effective_from: Mapped[date] = mapped_column(Date)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))


class BaselineRate(Base):
    """Rates in force when a baseline was locked (audit of what the cost baseline was priced with)."""
    __tablename__ = "baseline_rates"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    baseline_version: Mapped[int] = mapped_column(Integer)
    grade: Mapped[str] = mapped_column(String(40))
    hourly_rate: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3))


class ActivityProgress(Base):
    """2.6 weekly progress per activity (percent-complete method in the MVP)."""
    __tablename__ = "activity_progress"
    __table_args__ = (UniqueConstraint("activity_id", "week_start"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id"))
    week_start: Mapped[date] = mapped_column(Date)
    pct_complete: Mapped[float] = mapped_column(Float)
    etc_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class CostEntry(Base):
    """2.7 non-labor cost ledger. Labor cost is computed from approved hours x rate, never entered."""
    __tablename__ = "cost_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    activity_id: Mapped[int | None] = mapped_column(ForeignKey("activities.id"), nullable=True)
    category: Mapped[str] = mapped_column(String(60))
    vendor: Mapped[str | None] = mapped_column(String(200), nullable=True)
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3))
    entry_date: Mapped[date] = mapped_column(Date)
    doc_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    cost_status: Mapped[str] = mapped_column(String(20), default="invoiced")   # committed | invoiced | paid
    approval: Mapped[str] = mapped_column(String(20), default="approved")      # pending | approved
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class PlannedAllocation(Base):
    """2.1b planned hours per staff per week (forward-looking capacity)."""
    __tablename__ = "planned_allocations"
    __table_args__ = (UniqueConstraint("project_id", "user_id", "week_start"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    week_start: Mapped[date] = mapped_column(Date)
    hours: Mapped[float] = mapped_column(Float)


class Risk(Base):
    __tablename__ = "risks"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    title: Mapped[str] = mapped_column(String(300))
    category: Mapped[str | None] = mapped_column(String(60), nullable=True)
    probability: Mapped[int] = mapped_column(Integer)      # 1-5
    impact: Mapped[int] = mapped_column(Integer)           # 1-5
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open|mitigating|occurred|closed
    last_reviewed: Mapped[date | None] = mapped_column(Date, nullable=True)

    @property
    def score(self) -> int:
        return self.probability * self.impact


class Issue(Base):
    __tablename__ = "issues"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(String(10))      # low|medium|high|critical
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open|in_progress|resolved|closed
    linked_risk_id: Mapped[int | None] = mapped_column(ForeignKey("risks.id"), nullable=True)


class WeeklyReport(Base):
    __tablename__ = "weekly_reports"
    __table_args__ = (UniqueConstraint("project_id", "week_start"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    week_start: Mapped[date] = mapped_column(Date)
    pm_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    narrative: Mapped[dict] = mapped_column(JSON, default=dict)
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)   # auto-populated figures at submit time
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Alert(Base):
    """3.3 rule-generated alert; 3.5 triage lifecycle. Deduplicated per (project, rule, subject)."""
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    rule: Mapped[str] = mapped_column(String(40))
    dedupe_key: Mapped[str] = mapped_column(String(200))
    severity: Mapped[str] = mapped_column(String(10))            # info | warning | critical
    cause: Mapped[str] = mapped_column(Text)
    suggested_action: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open|acknowledged|assigned|resolved|closed|dismissed
    active: Mapped[bool] = mapped_column(Boolean, default=True)      # does the condition still hold?
    escalated: Mapped[bool] = mapped_column(Boolean, default=False)
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AlertAction(Base):
    """Audit trail of every triage step (3.5.4)."""
    __tablename__ = "alert_actions"
    id: Mapped[int] = mapped_column(primary_key=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id"))
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(30))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ClosureItem(Base):
    __tablename__ = "closure_items"
    __table_args__ = (UniqueConstraint("project_id", "key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    key: Mapped[str] = mapped_column(String(40))
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    done_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class Benefit(Base):
    """Benefits register: what the project is meant to deliver, and how far it has been realised."""
    __tablename__ = "benefits"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    title: Mapped[str] = mapped_column(String(300))
    metric: Mapped[str | None] = mapped_column(String(200), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    baseline: Mapped[float | None] = mapped_column(Float, nullable=True)
    target: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual: Mapped[float | None] = mapped_column(Float, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="planned")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class Holiday(Base):
    __tablename__ = "holidays"
    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[date] = mapped_column(Date, unique=True)
    name: Mapped[str] = mapped_column(String(200))


class RuleViolation(Base):
    __tablename__ = "rule_violations"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    rule: Mapped[str] = mapped_column(String(10))
    severity: Mapped[str] = mapped_column(String(10))
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PeriodLock(Base):
    __tablename__ = "period_locks"
    id: Mapped[int] = mapped_column(primary_key=True)
    locked_through: Mapped[date] = mapped_column(Date)
    locked_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class RuleConfig(Base):
    __tablename__ = "rule_config"
    rule: Mapped[str] = mapped_column(String(10), primary_key=True)
    severity: Mapped[str] = mapped_column(String(10))


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[float] = mapped_column(Float)


class AuditLog(Base):
    """Append-only: updates and deletes raise (4.2)."""
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(60))
    entity: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class Outbox(Base):
    """Transactional outbox for events (Section 6). A dispatcher can be added later."""
    __tablename__ = "outbox"
    id: Mapped[int] = mapped_column(primary_key=True)
    event: Mapped[str] = mapped_column(String(60))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    dispatched: Mapped[bool] = mapped_column(Boolean, default=False)


class Notification(Base):
    """In-app notification produced from the outbox by app.notify.dispatch."""
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(60))
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    link: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    emailed: Mapped[bool] = mapped_column(Boolean, default=False)


class ReportSchedule(Base):
    """A recurring report delivered as a notification (and e-mail when configured)."""
    __tablename__ = "report_schedules"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(20))            # portfolio | project
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    frequency: Mapped[str] = mapped_column(String(10))       # weekly | monthly
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_on: Mapped[date | None] = mapped_column(Date, nullable=True)


class AiDraft(Base):
    """Output of the AI layer. Always a draft: nothing is applied to project data until a person reviews it."""
    __tablename__ = "ai_drafts"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))            # plan | narrative | alert_action
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    alert_id: Mapped[int | None] = mapped_column(ForeignKey("alerts.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")   # draft | applied | rejected
    input_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    output: Mapped[dict] = mapped_column(JSON, default=dict)
    model: Mapped[str] = mapped_column(String(100))
    mode: Mapped[str] = mapped_column(String(10))            # stub | live
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Document(Base):
    """Uploaded project file (contract, charter, other). Stored in the database so no extra file service is needed."""
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))            # contract | charter | scope | other
    filename: Mapped[str] = mapped_column(String(200))
    size: Mapped[int] = mapped_column(Integer)
    content: Mapped[bytes] = mapped_column(LargeBinary)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Stakeholder(Base):
    __tablename__ = "stakeholders"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    organisation: Mapped[str | None] = mapped_column(String(200), nullable=True)
    role: Mapped[str | None] = mapped_column(String(200), nullable=True)
    power: Mapped[int] = mapped_column(Integer, default=3)       # 1-5
    interest: Mapped[int] = mapped_column(Integer, default=3)    # 1-5
    engagement: Mapped[str | None] = mapped_column(Text, nullable=True)


@event.listens_for(AuditLog, "before_update")
def _no_update(mapper, connection, target):
    raise RuntimeError("audit_log is append-only")


@event.listens_for(AuditLog, "before_delete")
def _no_delete(mapper, connection, target):
    raise RuntimeError("audit_log is append-only")


class Milestone(Base):
    __tablename__ = "milestones"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(String(300))
    due_date: Mapped[date] = mapped_column(Date)
    achieved_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    activity_id: Mapped[int | None] = mapped_column(ForeignKey("activities.id"), nullable=True)


class ProjectKpi(Base):
    __tablename__ = "project_kpis"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(String(200))
    unit: Mapped[str | None] = mapped_column(String(30), nullable=True)
    target: Mapped[float] = mapped_column(Float)
    actual: Mapped[float | None] = mapped_column(Float, nullable=True)
    higher_is_better: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ActivityDependency(Base):
    """Finish-to-start link: `activity_id` cannot start before `predecessor_id` finishes."""
    __tablename__ = "activity_dependencies"
    __table_args__ = (UniqueConstraint("activity_id", "predecessor_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id"))
    predecessor_id: Mapped[int] = mapped_column(ForeignKey("activities.id"))


class Snapshot(Base):
    """One row per project per day, so RAG / CPI / SPI can be shown as a trend (written lazily and on demand)."""
    __tablename__ = "snapshots"
    __table_args__ = (UniqueConstraint("project_id", "snap_date"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    snap_date: Mapped[date] = mapped_column(Date)
    rag: Mapped[str] = mapped_column(String(10))
    progress_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    cpi: Mapped[float | None] = mapped_column(Float, nullable=True)
    spi: Mapped[float | None] = mapped_column(Float, nullable=True)
    open_risks: Mapped[int] = mapped_column(Integer, default=0)
    open_alerts: Mapped[int] = mapped_column(Integer, default=0)


class ConfigItem(Base):
    """Administrator-maintained list entries (non-project codes, risk categories, KPI templates, closure items)."""
    __tablename__ = "config_items"
    __table_args__ = (UniqueConstraint("list_key", "code"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    list_key: Mapped[str] = mapped_column(String(30))
    code: Mapped[str] = mapped_column(String(40))
    label: Mapped[str] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)


class UserPref(Base):
    """Personal notification choices (profile page)."""
    __tablename__ = "user_prefs"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    muted_kinds: Mapped[list] = mapped_column(JSON, default=list)
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Proposal(Base):
    """Project intake: a business case that a decision maker approves before it becomes a project."""
    __tablename__ = "proposals"
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(60))
    name: Mapped[str] = mapped_column(String(300))
    business_case: Mapped[str] = mapped_column(Text)
    expected_benefits: Mapped[str | None] = mapped_column(Text, nullable=True)
    client: Mapped[str | None] = mapped_column(String(200), nullable=True)
    sponsor: Mapped[str | None] = mapped_column(String(200), nullable=True)
    est_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="SAR")
    est_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    est_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    strategic_fit: Mapped[int] = mapped_column(Integer, default=3)
    value: Mapped[int] = mapped_column(Integer, default=3)
    urgency: Mapped[int] = mapped_column(Integer, default=3)
    risk_level: Mapped[int] = mapped_column(Integer, default=3)
    status: Mapped[str] = mapped_column(String(30), default="submitted")
    submitted_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class GateReview(Base):
    """Stage gate: checks and a recorded decision before a project moves to the next stage."""
    __tablename__ = "gate_reviews"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    gate: Mapped[str] = mapped_column(String(40))          # planning_execution | execution_closing
    checks: Mapped[list] = mapped_column(JSON, default=list)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    requested_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DecisionRecord(Base):
    """Decision log: every governance decision with its rationale and conditions."""
    __tablename__ = "decision_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity: Mapped[str] = mapped_column(String(30))        # proposal | gate | change
    entity_id: Mapped[int] = mapped_column(Integer)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(300))
    outcome: Mapped[str] = mapped_column(String(30))
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    conditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ActivityForecast(Base):
    """PM's forecast finish date for an activity (hours to complete come from the weekly progress update)."""
    __tablename__ = "activity_forecasts"
    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id"), primary_key=True)
    forecast_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[int] = mapped_column(ForeignKey("users.id"))


class ProjectAction(Base):
    """Action log: agreed actions with an owner and a due date."""
    __tablename__ = "project_actions"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open")       # open | done | cancelled
    done_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))


class Lesson(Base):
    """Lessons learned register, searchable across projects."""
    __tablename__ = "lessons"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    category: Mapped[str] = mapped_column(String(40))
    impact: Mapped[str] = mapped_column(String(10))                       # positive | negative
    what_happened: Mapped[str] = mapped_column(Text)
    recommendation: Mapped[str] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class LeaveRequest(Base):
    """Planned leave, approved by the line manager; approved leave lowers planning capacity."""
    __tablename__ = "leave_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    start: Mapped[date] = mapped_column(Date)
    end: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(20), default="annual")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="requested")   # requested | approved | rejected | cancelled
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class WeekSubmission(Base):
    """A person's declaration that a week's timesheet is complete."""
    __tablename__ = "week_submissions"
    __table_args__ = (UniqueConstraint("user_id", "week_start"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    week_start: Mapped[date] = mapped_column(Date)
    total_hours: Mapped[float] = mapped_column(Float)
    missing_days: Mapped[list] = mapped_column(JSON, default=list)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ProjectScore(Base):
    """Strategic scores for a running project, so the whole portfolio can be ranked with the proposals."""
    __tablename__ = "project_scores"
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    strategic_fit: Mapped[int] = mapped_column(Integer, default=3)
    value: Mapped[int] = mapped_column(Integer, default=3)
    urgency: Mapped[int] = mapped_column(Integer, default=3)
    risk_level: Mapped[int] = mapped_column(Integer, default=3)
    updated_by: Mapped[int] = mapped_column(ForeignKey("users.id"))


class ProjectDependency(Base):
    """Cross-project dependency: a project needs another project's milestone (or finish) by a date."""
    __tablename__ = "project_dependencies"
    id: Mapped[int] = mapped_column(primary_key=True)
    program_id: Mapped[int] = mapped_column(ForeignKey("programs.id"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))                 # the project that waits
    predecessor_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))             # the project that delivers
    milestone_id: Mapped[int | None] = mapped_column(ForeignKey("milestones.id"), nullable=True)
    needed_by: Mapped[date] = mapped_column(Date)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProgramRisk(Base):
    """Risk owned at program level (not by one project)."""
    __tablename__ = "program_risks"
    id: Mapped[int] = mapped_column(primary_key=True)
    program_id: Mapped[int] = mapped_column(ForeignKey("programs.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    probability: Mapped[int] = mapped_column(Integer)
    impact: Mapped[int] = mapped_column(Integer)
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open")

    @property
    def score(self) -> int:
        return self.probability * self.impact


class AccountSecurity(Base):
    """Sign-in protection per user: failed attempts, lockout, forced password change."""
    __tablename__ = "account_security"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LoginEvent(Base):
    """Sign-in history (successes and failures)."""
    __tablename__ = "login_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    staff_id: Mapped[str] = mapped_column(String(40), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ok: Mapped[bool] = mapped_column(Boolean)
    reason: Mapped[str | None] = mapped_column(String(60), nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
