"""Monthly / quarterly / annual reports for a project, a program or the whole portfolio, as JSON, print-friendly HTML, CSV or Excel."""
import calendar
from datetime import date, timedelta
from html import escape

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import func

from ..alerts import rag_status
from ..deps import current_user, get_db
from ..evm import compute_evm
from ..models import Issue, Milestone, Program, Project, ProjectKpi, Risk, Snapshot, TimesheetEntry, User
from ..xlsx import build_xlsx
from .dashboards import EXEC, overall_pct
from .exports import csv_response
from .projects import can_view, can_view_cost

router = APIRouter(tags=["periodic reports"])
HEAD = ["Project", "Name", "State", "Status", "Progress %", "CPI", "SPI", "Hours approved in period", "Cost in period", "Currency",
        "Milestones achieved", "Milestones missed", "Open risks", "Open issues"]


def period_bounds(kind: str, anchor: date) -> tuple[date, date, str]:
    if kind == "month":
        return anchor.replace(day=1), anchor.replace(day=calendar.monthrange(anchor.year, anchor.month)[1]), anchor.strftime("%B %Y")
    if kind == "quarter":
        q = (anchor.month - 1) // 3
        s = date(anchor.year, q * 3 + 1, 1)
        e_m = q * 3 + 3
        return s, date(anchor.year, e_m, calendar.monthrange(anchor.year, e_m)[1]), f"Q{q + 1} {anchor.year}"
    if kind == "year":
        return date(anchor.year, 1, 1), date(anchor.year, 12, 31), str(anchor.year)
    raise HTTPException(422, "period must be month, quarter or year")


def _row(db, p: Project, start: date, end: date, cost_ok: bool) -> dict:
    today = date.today()
    at = min(end, today)
    snap = db.query(Snapshot).filter(Snapshot.project_id == p.id, Snapshot.snap_date <= end).order_by(Snapshot.snap_date.desc()).first()
    rag = snap.rag if snap and snap.snap_date >= start else (rag_status(db, p) if end >= today else "GREY")
    hours = float(db.query(func.coalesce(func.sum(TimesheetEntry.hours), 0.0)).filter(
        TimesheetEntry.project_id == p.id, TimesheetEntry.status == "approved", TimesheetEntry.entry_date >= start, TimesheetEntry.entry_date <= end).scalar())
    out = {"project_id": p.id, "number": p.number, "name": p.name, "state": p.state, "rag": rag, "progress_pct": overall_pct(db, p, at) if at >= (p.planned_start or start) else None,
           "hours": round(hours, 1), "currency": p.currency, "cpi": None, "spi": None, "cost": None}
    if cost_ok and p.state in ("execution", "closing", "archived"):
        e1 = compute_evm(db, p, at)
        if e1.get("available"):
            e0 = compute_evm(db, p, start - timedelta(days=1)) if start > (p.planned_start or start) else {"AC": 0.0}
            out.update(cpi=e1["CPI"], spi=e1["SPI"], cost=round(e1["AC"] - (e0.get("AC") or 0.0), 2))
    ms = db.query(Milestone).filter_by(project_id=p.id).all()
    out["milestones_achieved"] = sum(1 for m in ms if m.achieved_on and start <= m.achieved_on <= end)
    out["milestones_missed"] = sum(1 for m in ms if start <= m.due_date <= end and (m.achieved_on is None or m.achieved_on > m.due_date))
    out["open_risks"] = db.query(func.count(Risk.id)).filter(Risk.project_id == p.id, Risk.status.in_(("open", "mitigating"))).scalar()
    out["open_issues"] = db.query(func.count(Issue.id)).filter(Issue.project_id == p.id, Issue.status.in_(("open", "in_progress"))).scalar()
    return out


def build_report(db, user: User, scope: str, sid: int | None, kind: str, anchor: date) -> dict:
    start, end, label = period_bounds(kind, anchor)
    if scope == "project":
        p = db.get(Project, sid or 0)
        if not p:
            raise HTTPException(404, "Project not found")
        if not can_view(db, user, p):
            raise HTTPException(403, "No access to this project")
        projects, name, cost_ok = [p], f"{p.number} · {p.name}", can_view_cost(db, user, p)
        per_project_cost = {p.id: cost_ok}
    elif scope in ("program", "portfolio"):
        if user.role not in EXEC:
            raise HTTPException(403, "Program and portfolio reports require PMO, ADMIN, DECISION_MAKER or PROGRAM_MANAGER")
        if scope == "program":
            g = db.get(Program, sid or 0)
            if not g:
                raise HTTPException(404, "Program not found")
            projects, name = db.query(Project).filter_by(program_id=g.id).filter(Project.state != "tendering").order_by(Project.id).all(), f"{g.code} · {g.name}"
        else:
            projects, name = db.query(Project).filter(Project.state != "tendering").order_by(Project.id).all(), "Portfolio"
        per_project_cost = {p.id: True for p in projects}
    else:
        raise HTTPException(422, "scope must be project, program or portfolio")
    rows = [_row(db, p, start, end, per_project_cost[p.id]) for p in projects]
    cost_tot, rag = {}, {"RED": 0, "AMBER": 0, "GREEN": 0, "GREY": 0}
    for r in rows:
        rag[r["rag"]] = rag.get(r["rag"], 0) + 1
        if r["cost"] is not None:
            cost_tot[r["currency"]] = round(cost_tot.get(r["currency"], 0.0) + r["cost"], 2)
    return {"scope": {"type": scope, "id": sid, "name": name}, "period": {"kind": kind, "start": start.isoformat(), "end": end.isoformat(), "label": label},
            "generated": date.today().isoformat(), "rows": rows, "cost_visible": any(per_project_cost.values()),
            "totals": {"hours": round(sum(r["hours"] for r in rows), 1), "cost": cost_tot, "milestones_achieved": sum(r["milestones_achieved"] for r in rows),
                       "milestones_missed": sum(r["milestones_missed"] for r in rows), "rag_counts": rag}}


