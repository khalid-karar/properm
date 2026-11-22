"""CSV exports (UTF-8 with BOM so Excel shows Arabic correctly) and a print-friendly project report."""
import csv
import io
from datetime import date
from html import escape

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, Response

from ..alerts import rag_status
from ..deps import current_user, get_db
from ..evm import compute_evm
from ..models import Activity, Alert, Benefit, CostEntry, Issue, Project, Risk, TimesheetEntry, User
from .alerts import _visible
from .dashboards import EXEC, overall_pct
from .governance import realization_pct
from .projects import can_manage, can_view, can_view_cost, get_project

router = APIRouter(tags=["exports"])


def _safe(v):
    """Neutralise spreadsheet formula injection: a cell starting with = + - @ would be executed by Excel."""
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + v
    return "" if v is None else v


def csv_response(name: str, header: list, rows: list) -> Response:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    for r in rows:
        w.writerow([_safe(v) for v in r])
    return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/export/timesheets.csv")
def export_timesheets(project_id: int | None = None, start: date | None = None, end: date | None = None,
                      db=Depends(get_db), user: User = Depends(current_user)):
    q = db.query(TimesheetEntry)
    if project_id:
        q = q.filter(TimesheetEntry.project_id == project_id)
    if start:
        q = q.filter(TimesheetEntry.entry_date >= start)
    if end:
        q = q.filter(TimesheetEntry.entry_date <= end)
    names = {u.id: u.full_name for u in db.query(User)}
    rows, can = [], {}
    for e in q.order_by(TimesheetEntry.entry_date, TimesheetEntry.id):
        if e.user_id != user.id:
            if user.role == "STAFF":
                continue
            if e.project_id is None:
                if user.role not in ("PMO", "ADMIN"):
                    continue
            else:
                if e.project_id not in can:
                    can[e.project_id] = can_manage(db, user, db.get(Project, e.project_id)) or user.role in EXEC
                if not can[e.project_id]:
                    continue
        p = db.get(Project, e.project_id) if e.project_id else None
        rows.append([e.entry_date, names.get(e.user_id), p.number if p else e.nonproject_code, e.hours, e.status, e.description, e.overtime_reason])
    return csv_response("timesheets.csv", ["date", "person", "project_or_code", "hours", "status", "description", "overtime_reason"], rows)


@router.get("/export/alerts.csv")
def export_alerts(db=Depends(get_db), user: User = Depends(current_user)):
    rows = [[a.id, (db.get(Project, a.project_id).number), a.rule, a.severity, a.status, a.cause, a.suggested_action, a.due_date]
            for a in db.query(Alert).order_by(Alert.id) if _visible(db, user, a)]
    return csv_response("alerts.csv", ["id", "project", "rule", "severity", "status", "cause", "suggested_action", "due_date"], rows)


@router.get("/export/portfolio.csv")
def export_portfolio(as_of: date | None = None, db=Depends(get_db), user: User = Depends(current_user)):
    if user.role not in EXEC:
        raise HTTPException(403, "Portfolio export requires PMO, ADMIN, DECISION_MAKER or PROGRAM_MANAGER")
    as_of = as_of or date.today()
    rows = []
    for p in db.query(Project).order_by(Project.id):
        e = compute_evm(db, p, as_of) if p.state in ("execution", "closing") else {}
        rows.append([p.number, p.name, p.state, rag_status(db, p), overall_pct(db, p, as_of), e.get("CPI"), e.get("SPI"), e.get("BAC"), e.get("AC"), e.get("currency")])
    return csv_response("portfolio.csv", ["number", "name", "state", "rag", "progress_pct", "cpi", "spi", "bac", "ac", "currency"], rows)


@router.get("/projects/{pid}/export/costs.csv")
def export_costs(pid: int, db=Depends(get_db), user: User = Depends(current_user)):
    p = get_project(db, pid)
    if not can_view_cost(db, user, p):
        raise HTTPException(403, "cost_view permission required")
    rows = [[c.entry_date, c.category, c.vendor, c.amount, c.currency, c.cost_status, c.approval, c.doc_ref] for c in db.query(CostEntry).filter_by(project_id=pid).order_by(CostEntry.id)]
    return csv_response(f"{p.number}-costs.csv", ["date", "category", "vendor", "amount", "currency", "status", "approval", "doc_ref"], rows)


@router.get("/projects/{pid}/export/benefits.csv")
def export_benefits(pid: int, db=Depends(get_db), user: User = Depends(current_user)):
    p = get_project(db, pid)
    if not can_view(db, user, p):
        raise HTTPException(403, "No access to this project")
    rows = [[b.title, b.metric, b.unit, b.baseline, b.target, b.actual, realization_pct(b), b.status, b.due_date] for b in db.query(Benefit).filter_by(project_id=pid).order_by(Benefit.id)]
    return csv_response(f"{p.number}-benefits.csv", ["title", "metric", "unit", "baseline", "target", "actual", "realization_pct", "status", "due_date"], rows)


