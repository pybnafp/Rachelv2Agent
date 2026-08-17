from app.worker.celery_app import celery_app


@celery_app.task(bind=True, acks_late=True, soft_time_limit=3600, time_limit=3900)
def run_retro_job(self, job_id: str) -> str:
    from app.db.session import SessionLocal
    from app.services.jobs import set_status
    from app.db.models import JobStatus
    db = SessionLocal()
    try:
        set_status(db, job_id, JobStatus.RUNNING)
        set_status(db, job_id, JobStatus.SUCCEEDED, stats_patch={"steps": 0})
        return JobStatus.SUCCEEDED
    finally:
        db.close()
