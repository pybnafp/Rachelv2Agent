import traceback
from pathlib import Path
from app.worker.celery_app import celery_app
from app.core.config import get_settings


def ensure_workspace(job_id: str) -> Path:
    ws = get_settings().data_dir / job_id
    ws.mkdir(parents=True, exist_ok=True)
    return ws


def _build_driver(job, workspace: Path):
    """T9 接入后实现：RetroCmd + get_active_client + DbTraceSink → AgentDriver。"""
    raise NotImplementedError("wired in Task 9")


@celery_app.task(bind=True, acks_late=True, soft_time_limit=3600, time_limit=3900)
def run_retro_job(self, job_id: str) -> str:
    from app.db.session import SessionLocal
    from app.db.models import JobStatus
    from app.services.jobs import set_status
    db = SessionLocal()
    try:
        from app.db.models import Job
        job = db.get(Job, job_id)
        if job is None:
            return JobStatus.FAILED
        set_status(db, job_id, JobStatus.RUNNING)
        workspace = ensure_workspace(job_id)
        result = _build_driver(job, workspace).run()
        stats = {"steps": result.steps, "tokens_in": result.tokens_in,
                 "tokens_out": result.tokens_out, "reason": result.reason}
        if result.export_result.get("output_dir"):
            stats["export_dir"] = result.export_result["output_dir"]
        set_status(db, job_id, result.status, stats_patch=stats)
        return result.status
    except Exception as e:
        traceback.print_exc()
        set_status(db, job_id, "failed", error=str(e))
        return "failed"
    finally:
        db.close()
