from datetime import datetime, timezone
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.db.models import Job, JobStatus


def count_active(db: Session, user_id: int) -> int:
    return db.scalar(select(func.count()).select_from(Job).where(
        Job.user_id == user_id, Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]))) or 0


def set_status(db: Session, job_id: str, status: str, error: str = "", stats_patch: dict | None = None) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise ValueError(f"job not found: {job_id}")
    job.status = status
    if error:
        job.error = error
    if stats_patch:
        stats = dict(job.stats or {})
        stats.update(stats_patch)
        job.stats = stats
    now = datetime.now(timezone.utc)
    if status == JobStatus.RUNNING and job.started_at is None:
        job.started_at = now
    if status in (JobStatus.SUCCEEDED, JobStatus.PARTIAL, JobStatus.FAILED, JobStatus.CANCELLED):
        job.finished_at = now
    db.commit()
    db.refresh(job)
    return job
