from datetime import date, datetime, timezone
from sqlalchemy import (Boolean, Date, DateTime, Float, ForeignKey, Integer, JSON, String,
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


@event.listens_for(AuditLog, "before_update")
def _no_update(mapper, connection, target):
    raise RuntimeError("audit_log is append-only")


@event.listens_for(AuditLog, "before_delete")
def _no_delete(mapper, connection, target):
    raise RuntimeError("audit_log is append-only")
