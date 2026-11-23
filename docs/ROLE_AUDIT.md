# PROPERM role audit, round 4 (2026-11-23)

Method: `tests/test_role_audit.py` runs 122 concrete tasks, one by one, as each of the six roles against the flow chart (`PROPERM_Workflow_V0`) and PMO practice. It also checks what each role must NOT be able to do (staff cannot see costs, a requester cannot approve their own change, a PM cannot see another PM's project, and so on). The table below is the last run; every row passes.

## Gaps found and patched in this round
| Gap | Role | Fix |
|---|---|---|
| No AI assistant | all | `POST /ai/ask` and a floating widget. It answers only from data the asker may already see (flow chart 4.1), in Arabic or English, and obeys the admin AI switch and hourly limit. Rules answer without a model; the Saudi-hosted model only rephrases the answer when it is live. |
| No daily-hours rule: one entry of 24 h on one day was accepted | staff, PM | Rule R11: warn above `daily_soft_hours` (10), block above `daily_max_hours` (14). Both editable in Config. |
| 20+ menu items in one list; no start page | all | Grouped menu (My work, Projects, Insight, Governance, Administration), a Home page per role with what needs attention and the next actions, Ctrl+K quick jump. |

## Not gaps (checked, already built)
Adjust hours with a reason, alert acknowledge/assign/escalate/dismiss/resolve/verify with the assignee barred from verifying their own closure, per-staff activity caps, change control with a different decider, baseline revision, period lock, append-only audit, 2FA, backup restore, retention.

## Still open
- Live Saudi-hosted model not yet connected, so the assistant and the book refinement run in rule mode.
- Scanned books need Tesseract on the server.
- The AI plan covers requirements, deliverables, milestones, tasks, staffing, risks and compliance from the book. Cost plan, quality plan, communication plan and procurement plan are still entered by hand (flow chart 1.2 lists ten domains).

## Results
| Role | Task | Result | Note |
|---|---|---|---|
| STAFF | Sees only assigned projects | PASS |  |
| STAFF | Cannot open a project they are not on | PASS |  |
| STAFF | R: log hours on an assigned activity | PASS |  |
| STAFF | R7: duplicate entry rejected | PASS |  |
| STAFF | R11: more than 14 hours in one day rejected | PASS |  |
| STAFF | R3: not assigned to project rejected | PASS |  |
| STAFF | R6: activity not in baseline rejected | PASS |  |
| STAFF | Edit own pending entry | PASS |  |
| STAFF | Cannot approve own entry | PASS |  |
| STAFF | Queue is empty for staff | PASS |  |
| STAFF | Week view and utilisation | PASS |  |
| STAFF | Timesheet hints (remaining capacity / caps) | PASS |  |
| STAFF | Copy last week | PASS |  |
| STAFF | Submit my week (blocked until every working day is covered) | PASS |  |
| STAFF | To-do list | PASS |  |
| STAFF | Request leave | PASS |  |
| STAFF | Add own skill | PASS |  |
| STAFF | Profile, prefs, password | PASS |  |
| STAFF | Notifications list and count | PASS |  |
| STAFF | Cannot create a project | PASS |  |
| STAFF | Cannot see costs or rates | PASS |  |
| STAFF | Cannot see portfolio or executive | PASS |  |
| STAFF | Cannot see other staff timesheets | PASS |  |
| STAFF | Cannot read audit log | PASS |  |
| STAFF | Sees own task progress on the project | PASS |  |
| STAFF | Search is limited to what they can see | PASS |  |
| PM | Create a project | PASS |  |
| PM | Duplicate project number rejected | PASS |  |
| PM | Upload charter/contract document | PASS |  |
| PM | Per-activity max hours per staff | PASS |  |
| PM | R2: per-staff cap blocks logging beyond it | PASS |  |
| PM | Timesheet queue shows the entry | PASS |  |
| PM | Adjust hours needs reason | PASS |  |
| PM | Adjust hours with reason | PASS |  |
| PM | Reject needs a reason | PASS |  |
| PM | Weekly report is auto-populated | PASS |  |
| PM | Submit weekly report | PASS |  |
| PM | Risk with response strategy | PASS |  |
| PM | Issue log | PASS |  |
| PM | Stakeholder register | PASS |  |
| PM | Communication plan | PASS |  |
| PM | Quality plan item | PASS |  |
| PM | Contract / vendor register | PASS |  |
| PM | Payment milestones | PASS |  |
| PM | KPI definition | PASS |  |
| PM | Milestone | PASS |  |
| PM | Dependencies and critical path | PASS |  |
| PM | Progress update | PASS |  |
| PM | EVM numbers | PASS |  |
| PM | Change request needs impact analysis | PASS |  |
| PM | Change request with impact | PASS |  |
| PM | Requester cannot approve own change | PASS |  |
| PM | CCB approves, baseline revision increments | PASS |  |
| PM | Resource request | PASS |  |
| PM | Resource load view | PASS |  |
| PM | Lessons learned | PASS |  |
| PM | Project report (print) | PASS |  |
| PM | Cost entry and export | PASS |  |
| PM | Cannot touch users, rates or settings | PASS |  |
| PM | Cannot see other PM's project | PASS |  |
| PM | Cannot see cost rates of staff | PASS |  |
| PM | Alerts for own projects | PASS |  |
| PM | AI plan draft from brief text | PASS |  |
| PMO | Sees every project | PASS |  |
| PMO | Executive and portfolio dashboards | PASS |  |
| PMO | Evaluate alerts and triage | PASS |  |
| PMO | Alert workflow: ack, assign, resolve, verify | PASS |  |
| PMO | Audit trail with filters | PASS |  |
| PMO | Lock a period | PASS |  |
| PMO | Scheduled report | PASS |  |
| PMO | Period report data | PASS |  |
| PMO | Board pack | PASS |  |
| PMO | Cross-project resource conflicts | PASS |  |
| PMO | Priority scoring and what-if | PASS |  |
| PMO | Stage gates | PASS |  |
| PMO | Project templates | PASS |  |
| PMO | Compliance and procurement overview | PASS |  |
| PMO | Reassign project manager | PASS |  |
| PMO | Resource request decision queue | PASS |  |
| PMO | Skill matches for a request | PASS |  |
| PMO | Reminders to staff for missing timesheets | PASS |  |
| PMO | Cannot administer users | PASS |  |
| PMO | Lessons library across projects | PASS |  |
| PROGRAM_MANAGER | Program exists (created by PMO) | PASS |  |
| PROGRAM_MANAGER | Programs list | PASS |  |
| PROGRAM_MANAGER | Executive dashboard | PASS |  |
| PROGRAM_MANAGER | Cannot approve timesheets | PASS |  |
| PROGRAM_MANAGER | Cannot edit a project's activities | PASS |  |
| PROGRAM_MANAGER | Program roll-up, risks, benefits | PASS |  |
| DECISION_MAKER | Executive dashboard | PASS |  |
| DECISION_MAKER | Decision queue | PASS |  |
| DECISION_MAKER | Investment vs return | PASS |  |
| DECISION_MAKER | Top risks | PASS |  |
| DECISION_MAKER | Decision log | PASS |  |
| DECISION_MAKER | Proposals list | PASS |  |
| DECISION_MAKER | Read-only on timesheets | PASS |  |
| DECISION_MAKER | Cannot create a project | PASS |  |
| DECISION_MAKER | Drill into one project | PASS |  |
| DECISION_MAKER | Alert triage (acknowledge/escalate) | PASS |  |
| DECISION_MAKER | Board pack | PASS |  |
| ADMIN | Create and edit users | PASS |  |
| ADMIN | Duplicate staff id rejected | PASS |  |
| ADMIN | Weak password rejected | PASS |  |
| ADMIN | Rate grades | PASS |  |
| ADMIN | Rule engine configuration R1..R7 | PASS |  |
| ADMIN | Configurable lists | PASS |  |
| ADMIN | AI status and controls | PASS |  |
| ADMIN | Permission matrix | PASS |  |
| ADMIN | Login history | PASS |  |
| ADMIN | Export all data | PASS |  |
| ADMIN | Unlock a locked account | PASS |  |
| ADMIN | Hand over a leaver's work | PASS |  |
| ADMIN | Mail settings | PASS |  |
| ADMIN | Retention preview | PASS |  |
| ADMIN | Audit log is append-only (no delete route) | PASS |  |
| STAFF | AI assistant answers a question | PASS |  |
| PM | AI assistant answers a question | PASS |  |
| PMO | AI assistant answers a question | PASS |  |
| DECISION_MAKER | AI assistant answers a question | PASS |  |
| PROGRAM_MANAGER | AI assistant answers a question | PASS |  |
| ADMIN | AI assistant answers a question | PASS |  |
| STAFF | AI assistant never leaks other projects | PASS |  |
