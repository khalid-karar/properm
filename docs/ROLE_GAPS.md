# PROPERM role gap analysis (2026-11-23)

Method: logged into the running app as each of the five demo roles (Staff, PM, PMO, Decision Maker, Admin), dumped every page and project tab, and compared with (a) the master flow chart, (b) what the API already does, (c) what each role needs to do their job.
Priority: **P1** the role cannot finish a core job. **P2** it works but is painful or incomplete. **P3** nice to have.
Tags: [UI] backend exists, screen missing. [API+UI] both missing. [AI] needs the model.

## Staff
Can: enter, edit and resubmit timesheet entries (rules, overtime reason), see weekly utilisation, see projects and alerts, export own timesheet.
| # | Gap | Pri |
|---|---|---|
| S1 | Cannot withdraw or delete a submitted entry that is still pending [API+UI] | P1 |
| S2 | Weekly view has no per-project breakdown or list of rule flags (flow chart 2.5) [UI] | P2 |
| S3 | No "copy last week" or favourites, so entering 5 days across 3 projects is slow | P2 |
| S4 | Nothing says WHY an activity is missing from the dropdown (not assigned, wrong project state, cap reached); remaining hours per activity (R2 cap) not shown | P2 |
| S5 | "Approvals" appears in the menu for staff but is always empty | P3 |
| S6 | No view of own assigned projects with my hours vs my cap | P3 |
| S7 | No notification preferences (which events, e-mail on/off) | P3 |

## Project manager
Can: create a project, add activities and lock the baseline, assign people, set progress, costs, risks, issues, change requests, allocations, benefits, weekly report, approve timesheets, use AI drafts.
| # | Gap | Pri |
|---|---|---|
| P1 | Project intake is thin: no client, sponsor, stakeholders, contract and charter upload, scope statement, project type [API+UI] | P1 |
| P2 | Cannot edit a project (name, dates, budget, PM) after creation; no endpoint [API+UI] | P1 |
| P3 | Plan has activities only: no milestones, KPIs, dependencies/WBS, or the other plan domains (quality, communication, stakeholder, procurement). Flow chart 1.3 expects these [API+UI] | P1 |
| P4 | Per-activity staff hour limits (rule R2) can be set by API but there is no screen, so R2 never fires in real use [UI] | P1 |
| P5 | Activities cannot be edited or deleted in planning; assignments cannot be removed [API+UI] | P1 |
| P6 | AI plan review is a flat table; flow chart wants side-by-side AI draft vs editable form per domain, with tracked diffs and "reject and regenerate with feedback" [UI+AI] | P2 |
| P7 | Weekly report is a blank form; flow chart wants it auto-filled from progress, KPIs, risks and issues [API+UI] | P2 |
| P8 | Risk register lacks category, response plan, owner, due; risks cannot be edited, only status changed [API+UI] | P2 |
| P9 | Project dashboard has no charts: no S-curve (PV/EV/AC over time), milestone tracker, risk heatmap, actual vs plan hours [UI] | P2 |
| P10 | Approval queue: no bulk approve, no filter by project or person, no history of decisions | P2 |
| P11 | Change control: approved change does not guide the baseline revision (re-lock, re-confirm affected sections) | P2 |
| P12 | No Gantt or timeline of activities; no Kanban for issues | P3 |
| P13 | Cannot delegate approvals from the UI (delegate field exists in the database only) [UI] | P2 |
| P14 | No document attachments anywhere (issues, changes, costs, closure items) | P2 |

