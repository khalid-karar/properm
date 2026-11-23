"""Load test: seed 50 staff, 40 projects and N timesheet rows (default 100,000) into a throwaway SQLite file, start the server,
then 50 simulated users read the usual screens for a while. Prints p50/p95 per screen.
   python scripts/loadtest.py [--rows 100000] [--users 50] [--seconds 30]"""
import argparse
import os
import random
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from datetime import date, timedelta

ap = argparse.ArgumentParser()
ap.add_argument("--rows", type=int, default=100_000)
ap.add_argument("--users", type=int, default=50)
ap.add_argument("--seconds", type=int, default=30)
ap.add_argument("--port", type=int, default=8791)
ap.add_argument("--reuse", help="path of a database seeded by an earlier run (skips seeding)")
a = ap.parse_args()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB = a.reuse or os.path.join(tempfile.mkdtemp(), "load.db")
os.environ.update(DATABASE_URL=os.environ.get("DATABASE_URL", f"sqlite:///{DB}"), PROPERM_SECRET="load-test-secret-load-test-secret-12345", PROPERM_DEMO="1", PROPERM_DEMO_PASSWORD="demo-pass-1", PROPERM_LOGIN_MAX_PER_WINDOW="100000")

from app import demo                                            # noqa: E402
from app.deps import hash_pw                                    # noqa: E402
from app.main import app_from_env                               # noqa: E402
from app.models import Activity, Assignment, Project, TimesheetEntry, User  # noqa: E402

app = app_from_env()
from fastapi.testclient import TestClient                       # noqa: E402
if not a.reuse:
    demo.seed(app, "demo-pass-1", TestClient(app))
t0 = time.time()
with (app.state.Session() if not a.reuse else __import__("contextlib").nullcontext()) as db:
  if db is not None:
    pw = hash_pw("demo-pass-1")
    staff = [User(staff_id=f"L{i:03d}", full_name=f"Load User {i}", role="STAFF", password_hash=pw, rate_grade="G1") for i in range(a.users)]
    db.add_all(staff)
    pm_id = db.query(User).filter_by(staff_id="pm1").one().id
    projs = [Project(pm_id=pm_id, number=f"LD-{i:03d}", name=f"Load project {i}", state="execution", planned_start=date(2026, 1, 1), planned_end=date(2027, 12, 31), project_type="hybrid") for i in range(40)]
    db.add_all(projs)
    db.flush()
    acts = []
    for p in projs:
        for j in range(10):
            acts.append(Activity(project_id=p.id, code=f"A{j}", name=f"Task {j}", phase="execution", planned_hours=400, planned_start=date(2026, 1, 1), planned_end=date(2027, 12, 31)))
    db.add_all(acts)
    db.flush()
    for i, u in enumerate(staff):
        for p in random.sample(projs, 4):
            db.add(Assignment(project_id=p.id, user_id=u.id))
    db.flush()
    rnd, rows = random.Random(1), []
    for n in range(a.rows):
        u = staff[n % len(staff)]
        act = acts[rnd.randrange(len(acts))]
        d = date(2026, 1, 1) + timedelta(days=rnd.randrange(0, 700))
        rows.append(TimesheetEntry(user_id=u.id, project_id=act.project_id, activity_id=act.id, entry_date=d, hours=rnd.choice([2, 4, 6, 8]), status=rnd.choice(["approved"] * 8 + ["submitted"]), flags=[]))
        if len(rows) == 5000:
            db.bulk_save_objects(rows); rows = []
    db.bulk_save_objects(rows)
    db.commit()
print(f"db: {DB}")
print(f"seeded {a.rows} rows, {a.users} staff in {time.time() - t0:.1f}s", flush=True)

srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app_from_env", "--factory", "--port", str(a.port), "--log-level", "warning"], env=os.environ)
import httpx                                                    # noqa: E402
base = f"http://127.0.0.1:{a.port}"
for _ in range(60):
    try:
        httpx.get(base + "/health", timeout=1); break
    except Exception:
        time.sleep(0.5)
tok = lambda sid: {"Authorization": "Bearer " + httpx.post(base + "/auth/login", json={"staff_id": sid, "password": "demo-pass-1"}, timeout=30).json()["access_token"]}
H = {r: tok(r) for r in ("admin", "pmo1", "pm1")}
staff_h = [tok(f"L{i:03d}") for i in range(min(a.users, 50))]
ws = (date.today() - timedelta(days=date.today().weekday())).isoformat()
SCREENS = [("staff: my week", "staff", f"/timesheets/mine?week_of={ws}"), ("staff: utilization", "staff", "/me/utilization"), ("staff: home", "staff", "/projects"),
           ("pmo: projects", "pmo1", "/projects"), ("pmo: approvals queue", "pmo1", "/timesheets/queue"), ("pmo: alerts", "pmo1", "/alerts"), ("pmo: portfolio csv", "pmo1", "/export/portfolio.csv"),
           ("pmo: timesheets xlsx", "pmo1", "/export/timesheets.xlsx?project_id=1"), ("admin: users", "admin", "/users"), ("pm: projects", "pm1", "/projects")]
lat: dict[str, list[float]] = {s[0]: [] for s in SCREENS}
errs: dict[str, int] = {s[0]: 0 for s in SCREENS}
stop = time.time() + a.seconds


def worker(i):
    cl = httpx.Client(base_url=base, timeout=60)
    rnd = random.Random(i)
    while time.time() < stop:
        name, who, path = rnd.choice(SCREENS)
        h = staff_h[i % len(staff_h)] if who == "staff" else H[who]
        t = time.time()
        try:
            r = cl.get(path, headers=h)
            ok = r.status_code < 400
        except Exception:
            ok = False
        lat[name].append(time.time() - t)
        if not ok:
            errs[name] += 1
        time.sleep(rnd.uniform(0.2, 1.0))


ths = [threading.Thread(target=worker, args=(i,)) for i in range(a.users)]
[t.start() for t in ths]
[t.join() for t in ths]
srv.terminate()
print(f"{'screen':28} {'n':>5} {'p50 ms':>8} {'p95 ms':>8} {'max ms':>8} {'errors':>6}")
worst = 0
for n, v in lat.items():
    if not v:
        continue
    v.sort()
    p95 = v[int(len(v) * .95) - 1] * 1000 if len(v) > 1 else v[0] * 1000
    worst = max(worst, p95)
    print(f"{n:28} {len(v):5d} {statistics.median(v) * 1000:8.0f} {p95:8.0f} {v[-1] * 1000:8.0f} {errs[n]:6d}")
print(f"total requests {sum(len(v) for v in lat.values())}, errors {sum(errs.values())}, worst p95 {worst:.0f} ms")
