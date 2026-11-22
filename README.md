# PROPERM — Smart PMO Performance Management System (MVP)

Implements the Phase 1 slice of `PROPERM_Workflow_V1` (no AI yet): Python 3.11+, FastAPI, SQLAlchemy 2 (SQLite for dev, Postgres-ready).

## Run
    pip install -r requirements.txt
    export PROPERM_SECRET="<long random string>"            # required in any real deployment
    export PROPERM_ADMIN_PASSWORD="<min 8 chars>"           # optional PROPERM_ADMIN_ID (default: admin)
    python -m app.seed                                       # creates the first ADMIN
    uvicorn app.main:app_from_env --factory --reload         # API docs at /docs
    pytest -q

## Web UI
Served by the same app at `/ui` (`/` redirects there). Vanilla ES modules, no build step. English/Arabic with RTL, role-based navigation. Screens: login, timesheet (overtime/warning acknowledgment flow), approvals queue (timesheets and change requests), projects (overview, progress, risks and issues, cost and EVM, change control, allocations, weekly reports), resource load, portfolio and project dashboards, alert triage, admin (users incl. CCB flag, rules, settings, rate card).
Server messages (rule explanations) are shown in English even in Arabic mode. Not yet in the UI: editing or deactivating users, a program/portfolio grouping, notifications.

### Demo data
    PROPERM_DEMO=1 PROPERM_DEMO_PASSWORD="<pw>" python -m app.demo      # empty database only
Creates users admin, pm1, pmo1, dm1, s1, s2, s3 and a few projects in different health states.

Set `PROPERM_DEMO_LOGIN=1` to show one-click role buttons on the login page (no password needed). **Demo databases only: never enable it on a deployment with real data.**

`DATABASE_URL` selects the database (default `sqlite:///./properm.db`).

## What is built (flow chart section)
| Area | Section | Notes |
|---|---|---|
| Auth, JWT, roles (PM, STAFF, PMO, PROGRAM_MANAGER, DECISION_MAKER, ADMIN) + CCB flag | 0 | bcrypt passwords, 8h tokens |
| Project registration, phase activities, assignment | 1.1 | tendering/planning start; PRE-BID / PLAN-GEN / CLOSE-GEN auto-created |
| Lifecycle state machine with role-gated transitions | 1.0 | planning to execution only via baseline lock |
| Manual plan entry + baseline lock (v1) | 1.3 | activities, planned hours, per-staff caps |
| Change control (request, CCB decision, baseline version bump, activity added only via approved change) | 1.4 | |
| Staff master (capacity, line manager, delegate, cost rate restricted to ADMIN/PMO) | 2.1 | |
| Timesheet entry with rule engine R1-R9, configurable severity, overtime flow | 2.2, 2.3 | pure functions in `app/rules.py` |
| Approval (PM / delegate / line manager for non-project), approve / reject / adjust (reduce only) | 2.4 | no self-approval |
| Period lock by PMO (refused while entries pending) | 2.4, R8 | |
| Staff self-view utilization | 2.5 | own data only |
| Append-only audit log, transactional outbox, anomaly.flag | 4.2, 6 | |
| Admin: rule severities and thresholds | 4.5 (minimum) | |
| Weekly progress per activity (percent complete, ETC, reason when it decreases, stale flag) | 2.6 | |
| Non-labor cost ledger (committed / invoiced / paid; second approval above a threshold) | 2.7 | labor cost is computed from approved hours x the grade rate in effect on the entry date |
| Planned allocation per staff per week, over-allocation warning, resource load view | 2.1b | |
| Risk register and issue log (risk "occurred" auto-creates a linked issue) | 1.6 | benefits register not built |
| Earned value: BAC, PV, EV, AC, CPI, SPI, EAC, ETC, VAC | 3.1 | `GET /projects/{id}/evm`, cost viewers only. PV is phased per activity from each activity's own planned dates; an activity without dates falls back to the project window and is listed in `warnings` |
| Effective-dated rate card (`/admin/rates`), append-only; labor cost priced at the rate in effect on each entry date; rates snapshotted at baseline lock | 2.1.5, 2.7.3 | a rate change never reprices past cost |
| Rule-based alerts: CPI/SPI thresholds, cost over baseline, overdue activities (warning beyond tolerance, critical beyond 3x), risk score, critical or overdue issues, stale progress. Deduplicated, with a cooldown after dismissal; thresholds editable via `/admin/settings/{key}` | 3.3 | `POST /projects/{id}/alerts/evaluate`, `POST /alerts/evaluate` (all projects; call from cron, no scheduler yet) |
| Triage loop: acknowledge, assign (owner + due date), escalate, dismiss (reason), resolve, verify / reject; full action history; assignee cannot verify own closure; closure is refused while the condition still holds | 3.5 | |
| Dashboards: project health (RAG, reasons, progress, hours, overdue, risks, issues, EVM) and portfolio (RAG counts, per-project CPI/SPI, open alerts, filters, top risks) | 3.4 | RAG: RED = active critical alert, AMBER = active warning, GREEN, GREY = not in delivery |
| Weekly PM report with auto-populated snapshot (needs the week's progress update first) | 3.2 | EVM inside the snapshot is hidden from non-cost viewers |

## Not built yet (next slices)
Benefits register, a rate card per role and project (rates are per grade only), closure checklist beyond the pending-timesheet check (1.5), program-level roll-ups (there is no program or portfolio grouping yet; the portfolio view covers all projects), AI-generated reports and ML forecasts (3.3), export and scheduled delivery (3.4.5), notification delivery, all AI features (1.2, 3.3), notification dispatcher (outbox rows are written but nothing consumes them), work calendars / holidays (4.6), remaining UI screens (see Web UI), Postgres row-level security (access control is enforced in the API layer today).

## Assumptions to confirm (see Section 8 of the flow chart)
- Work week starts Sunday (`WEEK_STARTS_ON_SUNDAY` in `app/config.py`); capacity is a flat `capacity_hours_week` per user until the calendar service exists.
- Default per-staff activity cap is the activity's planned hours; override per staff via `PUT /projects/{id}/activities/{aid}/limits`.
- Overtime: above capacity up to 125% needs a reason and acknowledgment (R1 = WARN); above 125% is blocked. Both are configurable.
- Single organization (no tenant_id yet).

## Schema changes
Tables are created with `create_all`; there are no migrations yet. If you created a dev database from the first commit, delete `properm.db` (`activities` gained `baseline_cost`, `planned_start`, `planned_end`; `users.cost_rate_hour` was replaced by `rate_grade`). Add Alembic before any real data exists.
