import traceback
from pathlib import Path
from app.worker.celery_app import celery_app
from app.core.config import get_settings


def ensure_workspace(job_id: str) -> Path:
    ws = get_settings().data_dir / job_id
    ws.mkdir(parents=True, exist_ok=True)
    return ws


def _build_driver(job, workspace: Path):
    """RetroCmd + get_active_client + DbTraceSink → AgentDriver。"""
    from app.agent.driver import AgentDriver, DriverLimits
    from app.agent.prompts import build_task_prompt
    from app.agent.trace import DbTraceSink
    from app.api.admin import get_active_client
    from app.db.session import SessionLocal
    from Rachel.main.retro_cmd import RetroCmd
    retro = RetroCmd(str(workspace / "session.json"))
    llm = get_active_client(SessionLocal())
    if llm is None:
        raise RuntimeError("no active llm provider configured")
    trace = DbTraceSink(SessionLocal, job.id)
    return AgentDriver(retro=retro, llm=llm, trace=trace,
                       task_prompt=build_task_prompt(job.smiles, job.name),
                       name=job.name or job.smiles[:20],
                       limits=DriverLimits(), workspace=workspace)


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
            from app.services.artifacts import parse_export
            export_dir = Path(result.export_result["output_dir"])
            if export_dir.exists():
                parsed = parse_export(export_dir)
                stats["artifacts"] = parsed.get("metrics", {})
                stats["artifacts"]["incomplete"] = parsed.get("incomplete", False)
        set_status(db, job_id, result.status, stats_patch=stats)
        return result.status
    except Exception as e:
        traceback.print_exc()
        set_status(db, job_id, JobStatus.FAILED, error=str(e))
        return JobStatus.FAILED
    finally:
        db.close()
