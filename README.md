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
Server messages (rule explanations) are shown in English even in Arabic mode. Not yet in the UI: a program/portfolio grouping, notifications.

### Demo data
    PROPERM_DEMO=1 PROPERM_DEMO_PASSWORD="<pw>" python -m app.demo      # empty database only
Creates users admin, pm1, pmo1, dm1, pg1, s1, s2, s3 and a few projects in different health states.

Set `PROPERM_DEMO_LOGIN=1` to show one-click role buttons on the login page (no password needed). **Demo databases only: never enable it on a deployment with real data.**

### Tests
`python -m pytest` runs the backend suite. `bash tests/ui/run.sh` runs the browser test against a freshly seeded demo server (needs `npm i playwright` and Chrome; set `PLAYWRIGHT_PATH` / `CHROME_PATH` if they are installed elsewhere).

### Build progress timeline
The login page shows milestones with green (done), amber (in progress) and red (not started) lights, read from `app/static/milestones.json`. Change a sub-step's `s` to `done`, `progress` or `todo` and bump `updated`; the percentage counts steps equally, not effort.

### Netlify only (no server)
`netlify.toml` publishes `app/static`; the real Python backend then runs inside the visitor's browser (Pyodide, in a Web Worker) with an in-memory database seeded with demo data and one-click role buttons. First load takes a few seconds; data resets on reload. Demo only. `python3 scripts/build_demo.py` rebuilds `app/static/demo/pyapp.zip` from `app/` and `vendor/` (Netlify runs it; the committed copy is the fallback). The Pyodide runtime in `app/static/pyodide/` is 0.27.7 (Python 3.12); `vendor/` pins FastAPI 0.115 and Starlette 0.46 to match its Pydantic 2.10.

