import traceback
from pathlib import Path
from app.worker.celery_app import celery_app
from app.core.config import get_settings


def ensure_workspace(job_id: str) -> Path:
    ws = get_settings().data_dir / job_id
    ws.mkdir(parents=True, exist_ok=True)
    return ws


def _ensure_engine():
    """Worker 进程惰性绑定 DB engine；幂等，且不覆盖测试中已 rebind 的 SessionLocal。"""
    import app.db.session as dbs
    if dbs.engine is not None:
        return
    from app.db.base import Base
    import app.db.models  # register tables on Base
    from sqlalchemy import inspect
    if dbs.engine is None:
        # 测试可能已把 SessionLocal 绑到测试引擎：init_engine 会 configure(bind=默认库)，
        # 需保留原 bind，否则 worker 读写会落到 dev.db（幂等：engine 已绑定则直接返回）。
        bound = dbs.SessionLocal.kw.get("bind")
        dbs.init_engine()
        if bound is not None and dbs.SessionLocal.kw.get("bind") is not bound:
            dbs.SessionLocal.configure(bind=bound)
    insp = inspect(dbs.engine)
    if not insp.get_table_names():
        Base.metadata.create_all(dbs.engine)


def _build_driver(job, workspace: Path):
    """RetroCmd + get_active_client + DbTraceSink → AgentDriver。"""
    from app.agent.driver import AgentDriver, DriverLimits
    from app.agent.prompts import build_task_prompt
    from app.agent.trace import DbTraceSink
    from app.api.admin import get_active_client
    from app.db.session import SessionLocal
    from Rachel.main.retro_cmd import RetroCmd
    retro = RetroCmd(str(workspace / "session.json"))
    db = SessionLocal()
    try:
        llm = get_active_client(db)
    finally:
        db.close()
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
    _ensure_engine()
    db = SessionLocal()
    try:
        from app.db.models import Job
        job = db.get(Job, job_id)
        if job is None:
            return JobStatus.FAILED
        if job.status == JobStatus.CANCELLED:  # 取消先于 pickup
            return JobStatus.CANCELLED
        set_status(db, job_id, JobStatus.RUNNING)
        workspace = ensure_workspace(job_id)
        result = _build_driver(job, workspace).run()
        db.expire_all()
        if db.get(Job, job_id).status == JobStatus.CANCELLED:
            return JobStatus.CANCELLED  # 取消竞态：不覆盖 CANCELLED
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
        # 路线已完成、状态已翻转，再跑可降级审计（不阻塞用户看到结果）
        if result.export_result.get("output_dir"):
            from app.services.terminal_audit import run_terminal_audit
            export_dir = Path(result.export_result["output_dir"])
            if export_dir.exists():
                audit_payload = run_terminal_audit(export_dir)  # offline 取 settings（测试=PUBCHEM_OFFLINE）
            else:
                audit_payload = {"available": False, "error": "no export dir"}
            set_status(db, job_id, result.status, stats_patch={
                "terminal_audit_summary": audit_payload.get("summary") or {
                    "available": audit_payload.get("available")}})
        return result.status
    except Exception as e:
        traceback.print_exc()
        set_status(db, job_id, JobStatus.FAILED, error=str(e))
        return JobStatus.FAILED
    finally:
        db.close()
