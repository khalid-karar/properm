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
    cost_rate_hour: Mapped[float | None] = mapped_column(Float, nullable=True)  # restricted data
    line_manager_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    delegate_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


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
