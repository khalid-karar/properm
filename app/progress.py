"""Live progress of a long job (reading a book and drafting a plan), so the screen can show what is happening.
Kept in memory: it only matters while the job runs, and a lost entry just means the bar becomes indeterminate."""
import threading
import time

_lock = threading.Lock()
_jobs: dict[tuple[int, str], dict] = {}
TTL = 3600


def update(user_id: int, key: str | None, pct: float, step: str, **info) -> None:
    if not key:
        return
    now = time.time()
    with _lock:
        for k in [k for k, v in _jobs.items() if now - v["at"] > TTL]:
            del _jobs[k]
        _jobs[(user_id, key)] = {"pct": int(max(0, min(100, pct))), "step": step, "info": info, "at": now, "started": _jobs.get((user_id, key), {}).get("started", now)}


def get(user_id: int, key: str) -> dict | None:
    with _lock:
        j = _jobs.get((user_id, key))
        return {"pct": j["pct"], "step": j["step"], "info": j["info"], "seconds": int(time.time() - j["started"])} if j else None
