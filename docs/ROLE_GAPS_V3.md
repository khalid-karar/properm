# PROPERM role review, round 3: checked against the PMP standard (2026-11-23)

**Benchmark:**
- PMI *PMP Examination Content Outline*: People 42%, Process 50%, Business Environment 8%. About half of the outline is agile or hybrid.
- *PMBOK Guide* 7th edition: eight performance domains.
- *PMBOK Guide* 6th edition: ten knowledge areas, used as a detailed checklist.
- PMI *Standard for Program Management*, and common practice in government PMOs.

**Method:** every item below was checked against the code at commit `ec579c2` (230 endpoints, 31 pages, 63 tables), not against earlier notes.

Status: ✅ covered · 🟡 partly · ⬜ missing. Priority: **P1** = a PMP-trained practitioner would expect it in a PMO system; **P2** = expected by mature PMOs; **P3** = nice to have.

---

## 1. Coverage by PMBOK 7 performance domain

| Domain | What is there | Main gaps |
|---|---|---|
| Stakeholders | Register with power, interest and engagement; RACI; communication plan | Engagement is one text field: there is no "current vs desired" engagement matrix 🟡 |
| Team | Assignments, capacity, leave, resource requests, load, RACI | No skills register, so resource requests cannot be matched to people. No team charter, training needs, recognition or team-health pulse ⬜ |
| Development approach and life cycle | Project type field (predictive / hybrid / adaptive), stage gates | The type changes nothing. There are **no agile tools**: backlog, sprints, velocity, burndown ⬜ |
| Planning | Activities, milestones, dependencies, critical path, KPIs, templates, allocations, baseline | Activities are a **flat list**, with no work breakdown structure (deliverables → work packages) ⬜. No cost reserves ⬜ |
| Project work | Timesheets, progress, actions, issues, documents, procurement as cost lines | No vendor or contract register ⬜. Documents have no versions ⬜ |
| Delivery | Benefits, KPIs, closure checklist | No requirements register, no traceability, no formal **deliverable acceptance** (only a closure checkbox) ⬜. No quality log ⬜ |
| Measurement | EVM (PV, EV, AC, CPI, SPI, EAC, ETC, VAC), variance, trends, S-curve, dashboards, compliance | No TCPI, CV or SV shown 🟡. No risk or issue trend 🟡 |
| Uncertainty | Risk register, matrix, owners, reviews, program risks, what-if | No response **strategy** (avoid, mitigate, transfer, accept, escalate), triggers or contingency amounts. No opportunities (positive risks) 🟡 |

## 2. Coverage by knowledge area (PMBOK 6 checklist)

| Area | Status | Notes |
|---|---|---|
| Integration | 🟡 | Charter is a document upload plus one scope text. No structured **charter**: objectives, success criteria, assumptions, constraints, exclusions. No assumption log. Change control, decision log and closure are ✅ |
| Scope | ⬜ | No WBS hierarchy, requirements register, traceability or acceptance of deliverables |
| Schedule | ✅ | Baseline, dependencies, critical path, forecast dates, milestones, timeline |
| Cost | 🟡 | Budget, actuals, EVM, forecast and envelope are ✅. Missing: contingency and management reserve, budget by cost category vs actual, funding/cash-flow plan, TCPI |
| Quality | ⬜ | KPIs only. No quality plan, review checklist, defect or non-conformance log |
| Resources | 🟡 | Capacity, leave, requests and load are ✅. Skills and team development ⬜ |
| Communications | ✅ | Communication plan, weekly reports, board pack, notifications |
| Risk | 🟡 | Register and reviews ✅; response strategy, triggers, reserves, opportunities ⬜ |
| Procurement | ⬜ | The vendor is free text on a cost line. No contract register (value, dates, payment milestones, invoiced vs contract value), vendor performance or Etimad reference |
| Stakeholders | 🟡 | See the domain table |

## 3. Coverage by PMP exam domain

| Exam domain | Status | Gaps |
|---|---|---|
| People (42%) | 🟡 | Skills, team charter and ground rules, training, recognition, team health, conflict/impediment log (issues cover part of this) |
| Process (50%) | 🟡 | Agile and hybrid delivery, WBS, requirements and acceptance, quality, procurement, reserves |
| Business Environment (8%) | 🟡 | Benefits and governance ✅. Missing: **compliance requirements register** (for example PDPL, NCA controls, sector regulators); **strategic objectives register** linking projects to the organisation's objectives (for example Vision 2030 programs); organisational change and readiness for go-live |

