# PROPERM — Smart PMO Performance Management System (MVP backend)

Implements the Phase 1 slice of `PROPERM_Workflow_V1` (no AI yet): Python 3.11+, FastAPI, SQLAlchemy 2 (SQLite for dev, Postgres-ready).

## Run
    pip install -r requirements.txt
    export PROPERM_SECRET="<long random string>"            # required in any real deployment
    export PROPERM_ADMIN_PASSWORD="<min 8 chars>"           # optional PROPERM_ADMIN_ID (default: admin)
    python -m app.seed                                       # creates the first ADMIN
    uvicorn app.main:app_from_env --factory --reload         # API docs at /docs
    pytest -q

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
| Non-labor cost ledger (committed / invoiced / paid; second approval above a threshold) | 2.7 | labor cost is computed from approved hours x staff cost rate |
| Planned allocation per staff per week, over-allocation warning, resource load view | 2.1b | |
| Risk register and issue log (risk "occurred" auto-creates a linked issue) | 1.6 | benefits register not built |
| Earned value: BAC, PV, EV, AC, CPI, SPI, EAC, ETC, VAC | 3.1 | `GET /projects/{id}/evm`, cost viewers only; PV is linear over the planned window |
| Weekly PM report with auto-populated snapshot (needs the week's progress update first) | 3.2 | EVM inside the snapshot is hidden from non-cost viewers |

## Not built yet (next slices)
Versioned rate card (a single cost rate per user is used for now), benefits register, closure checklist beyond the pending-timesheet check (1.5), dashboards, portfolio roll-ups and alerts (Section 3), all AI features (1.2, 3.3), notification dispatcher (outbox rows are written but nothing consumes them), work calendars / holidays (4.6), a web UI, Postgres row-level security (access control is enforced in the API layer today).

## Assumptions to confirm (see Section 8 of the flow chart)
- Work week starts Sunday (`WEEK_STARTS_ON_SUNDAY` in `app/config.py`); capacity is a flat `capacity_hours_week` per user until the calendar service exists.
- Default per-staff activity cap is the activity's planned hours; override per staff via `PUT /projects/{id}/activities/{aid}/limits`.
- Overtime: above capacity up to 125% needs a reason and acknowledgment (R1 = WARN); above 125% is blocked. Both are configurable.
- Single organization (no tenant_id yet).

## Schema changes
Tables are created with `create_all`; there are no migrations yet. If you created a dev database from the first commit, delete `properm.db` (the `activities` table gained `baseline_cost`). Add Alembic before any real data exists.
