# Scale notes

`python scripts/loadtest.py` seeds 50 staff, 40 projects, 400 tasks and 100,000 timesheet rows into a throwaway SQLite file, starts the server, and has 50 simulated users read the usual screens for 30 seconds.

Result on a 2-core test machine (server and the 50 simulated users sharing it, one server process, SQLite):

| | before | after |
|---|---|---|
| requests served in 25 s | 545 | 1,786 |
| worst p95 | 5.8 s (approvals queue) | 0.94 s (portfolio export) |
| typical screen p50 | 1.2–1.8 s | 30–115 ms |

What changed: the approvals queue and "my timesheet" no longer return every row (queue: oldest 300, `limit` up to 2,000; my timesheet: last 90 days by default, `start`/`end`/`limit`/`offset`), approver checks are remembered per project, and 29 indexes were added (migration `0003`).

Still the heaviest: the portfolio export (earned-value for every running project, about 0.35 s median with 40 projects). If the portfolio grows past a few hundred projects, cache it per day.

This was measured on SQLite. Oracle has its own optimiser: re-run the script against an EMPTY Oracle test schema (`DATABASE_URL=oracle+oracledb://... python scripts/loadtest.py`) before go-live and run several server processes (`uvicorn --workers 4`) behind the load balancer.