# ---------------- summaries (shared with scheduled reports) ----------------
def project_summary(db, p: Project, as_of: date, with_cost: bool = True) -> str:
    lines = [f"{p.number} {p.name} - state: {p.state}, status: {rag_status(db, p)}, progress: {overall_pct(db, p, as_of)}%"]
    if with_cost and p.state in ("execution", "closing"):
        e = compute_evm(db, p, as_of)
        if e.get("available"):
            lines.append(f"CPI {e['CPI']}, SPI {e['SPI']}, AC {e['AC']} {e['currency']} of BAC {e['BAC']}")
    alerts = db.query(Alert).filter(Alert.project_id == p.id, Alert.active.is_(True), Alert.status.in_(("open", "acknowledged", "assigned"))).all()
    lines.append(f"Open alerts: {len(alerts)}; open risks: {db.query(Risk).filter(Risk.project_id == p.id, Risk.status.in_(('open', 'mitigating'))).count()}; open issues: {db.query(Issue).filter(Issue.project_id == p.id, Issue.status.in_(('open', 'in_progress'))).count()}")
    return "\n".join(lines)


def portfolio_summary(db, as_of: date) -> str:
    counts = {"RED": 0, "AMBER": 0, "GREEN": 0, "GREY": 0}
    lines = []
    for p in db.query(Project).filter(Project.state != "archived").order_by(Project.id):
        r = rag_status(db, p)
        counts[r] += 1
        lines.append(f"{r}: {p.number} {p.name} ({p.state}, {overall_pct(db, p, as_of)}%)")
    return f"Red {counts['RED']}, Amber {counts['AMBER']}, Green {counts['GREEN']}\n" + "\n".join(lines)


# ---------------- print-friendly report ----------------
def _tbl(head, rows):
    h = "".join(f"<th>{escape(str(x))}</th>" for x in head)
    b = "".join("<tr>" + "".join(f"<td>{escape('' if v is None else str(v))}</td>" for v in r) + "</tr>" for r in rows)
    return f"<table><thead><tr>{h}</tr></thead><tbody>{b or '<tr><td>None</td></tr>'}</tbody></table>"


@router.get("/projects/{pid}/report.html", response_class=HTMLResponse)
def project_report(pid: int, as_of: date | None = None, db=Depends(get_db), user: User = Depends(current_user)):
    p = get_project(db, pid)
    if not can_view(db, user, p):
        raise HTTPException(403, "No access to this project")
    as_of = as_of or date.today()
    cost_ok = can_view_cost(db, user, p)
    parts = [f"<h1>{escape(p.number)} · {escape(p.name)}</h1><p>State: {escape(p.state)} · Status: {escape(rag_status(db, p))} · As of {as_of} · Baseline v{p.baseline_version}</p>",
             f"<pre>{escape(project_summary(db, p, as_of, cost_ok))}</pre>"]
    acts = db.query(Activity).filter_by(project_id=pid, phase="execution").order_by(Activity.id).all()
    from ..evm import latest_progress
    parts.append("<h2>Activities</h2>" + _tbl(["Code", "Name", "Planned hours", "% complete"],
                 [[a.code, a.name, a.planned_hours, (latest_progress(db, a.id, as_of).pct_complete if latest_progress(db, a.id, as_of) else 0)] for a in acts]))
    parts.append("<h2>Risks</h2>" + _tbl(["Title", "Score", "Status"], [[r.title, r.score, r.status] for r in db.query(Risk).filter_by(project_id=pid)]))
    parts.append("<h2>Issues</h2>" + _tbl(["Title", "Severity", "Status", "Due"], [[i.title, i.severity, i.status, i.due_date] for i in db.query(Issue).filter_by(project_id=pid)]))
    parts.append("<h2>Benefits</h2>" + _tbl(["Benefit", "Baseline", "Target", "Actual", "Realised %", "Status"],
                 [[b.title, b.baseline, b.target, b.actual, realization_pct(b), b.status] for b in db.query(Benefit).filter_by(project_id=pid)]))
    if cost_ok:
        parts.append("<h2>Costs</h2>" + _tbl(["Date", "Category", "Vendor", "Amount", "Currency", "Approval"],
                     [[c.entry_date, c.category, c.vendor, c.amount, c.currency, c.approval] for c in db.query(CostEntry).filter_by(project_id=pid).order_by(CostEntry.id)]))
    css = ("body{font:14px/1.5 system-ui,sans-serif;max-width:900px;margin:24px auto;padding:0 16px;color:#111}h1{color:#0b2545}h2{border-bottom:2px solid #c9a227;padding-bottom:2px}"
           "table{border-collapse:collapse;width:100%;margin-bottom:12px}th,td{border:1px solid #ccc;padding:4px 8px;text-align:start}th{background:#0b2545;color:#fff}pre{background:#f4f4f4;padding:8px}@media print{body{margin:0}}")
    return HTMLResponse(f"<!doctype html><html><head><meta charset='utf-8'><title>{escape(p.number)} report</title><style>{css}</style></head><body>{''.join(parts)}</body></html>")