### Deploy with a server (Render, optional)
`render.yaml` and `Dockerfile` deploy the whole app (API + UI) as one Render service with demo data and quick-login. For a UI on Netlify: publish directory `app/static`, no build command, then set `window.PROPERM_API` in `app/static/config.js` to the Render address and set `PROPERM_CORS_ORIGINS` on Render to the Netlify address. Demo settings use a throwaway SQLite file; use Postgres for real data.

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
| Risk register and issue log (risk "occurred" auto-creates a linked issue) | 1.6 | benefits register: see below |
| Earned value: BAC, PV, EV, AC, CPI, SPI, EAC, ETC, VAC | 3.1 | `GET /projects/{id}/evm`, cost viewers only. PV is phased per activity from each activity's own planned dates; an activity without dates falls back to the project window and is listed in `warnings` |
| Effective-dated rate card (`/admin/rates`), append-only; labor cost priced at the rate in effect on each entry date; rates snapshotted at baseline lock | 2.1.5, 2.7.3 | a rate change never reprices past cost |
| Rule-based alerts: CPI/SPI thresholds, cost over baseline, overdue activities (warning beyond tolerance, critical beyond 3x), risk score, critical or overdue issues, stale progress. Deduplicated, with a cooldown after dismissal; thresholds editable via `/admin/settings/{key}` | 3.3 | `POST /projects/{id}/alerts/evaluate`, `POST /alerts/evaluate` (all projects; call from cron, no scheduler yet) |
| Triage loop: acknowledge, assign (owner + due date), escalate, dismiss (reason), resolve, verify / reject; full action history; assignee cannot verify own closure; closure is refused while the condition still holds | 3.5 | |
| Dashboards: project health (RAG, reasons, progress, hours, overdue, risks, issues, EVM) and portfolio (RAG counts, per-project CPI/SPI, open alerts, filters, top risks) | 3.4 | RAG: RED = active critical alert, AMBER = active warning, GREEN, GREY = not in delivery |
| Weekly PM report with auto-populated snapshot (needs the week's progress update first) | 3.2 | EVM inside the snapshot is hidden from non-cost viewers |

## Governance, notifications, exports and AI (added 2026-11-23)
| Area | Notes |
|---|---|
| Closure checklist | Opens when a project moves to `closing`. 8 items: 2 checked by the system (all timesheets approved, no open issues), 6 ticked by the manager. Archiving is refused (409) until every item is satisfied. `GET/PUT /projects/{id}/closure` |
| Benefits register | Baseline, target, actual, owner, status; realisation % = (actual - baseline) / (target - baseline), capped 0-150. `/projects/{id}/benefits` |
| Programs | Group projects (`/programs`, `PUT /projects/{id}/program`); roll-up dashboard with RAG counts, benefits and summed EVM (only when all projects share one currency). PMO/ADMIN manage; executive roles read |
| Work calendar | Work week Sunday to Thursday (`WEEKEND_DAYS` in `app/config.py`). Public holidays (`/calendar/holidays`, PMO/ADMIN) reduce that week's capacity by one day each. New rule **R10** (default FLAG) marks entries on weekends/holidays |
| Notifications | Outbox events become in-app notifications (`app/notify.py`) after every successful write; bell in the header. Optional e-mail: set `PROPERM_SMTP_HOST`, `PROPERM_SMTP_PORT`, `PROPERM_SMTP_USER`, `PROPERM_SMTP_PASSWORD`, `PROPERM_SMTP_FROM` and give users an e-mail in Admin. E-mail is best effort and has not been tried against a real mail server. Not available in the browser demo |
| Exports | CSV with UTF-8 BOM (Excel-safe Arabic, formula-injection neutralised): timesheets, alerts, portfolio, costs, benefits. Printable project report `GET /projects/{id}/report.html` (cost section only for cost viewers) |
| Scheduled reports | Weekly/monthly portfolio or project reports delivered as notifications. `POST /reports/run-due` (PMO/ADMIN) sends what is due; call it from a cron (for example a GitHub Actions schedule with an admin token). Nothing runs it automatically |
| AI layer | OpenAI-compatible client for a model hosted **inside the Kingdom** (`app/ai.py`). Set `PROPERM_AI_BASE_URL` (for example a Saudi-hosted vLLM serving Qwen), `PROPERM_AI_MODEL`, `PROPERM_AI_API_KEY`. The host must be localhost, a private address, or under `.sa` (`PROPERM_AI_ALLOWED_HOSTS` overrides); anything else is refused before any data is sent. With no URL set (and always in the browser demo) an **offline stub** answers and is labelled as such. Features: plan drafting from a brief, status narrative, alert suggested action. Output is schema-validated and stored as a draft; a person edits and applies or rejects it (plans) or copies it (text). Prompts contain only data the requesting user may see (no rates for non-cost viewers); user text is passed inside `<data>` delimiters; 30 requests per user per hour |

## Role gap build-out (added 2026-11-23, from `docs/ROLE_GAPS.md`)
| Area | Notes |
|---|---|
| Project intake | Client, sponsor, scope statement, project type; edit a project (`PATCH /projects/{id}`; after the baseline, dates, budget, currency and type are locked and change only through change control); PMO/ADMIN reassign the manager (`PUT /projects/{id}/manager`); documents (base64 upload, 3 MB, allow-listed extensions, always downloaded as an attachment); stakeholders (power/interest); edit/delete planning activities; remove an assignment. Admin can set a delegate per user |
| Plan depth | Milestones (upcoming/achieved/missed, slip days), KPIs (target vs actual, RAG), activity dependencies (finish-to-start, cycles refused, date-conflict flag), per-person activity hour limits (rule R2) with list and clear |
| Oversight | Audit log viewer with filters and paging (`GET /admin/audit`, PMO/ADMIN); period lock page with pending-entry counts; future-dated rates can be removed (rates already in effect never can) |
| Insight | Dependency-free SVG charts on the project dashboard: S-curve (PV/EV/AC), CPI/SPI trend, hours vs plan, risk heat map. Daily `snapshots` table (written when a trend is read, or `POST /dashboards/snapshots`) so history builds up. Executive summary (`/dashboards/executive`) and decision queue (`/dashboards/decisions`: change requests, cost approvals, critical alerts) |
| Daily work | `GET /me/todo`; approvals filter/bulk approve/decision history; staff can withdraw a pending or rejected entry (`DELETE /timesheets/{id}`, audited); remaining hours against the activity cap beside the hours box; this week by project |
| Period reports | `GET /reports/period?scope=project|program|portfolio&period=month|quarter|year&format=json|html|csv|xlsx`. Excel is written by `app/xlsx.py` (standard library only, also works in the browser demo). PDF = print the HTML report and choose Save as PDF. Cost columns appear only for cost viewers |
| Configuration | `ConfigItem` lists for non-project time codes (Leave is protected), risk categories, KPI templates and extra closure items; built-ins can be switched off but not deleted. Project types stay fixed because rules depend on them. AI administration: mode, host, in-Kingdom check, on/off switch, hourly limit, connection test, 30-day use, recent failures |

## Role completeness (added 2026-11-23, from `docs/ROLE_TASKS.md`)
| Area | Notes |
|---|---|
| Self-service | Profile page from the avatar: e-mail, delegate, password change (`POST /me/password`), notification choices (`UserPref`, honoured by `notify.py`). Role guide page lists each role's tasks with links |
| Staff | My projects with activity caps and hours used (`GET /me/projects`); copy last week (`POST /timesheets/copy-week`, skips duplicates and anything the rules reject) |
| PM | Edit risks and issues (title, category, owner, response, due date); timeline (Gantt) on the Plan tab with milestones and a today line |
| PMO / program / decision | Portfolio filters; program managers see and edit only their own programs and move projects in and out; program roll-up of risks and benefits; investment-versus-return table with drill-down; resource load shows the projects behind each person's hours |
| Admin | Job title and department on users; bulk CSV import with one-time generated passwords (`POST /admin/users/import`); read-only permission matrix |

## Governance (added 2026-11-23, from `docs/ROLE_GAPS_V2.md`)
| Area | Notes |
|---|---|
| Decisions | One set of outcomes everywhere: approve, approve with conditions, reject, defer, request more information. A rationale is required except for a plain approval; conditions for a conditional one. Every decision goes into `decision_records` (`GET /decision-log`) |
| Project intake | `POST /proposals` with business case and 1-5 scores; score out of 100 (fit and value 35% each, urgency 15%, low risk 15%); ranked list; approval creates the project in planning. Setting `intake_required=1` stops PMs creating projects directly |
| Stage gates | `POST /projects/{id}/gates` records automatic checks; DECISION_MAKER/PMO/ADMIN decide. With `stage_gates=1`, baseline lock (planning → execution) and execution → closing need an approved gate. A plain approval needs all checks met |
| PM control | Control tab: plan vs forecast per activity (`GET /projects/{id}/variance`; hours still needed from the weekly progress update, else trend, else plan; forecast end via `PUT .../activities/{aid}/forecast`; cost columns for cost viewers only). Action log (`/projects/{id}/actions`, owners see theirs in My to-do and can mark them done). Lessons learned per project and a library across projects (`GET /lessons?q=`) |
| Weekly cycle | Week strip on the timesheet and `POST /me/week/submit` (days without hours need a note; rejected entries must be fixed first). Team status `GET /timesheets/weeks`; reminders `POST /reminders/timesheets` (PMO/ADMIN, or a weekly cron). Leave `POST /leave`, decided by the line manager, their delegate, PMO or ADMIN; approved leave lowers capacity in resource load only (overtime rules still use full capacity, because leave days are logged with the Leave code) |
| Portfolio | `GET /portfolio/priorities` ranks running projects (scores via `PUT /portfolio/scores/{id}`, copied from the proposal on approval) and open proposals together. `GET /portfolio/capacity?group=department|grade|person&weeks=12`: planned hours against capacity after holidays and approved leave. `GET /portfolio/compliance`: per PM, missing weekly reports, stale progress, unreviewed risks (30 days), overdue actions, approvals waiting over 3 days, team weeks not submitted |
| Programs | Program page (`#/programs/{id}`): roadmap of projects with milestones and dependency lines (`GET /programs/{id}/roadmap`); cross-project dependencies on a milestone or the project finish, with conflict and late flags and a loop check (`/programs/{id}/dependencies`); program-level risks (`/programs/{id}/risks`, included in the roll-up). PMO, ADMIN or the program's own manager can change them |
| Security | Password rule (minimum length setting, at least one letter and one digit); lockout after `lockout_attempts` failures for `lockout_minutes` (HTTP 423), admin unlock; sign-in history (`GET /admin/logins`, `GET /me/logins`); session length `session_hours`; with `force_password_change=1`, passwords set by an admin must be changed before anything else works. Off-boarding: `GET/POST /admin/users/{id}/handover` moves projects, programs, open risks, issues, actions, alerts, line reports and delegations to another user and can deactivate the account |
| Project tools | Templates (`/templates`, PMO/ADMIN; save a project as a template; `POST /projects/{id}/apply-template/{tid}` while in tendering/planning). Resource requests (`/projects/{id}/resource-requests`; PMO assigns a person, which adds the assignment and plans the weekly hours). RACI matrix with checks (exactly one A, at least one R) and communication plan with due dates. Critical path (`GET /projects/{id}/critical-path`) shown on the Plan timeline |
| Insight | Search box in the top bar (`GET /search?q=`, respects project access). Steering-committee pack (`GET /reports/board-pack.html[?program_id=]`, one printable page per project plus a cover page). "Coming up" calendar on My to-do (`GET /me/calendar`). Planned hours ahead for staff (`GET /me/upcoming`). What-if (`POST /portfolio/what-if`: stop or delay a project; capacity before/after and dependent projects hit; nothing is saved) |
| Admin and program extras | Department list (Configuration; user departments must come from it once it has entries). Mail server settings with a test button (`/admin/mail`, password write-only; falls back to `PROPERM_SMTP_*`). Full JSON export (`GET /admin/export`, no password hashes). Personal start page (`PUT /me/home`). Program issues, funding envelope vs project budgets and forecast, and a benefits realisation plan by quarter on the program page |
| Change requests | Same outcomes; deferred or returned requests can be resubmitted (`POST /projects/{id}/changes/{cid}/resubmit`) |

## Assistant, home page and role audit (added 2026-11-23)
A gold button at the bottom corner opens the assistant (Arabic or English). It answers about your hours, to-do, approvals, alerts, risks, a project's status and how to do a task, using only what you may already see. `Ctrl+K` jumps to any page or project. Each role lands on **Home**. New timesheet rule R11 (daily hours). The full role-by-role audit is in `docs/ROLE_AUDIT.md` and runs as `tests/test_role_audit.py`.

## Project book to plan (added 2026-11-23, flow chart 1.2 and 1.3)
Open a project in tendering or planning, tab **Project book**: pick an uploaded file, upload one (PDF, DOCX, text, or a scan), or paste text. Arabic and English both work. PROPERM reads it (`app/docread.py`; scans need Tesseract `ara+eng` and poppler on the server), extracts phases, requirements with source page, deliverables, tasks with estimated hours, team roles, risks, compliance items and acceptance terms (`app/brief.py`, rules first; the Saudi-hosted model refines each phase when it is live). You review and edit, then **Apply**: requirements, deliverables (WBS), milestones, tasks, risks, compliance and assumptions are created, and each task is given to a person with the skill and free weekly hours, or left **unassigned** with a resource request. After the baseline, burn hours are watched by two alerts: `activity_burn_high` and `activity_hours_exceeded`. Hour estimates are a starting point. Tested on the real 45-page Arabic Taqeem book and by `tests/test_brief.py` (book to closure).

## Role gaps V3 (added 2026-11-23, from `docs/ROLE_GAPS_V3.md`)
| Area | Notes |
|---|---|
| Scope and acceptance | Charter per project (`/projects/{id}/charter`, approve or reopen by PMO/ADMIN/DECISION_MAKER), assumption log, WBS of deliverables and work packages with submit and accept (`/wbs`), requirements with traceability (verified needs a test reference), `GET /scope-summary`. Closure item "deliverables accepted" turns automatic once deliverables exist |
| Agile and hybrid | `/backlog`, `/sprints` (start, close with carry-over), board move by assignee or manager, `GET /agile-summary` (velocity, burndown, forecast). Predictive projects get 409; the Agile tab shows for adaptive and hybrid only |
| Strategy and compliance | Strategic objectives (`/objectives`, coverage view `/objectives/coverage`), links from projects and proposals. Compliance library and per-project register with evidence, `apply-framework`, overview |
| Procurement | Contracts (cost viewers only), payment milestones planned → achieved → invoiced → paid, vendor reviews, `GET /procurement/overview`; contracts with payments cannot be deleted |
| Skills and team | `/me/skills`, `/me/certs`, skills directory and development gaps (PMO), best matches for a resource request (`/resource-requests/{id}/matches`), team charter `/projects/{id}/team-norms` |
| Depth | Risk responses with residual score, opportunities, reserves with drawdown approved by PMO (`/reserves`), CV/SV/TCPI in EVM, quality log, document versions (`/documents/{id}/versions`), stakeholder engagement |
| Admin | `POST /admin/restore` (ADMIN, `confirm:"RESTORE"`, `mode` dry_run or replace; one transaction; the audit log is never touched; people already present keep their password, new ones get a temporary password shown once and must change it). Retention: `GET /admin/retention`, `POST /admin/retention/apply` removes old sign-in history and read notifications only; old closed projects are listed, never deleted. Two-factor (TOTP, authenticator app): `/me/2fa`, `/setup`, `/enable` (8 backup codes once), `/disable`, admin reset `POST /admin/users/{id}/2fa/reset`; sign-in takes an optional `otp` (401 `otp_required`); setting `require_2fa_privileged=1` makes ADMIN, PMO and DECISION_MAKER turn it on first. Single sign-on is not built (needs real hosting) |

## Not built yet (next slices)
Single sign-on (needs real hosting and an identity provider), saved filters, progress updates by staff, a rate card per role and project (rates are per grade only), forecasting models, PDF/DOCX parsing for the AI brief (paste text for now), a real mail-server test, a built-in scheduler for reports and alert evaluation (call the endpoints from a cron), Postgres with migrations and row-level security (access control is enforced in the API layer today), remaining UI polish (see Web UI).

## Assumptions to confirm (see Section 8 of the flow chart)
- Work week starts Sunday (`WEEK_STARTS_ON_SUNDAY` in `app/config.py`); capacity is a flat `capacity_hours_week` per user until the calendar service exists.
- Default per-staff activity cap is the activity's planned hours; override per staff via `PUT /projects/{id}/activities/{aid}/limits`.
- Overtime: above capacity up to 125% needs a reason and acknowledgment (R1 = WARN); above 125% is blocked. Both are configurable.
- Single organization (no tenant_id yet).

## Schema changes
Tables are created with `create_all`; there are no migrations yet. If you created a dev database from the first commit, delete `properm.db` (`activities` gained `baseline_cost`, `planned_start`, `planned_end`; `users.cost_rate_hour` was replaced by `rate_grade`). Add Alembic before any real data exists. The 2026-11-23 slice added tables (`programs`, `closure_items`, `benefits`, `holidays`, `notifications`, `report_schedules`, `ai_drafts`) and columns (`projects.program_id`, `users.email`); `create_all` adds new tables but not new columns, so delete an old dev database. The V3 build added tables for scope, agile, strategy, compliance, procurement, skills, reserves, quality, document versions, engagement and `two_factor` (new tables only). The role-gap build-out added tables `documents`, `stakeholders`, `milestones`, `project_kpis`, `activity_dependencies`, `snapshots`, `config_items` and columns `projects.client`, `projects.sponsor`, `projects.scope_statement`.
