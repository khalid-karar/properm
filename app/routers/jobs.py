import os

from fastapi import APIRouter, Depends

from .. import scheduler
from ..deps import get_db, require_roles
from ..models import JobRun, User

router = APIRouter(tags=["jobs"])


@router.get("/admin/jobs")
def list_jobs(db=Depends(get_db), _: User = Depends(require_roles("ADMIN", "PMO"))):
    rows = db.query(JobRun).order_by(JobRun.id.desc()).limit(60).all()
    return {"scheduler_on": os.environ.get("PROPERM_SCHEDULER") == "1", "jobs": list(scheduler.JOBS),
            "runs": [{"name": r.name, "date": r.run_date, "status": r.status, "detail": r.detail, "at": r.started_at} for r in rows]}


@router.post("/admin/jobs/run")
def run_now(force: bool = False, db=Depends(get_db), _: User = Depends(require_roles("ADMIN", "PMO"))):
    """Runs the jobs that have not run today (force=true runs them again). Also the entry point for an external cron."""
    return scheduler.run_due(db, force=force)