## PMO
Can: everything a PM can on all projects, portfolio dashboard, programs, holidays in Admin, closure gate, run scheduled reports.
| # | Gap | Pri |
|---|---|---|
| O1 | Cannot reassign a project to another PM or add a delegate [API+UI] | P1 |
| O2 | Period lock (freeze a closed month so entries cannot change) exists in the API only [UI] | P1 |
| O3 | No audit log viewer; the log is written but nobody can read it [API+UI] | P1 |
| O4 | Portfolio dashboard cannot filter by period, owner or program, and has no drill-down portfolio > program > project > activity [UI] | P2 |
| O5 | No resource conflict view across projects (who is over-allocated by project and week, with a way to fix it) | P2 |
| O6 | No governance calendar or template library (standard activities, risk lists, closure items) the PMO can maintain | P2 |
| O7 | Monthly, quarterly and annual reports (per project, program, portfolio) do not exist; only weekly reports and an on-demand narrative [API+UI+AI] | P2 |
| O8 | Alert evaluation runs only when someone presses a button or a cron calls it | P2 |
| O9 | Exports are CSV and printable HTML only; flow chart asks for PDF and Excel | P3 |
| O10 | Program page has no "add project", no benefits list, no program-level risks | P3 |

## Decision maker (executive)
Can: read the portfolio dashboard, programs, project pages, alerts (acknowledge, assign, escalate, dismiss).
| # | Gap | Pri |
|---|---|---|
| D1 | A one-screen executive summary is missing: top 5 risks, top deviations, projects needing a decision, benefits at risk, in plain language [UI] | P1 |
| D2 | No trends. Everything is a snapshot; no RAG or CPI/SPI history per project over weeks [API+UI] | P1 |
| D3 | A decision queue is missing: change requests above a threshold, escalated alerts, cost approvals in one place. Escalated alerts have no named recipient [API+UI] | P1 |
| D4 | No portfolio view by strategic objective, investment versus return (budget vs benefits) [API+UI] | P2 |
| D5 | No drill-down to activity level; the dashboard links to project pages built for PMs | P2 |
| D6 | No scheduled executive pack (PDF) by e-mail; reports arrive as in-app notifications | P2 |
| D7 | Forecasts (probability of schedule or cost overrun) not built [AI/ML] | P2 |
| D8 | Cannot comment on or annotate an alert or report | P3 |

## Program manager (role exists, not in the demo)
| # | Gap | Pri |
|---|---|---|
| G1 | Cannot manage programs or add projects to a program (PMO/ADMIN only); sees all programs, not "my programs" [API+UI] | P1 |
| G2 | No cross-project dependencies or resource conflicts inside the program [API+UI] | P2 |
| G3 | Program risks and benefits are not tracked at program level | P2 |

## Admin
Can: users (create, edit, deactivate, reset password, CCB flag, grade, capacity, line manager), rate card, holidays, rule severities, settings.
| # | Gap | Pri |
|---|---|---|
| A1 | Rate card cannot be edited or end-dated; no per-role or per-project rates [API+UI] | P1 |
| A2 | No audit log viewer and no export of it (see O3) | P1 |
| A3 | User form lacks job title, department, skills, e-mail on create, delegate; no bulk import from CSV [UI] | P2 |
| A4 | No AI administration: model health, failed requests, prompt versions, usage per user [API+UI] | P2 |
| A5 | No role and permission matrix screen; permissions are in code | P3 |
| A6 | No configurable lists (project types, risk categories, KPI library, closure items, report templates) [API+UI] | P2 |
| A7 | No backup, retention or data-export controls | P2 |
| A8 | No login security screen (failed logins, lockout, session list, SSO) | P2 |

## Cross-role
| # | Gap | Pri |
|---|---|---|
| X1 | No global search or "my to-do" page that pulls approvals, assigned alert actions and overdue items together | P1 |
| X2 | No charts anywhere in the product (progress, EVM, load, risk) | P1 |
| X3 | No in-app help or empty-state guidance for first-time users | P2 |
| X4 | Notification preferences and e-mail digest | P2 |
| X5 | Accessibility and Arabic wording review not done | P2 |

## Suggested build order
1. Project intake and edit (P1, P2, P5, O1) so a PM can really create and run a project.
2. Plan depth: milestones, KPIs, activity limits UI (P3, P4).
3. Audit log, period lock, rate card editing (O2, O3, A1).
4. Charts and trends, then the executive summary and decision queue (X2, D1-D3, P9).
5. My to-do page and approvals improvements (X1, P10, S1).
6. Monthly/quarterly reports and PDF/Excel export (O7, O9).
7. Admin configuration and AI administration (A4, A6).