def _table_rows(rep: dict) -> list:
    return [[r["number"], r["name"], r["state"], r["rag"], r["progress_pct"], r["cpi"], r["spi"], r["hours"], r["cost"], r["currency"], r["milestones_achieved"], r["milestones_missed"], r["open_risks"], r["open_issues"]]
            for r in rep["rows"]]


def _extra_sheets(db, rep: dict) -> list:
    if rep["scope"]["type"] != "project" or not rep["rows"]:
        return []
    pid, s, e = rep["rows"][0]["project_id"], rep["period"]["start"], rep["period"]["end"]
    ms = [[m.name, m.due_date, m.achieved_on, "achieved" if m.achieved_on else "open"] for m in db.query(Milestone).filter_by(project_id=pid).order_by(Milestone.due_date)]
    kp = [[k.name, k.unit, k.target, k.actual] for k in db.query(ProjectKpi).filter_by(project_id=pid)]
    rk = [[r.title, r.probability, r.impact, r.score, r.status] for r in db.query(Risk).filter_by(project_id=pid).order_by(Risk.id)]
    iss = [[i.title, i.severity, i.status, i.due_date] for i in db.query(Issue).filter_by(project_id=pid).order_by(Issue.id)]
    return [("Milestones", ["Milestone", "Due", "Achieved on", "Status"], ms), ("KPIs", ["KPI", "Unit", "Target", "Actual"], kp),
            ("Risks", ["Risk", "Probability", "Impact", "Score", "Status"], rk), ("Issues", ["Issue", "Severity", "Status", "Due"], iss)]


def _html(rep: dict) -> str:
    th = "".join(f"<th>{escape(h)}</th>" for h in HEAD)
    tr = "".join("<tr>" + "".join(f"<td>{escape('' if v is None else str(v))}</td>" for v in r) + "</tr>" for r in _table_rows(rep))
    t = rep["totals"]
    cost = ", ".join(f"{v:,.0f} {k}" for k, v in t["cost"].items()) or "—"
    css = ("body{font:14px/1.5 system-ui,sans-serif;max-width:1100px;margin:24px auto;padding:0 16px;color:#111}h1{color:#1F3864}h2{border-bottom:2px solid #B8860B;padding-bottom:2px}"
           "table{border-collapse:collapse;width:100%;margin-bottom:12px;font-size:12px}th,td{border:1px solid #ccc;padding:4px 6px;text-align:start}th{background:#1F3864;color:#fff}@media print{body{margin:0}}")
    return (f"<!doctype html><html><head><meta charset='utf-8'><title>{escape(rep['scope']['name'])} {escape(rep['period']['label'])}</title><style>{css}</style></head><body>"
            f"<h1>{escape(rep['scope']['name'])}</h1><p>{escape(rep['period']['kind'].title())} report · {escape(rep['period']['label'])} ({rep['period']['start']} → {rep['period']['end']}) · generated {rep['generated']}</p>"
            f"<p>Hours approved: <b>{t['hours']}</b> · Cost: <b>{escape(cost)}</b> · Milestones achieved: <b>{t['milestones_achieved']}</b>, missed: <b>{t['milestones_missed']}</b> · "
            f"Red {t['rag_counts']['RED']}, Amber {t['rag_counts']['AMBER']}, Green {t['rag_counts']['GREEN']}</p>"
            f"<table><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table></body></html>")


@router.get("/reports/period")
def period_report(scope: str = "portfolio", id: int | None = None, period: str = "month", anchor: date | None = None, format: str = "json",
                  db=Depends(get_db), user: User = Depends(current_user)):
    rep = build_report(db, user, scope, id, period, anchor or date.today())
    base = f"{scope}-{rep['period']['label'].replace(' ', '-')}"
    if format == "json":
        return rep
    if format == "html":
        return HTMLResponse(_html(rep))
    if format == "csv":
        return csv_response(f"{base}.csv", HEAD, _table_rows(rep))
    if format == "xlsx":
        data = build_xlsx([("Summary", HEAD, _table_rows(rep)), *_extra_sheets(db, rep)])
        return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f'attachment; filename="{base}.xlsx"', "X-Content-Type-Options": "nosniff"})
    raise HTTPException(422, "format must be json, html, csv or xlsx")


@router.get("/reports/period/xlsx-b64")
def period_xlsx_b64(scope: str = "portfolio", id: int | None = None, period: str = "month", anchor: date | None = None, db=Depends(get_db), user: User = Depends(current_user)):
    """Same workbook as base64 JSON, so the browser demo (text-only transport) can save it too."""
    import base64
    rep = build_report(db, user, scope, id, period, anchor or date.today())
    data = build_xlsx([("Summary", HEAD, _table_rows(rep)), *_extra_sheets(db, rep)])
    return {"filename": f"{scope}-{rep['period']['label'].replace(' ', '-')}.xlsx", "content_b64": base64.b64encode(data).decode()}