---

## 4. What each role still misses

### Staff
| Need | Status | Pri |
|---|---|---|
| Work from a task board (to do, doing, done) and update my own tasks on adaptive projects | ⬜ | P1 |
| Update progress on activities I own | ⬜ (activities have no owner) | P2 |
| Keep my skills and certifications up to date so the PMO can staff me | ⬜ | P2 |

### Project manager
| Need | Status | Pri |
|---|---|---|
| Structured charter: objectives, success criteria, assumptions, constraints, exclusions | ⬜ | P1 |
| WBS: deliverables with work packages under them, with a WBS dictionary | ⬜ | P1 |
| Requirements register with traceability to deliverables and tests | ⬜ | P1 |
| Formal acceptance of each deliverable by the client or sponsor, with a record | ⬜ | P1 |
| Agile delivery for adaptive and hybrid projects: backlog, sprints, velocity, burndown | ⬜ | P1 |
| Vendor contracts: value, payment milestones, invoiced vs contract, performance | ⬜ | P1 |
| Risk response strategy, trigger, contingency amount; opportunities | 🟡 | P2 |
| Contingency and management reserve, drawdown recorded through change control | ⬜ | P2 |
| Quality log: reviews, defects, non-conformances | ⬜ | P2 |
| Stakeholder engagement: current vs desired level | 🟡 | P2 |
| Document versions and approval | ⬜ | P2 |
| Assumption log | ⬜ | P2 |

### PMO
| Need | Status | Pri |
|---|---|---|
| Skills register to match resource requests to people | ⬜ | P1 |
| Strategic objectives register; every project and proposal linked to objectives; coverage view | ⬜ | P1 |
| Compliance requirements register per project (regulations, NCA, PDPL) with evidence | ⬜ | P2 |
| Portfolio risk and issue trend over time | 🟡 | P2 |
| Vendor performance across projects | ⬜ | P2 |
| PMO maturity / methodology compliance by project type | 🟡 (templates exist) | P3 |

### Program manager
| Need | Status | Pri |
|---|---|---|
| Program objectives linked to strategy, and benefits linked to them | ⬜ | P2 |
| Transition and organisational change readiness (training, communications, go-live checklist) | ⬜ | P2 |

### Decision maker
| Need | Status | Pri |
|---|---|---|
| See how the portfolio covers each strategic objective (and where nothing is being done) | ⬜ | P1 |
| Sponsor acceptance of deliverables and project closure | 🟡 (closure checklist only) | P1 |
| Approve reserve drawdowns | ⬜ | P2 |

### Administrator
| Need | Status | Pri |
|---|---|---|
| Single sign-on (Active Directory or Nafath) and two-factor sign-in | ⬜ (needs real hosting) | P2 |
| Restore from a backup file | ⬜ | P2 |
| Data retention rules (how long audit and documents are kept) | ⬜ | P3 |

---

## 5. Recommended build order

**Status 2026-11-23: all seven steps are built** (tables, API, UI, EN/AR, demo data, tests). Single sign-on is the only item left, because it needs real hosting and an identity provider.
1. ✅ **Scope and acceptance**: structured charter and assumption log, WBS (deliverables → work packages), requirements with traceability, deliverable acceptance by the sponsor or client.
2. ✅ **Agile and hybrid delivery**: backlog, sprints, task board for staff, velocity, burndown. Switched on when the project type is adaptive or hybrid.
3. ✅ **Strategy and compliance**: strategic objectives register with project/proposal links and a coverage view; compliance requirements register with evidence.
4. ✅ **Procurement**: contract register, payment milestones, invoices against contract value, vendor performance.
5. ✅ **People**: skills and certifications, matching on resource requests, team charter, training needs.
6. ✅ **Risk, cost and quality depth**: response strategies, triggers, opportunities, reserves with drawdown, TCPI/CV/SV, quality log, document versions, engagement matrix.
7. ✅ **Admin**: restore from backup, retention rules. Two-factor sign-in (TOTP) is built; SSO is not (needs hosting and an identity provider).
