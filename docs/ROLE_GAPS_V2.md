# PROPERM role review, round 2 (2026-11-23)

Benchmark: PMI PMBOK 7 and *Standard for Portfolio/Program Management*, AXELOS P3O/MoP, and common PMO practice in Saudi government entities.
Method: for each role, what a strong practitioner needs to do the job well, checked against the current UI (151 endpoints, 20 pages).

Priority: **P1** = the role cannot work properly without it · **P2** = expected by experienced users · **P3** = nice to have.
Status: ✅ have · 🟡 partly · ⬜ missing

---

## 1. Staff (team member)
Best practice: a full, accurate timesheet with little effort; knows what is coming next; time off is planned in advance.

| Need | Status | Gap | Pri |
|---|---|---|---|
| Log time, fix rejected entries, copy last week | ✅ | — | |
| Submit the **whole week** in one go and get a weekly status | ✅ | Week strip + Submit week (entries are still approved one by one) | P1 |
| **Reminders** for missing days and the weekly deadline | ✅ | To-do item; PMO sends reminders (or a cron calls `POST /reminders/timesheets`) | P1 |
| **Plan leave ahead** so managers see reduced capacity | ✅ | Leave page, line-manager approval, lowers capacity in resource load | P1 |
| See **upcoming work** (my planned hours for the next weeks) | ⬜ | "My projects" shows caps, not the forward plan | P2 |
| Update % complete on activities I own | 🟡 | Only the PM updates progress | P3 |

## 2. Project Manager
Best practice: plan against a baseline, forecast honestly, control change, keep a decision and action log, report on time, close with lessons learned.

| Need | Status | Gap | Pri |
|---|---|---|---|
| Plan, baseline, milestones, KPIs, risks, issues, changes, costs, benefits | ✅ | — | |
| **Baseline vs current** per activity (dates, hours, cost variance) | ✅ | Control tab | P1 |
| **Estimate to complete** per activity (PM's own forecast, not just formula) | ✅ | Progress tab hours + forecast end date | P1 |
| **Decision and action log** per project (who decided what, actions with owners and due dates) | ✅ | Decision log (Overview), action log (Control, feeds My to-do) | P1 |
| **Lessons learned register** (during and at closure, searchable by other PMs) | ✅ | Control tab + Lessons library | P1 |
| **Resource request** to PMO/line manager instead of assigning people directly | ⬜ | | P2 |
| **RACI** and **communication plan** (who is informed, how often) | ⬜ | | P2 |
| Critical path and dependency arrows on the timeline | ⬜ | Timeline has bars and milestones only | P2 |
| Start a project from a **template** (standard activities, KPIs, risks) | ⬜ | | P2 |

## 3. PMO
Best practice: run the governance cycle (stage gates, reporting calendar, compliance), standardise methods, plan capacity across the portfolio.

| Need | Status | Gap | Pri |
|---|---|---|---|
| Portfolio health, alerts, audit, period lock, reports, filters | ✅ | — | |
| **Stage gates**: entry criteria and a recorded approval to move tendering → planning → execution → closing | ✅ | Automatic checks, recorded decision; switch in Configuration | P1 |
| **Compliance view**: late weekly reports, missing timesheets, stale risks, overdue actions, per PM | ✅ | Portfolio page | P1 |
| **Capacity plan** for the next 8–12 weeks (demand vs supply by department/grade) | ✅ | Portfolio page, by department, grade or person | P1 |
| **Project templates / methodology library** maintained by PMO | ⬜ | | P2 |
| Reporting calendar (who must submit what, when) | 🟡 | Scheduled reports exist; no due-date calendar | P2 |

## 4. Program Manager
Best practice: manage the program as one unit: roadmap, inter-project dependencies, program-level risks and a benefits realisation plan.

| Need | Status | Gap | Pri |
|---|---|---|---|
| Own programs, add/remove projects, roll-up of risks and benefits | ✅ | — | |
| **Program roadmap** (all projects and key milestones on one timeline) | ✅ | Programs → Roadmap | P1 |
| **Inter-project dependencies** (project B waits for A's milestone) | ✅ | Conflicts flagged and drawn on the roadmap | P1 |
| **Program-level risks and issues** (owned by the program, not a project) | 🟡 | Program risks done; program issues not yet | P2 |
| **Benefits realisation plan** (owner, measure, schedule, handover to operations) | 🟡 | Benefits exist per project; no program plan view | P2 |
| Program budget envelope vs sum of project budgets | 🟡 | EVM totals only | P3 |

## 5. Decision Maker (sponsor / steering committee)
Best practice: decides on investment (what to start, stop, continue), not on daily detail; needs short, comparable evidence and a record of decisions.

| Need | Status | Gap | Pri |
|---|---|---|---|
| Executive dashboard, decisions queue, investment vs return, drill-down | ✅ | — | |
| **Project intake approval** (business case → approve/reject before a PM can start) | ✅ | Proposals page; switch in Configuration | P1 |
| **Prioritisation / scoring** (strategic fit, value, risk, cost) to rank the portfolio | ✅ | Projects and proposals on one ranked list (Portfolio page) | P1 |
| Decision options beyond approve/reject: **defer, request more information, approve with conditions**, with rationale kept | ✅ | Proposals, stage gates and change requests | P1 |
| **Steering-committee pack**: one-page per project, exportable | 🟡 | Period reports exist; no board pack format | P2 |
| What-if (stop or delay a project, effect on budget and capacity) | ⬜ | | P3 |

## 6. Administrator
Best practice: secure access, clean organisation data, safe off-boarding, recoverable data.

| Need | Status | Gap | Pri |
|---|---|---|---|
| Users, roles, rates, lists, AI settings, bulk import, permission matrix | ✅ | — | |
| **Account security**: password policy, lockout after failed sign-ins, force change at first sign-in, session timeout | ✅ | Settings + Admin → Security | P1 |
| **Sign-in history** (who, when, failures) | ✅ | Admin → Security; own history on My profile | P1 |
| **Off-boarding**: deactivate a user and reassign their projects, risks, actions, approvals | ✅ | Admin → Hand over | P1 |
| **Organisation structure**: departments as a maintained list/hierarchy | 🟡 | Free text | P2 |
| Mail server settings and test from the UI | ⬜ | Environment variables only | P2 |
| Backup / full data export | ⬜ | | P2 |
| Single sign-on (Active Directory / Nafath) and MFA | ⬜ | Needs real hosting first | P3 |

## 7. Everyone
| Need | Status | Pri |
|---|---|---|
| **Global search** (projects, people, risks, documents) | ⬜ | P2 |
| Saved filters / personal home page | ⬜ | P3 |
| Arabic/English, role guide, profile | ✅ | |

---

## Recommended build order
1. ✅ **Governance core** (done 2026-11-23) — project intake approval, stage gates with criteria, decision options with rationale (Decision Maker + PMO, P1).
2. ✅ **PM control** (done 2026-11-23) — baseline vs current variance, estimate to complete, decision & action log, lessons learned register.
3. ✅ **Staff weekly cycle** (done 2026-11-23) — weekly submission, reminders, planned leave feeding capacity.
4. ✅ **Portfolio planning** (done 2026-11-23) — 12-week capacity plan, compliance view, prioritisation scoring.
5. ✅ **Program** (done 2026-11-23) — roadmap, inter-project dependencies, program-level risks.
6. ✅ **Admin security** (done 2026-11-23) — password policy, lockout, sign-in history, off-boarding with reassignment.
7. P2/P3 items: templates, RACI/communications, resource requests, critical path, search, board pack, mail settings, backup.
