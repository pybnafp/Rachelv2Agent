import json
import shutil
import time as _time
import anyio
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import delete as sa_delete, select
from sqlalchemy.orm import Session
from app.api.deps import bearer, get_current_user, get_db, resolve_token_user
from app.core.config import get_settings
from app.db import session as dbs
from app.db.models import Job, JobStatus, JobStep, User
from app.schemas.jobs import JobIn, JobOut, JobStepOut, ResultOut
from app.services.artifacts import parse_export
from app.services.jobs import count_active, set_status
from app.services.smiles import heavy_atoms, validate_smiles
from app.worker.tasks import run_retro_job

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("", response_model=JobOut, status_code=201)
def submit(body: JobIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = get_settings()
    canonical, err = validate_smiles(body.smiles)
    if err:
        raise HTTPException(400, err)
    if heavy_atoms(canonical) > s.max_heavy_atoms:
        raise HTTPException(400, f"molecule too large (> {s.max_heavy_atoms} heavy atoms)")
    if count_active(db, user.id) >= s.max_running_per_user:
        raise HTTPException(429, "concurrent job limit reached")
    job = Job(smiles=canonical, name=body.name[:120], user_id=user.id)
    db.add(job)
    db.commit()
    db.refresh(job)
    async_result = run_retro_job.delay(job.id)
    job.celery_task_id = getattr(async_result, "id", "") or ""
    db.commit()
    return job


@router.get("", response_model=list[JobOut])
def list_jobs(mine: int = 0, page: int = 1, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = select(Job).order_by(Job.created_at.desc()).offset((page - 1) * 20).limit(20)
    if mine or user.role != "admin":
        q = q.where(Job.user_id == user.id)
    return db.scalars(q).all()


@router.get("/{job_id}", response_model=JobOut)
def detail(job_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = _get_own_job(db, job_id, user)
    return job


def _get_own_job(db: Session, job_id: str, user: User) -> Job:
    job = db.get(Job, job_id)
    if job is None or (job.user_id != user.id and user.role != "admin"):
        raise HTTPException(404, "job not found")
    return job


@router.get("/{job_id}/result", response_model=ResultOut, response_model_exclude_none=True)
def result(job_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = _get_own_job(db, job_id, user)
    out = ResultOut(job=JobOut.model_validate(job))
    export_dir = (job.stats or {}).get("export_dir")
    if export_dir:
        # 防御纵深：export_dir 来自 stats JSON，仅接受 data_dir 之下的路径，越界则降级
        path = Path(export_dir).resolve()
        root = get_settings().data_dir.resolve()
        if root in path.parents and path.exists():
            parsed = parse_export(path)
            out.visualization = parsed.get("visualization")
            out.terminals = parsed.get("terminals")
            out.metrics = parsed.get("metrics")
            out.terminal_audit = parsed.get("terminal_audit")
    return out


_CONTENT_TYPES = {".html": "text/html", ".png": "image/png", ".json": "application/json",
                  ".txt": "text/plain", ".md": "text/markdown", ".jsonl": "application/json"}


@router.get("/{job_id}/files/{file_path:path}")
def files(job_id: str, file_path: str, token: str | None = None,
          cred: HTTPAuthorizationCredentials | None = Depends(bearer),
          db: Session = Depends(get_db)):
    # 双通道认证：iframe/<a>/<img> 无法携带 Authorization 头 → 允许 ?token=<jwt> 等价校验（M2-T10 裁定）
    user = resolve_token_user(cred, token, db)
    if user is None:
        raise HTTPException(401, "missing or invalid token")
    job = _get_own_job(db, job_id, user)
    root = (get_settings().data_dir / job.id).resolve()
    target = (root / file_path).resolve()
    if target != root and root not in target.parents:
        raise HTTPException(404, "file not found")
    if not target.is_file():
        raise HTTPException(404, "file not found")
    suffix = target.suffix.lower()
    return FileResponse(target, media_type=_CONTENT_TYPES.get(suffix, "application/octet-stream"))


_TERMINAL = {JobStatus.SUCCEEDED, JobStatus.PARTIAL, JobStatus.FAILED, JobStatus.CANCELLED}
SSE_POLL_SEC = 2.0
SSE_MAX_SEC = 7200
_SSE_IDLE_PINGS = 8  # ~16s without any steps/status frame → heartbeat comment


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _live_stats(db: Session, job_id: str, last_seq: int) -> dict:
    rows = db.scalars(select(JobStep).where(JobStep.job_id == job_id)).all()
    return {"steps": len(rows), "tokens": sum(r.tokens or 0 for r in rows),
            "duration_ms": sum(r.duration_ms or 0 for r in rows), "last_seq": last_seq}


def _poll_once(job_id: str, last_seq: int) -> tuple[list[JobStep], Job | None]:
    """短生命周期轮询会话：每轮独立 Session/连接，避免流期间长期占用池连接（SQLite 锁 / PG 池耗尽）。
    新会话天然读到最新数据，无需 expire_all。"""
    db_poll = dbs.SessionLocal()
    try:
        steps = db_poll.scalars(select(JobStep).where(
            JobStep.job_id == job_id, JobStep.seq > last_seq).order_by(JobStep.seq)).all()
        job = db_poll.get(Job, job_id)
        return steps, job
    finally:
        db_poll.close()


def _stats_once(job_id: str, last_seq: int) -> dict:
    db_stats = dbs.SessionLocal()
    try:
        return _live_stats(db_stats, job_id, last_seq)
    finally:
        db_stats.close()


@router.get("/{job_id}/events")
def events(job_id: str, request: Request, token: str | None = None,
           cred: HTTPAuthorizationCredentials | None = Depends(bearer),
           db: Session = Depends(get_db)):
    # EventSource 无法带 Authorization 头 → 与 /files 共用 ?token= 双通道鉴权
    user = resolve_token_user(cred, token, db)
    if user is None:
        raise HTTPException(401, "missing or invalid token")
    job = _get_own_job(db, job_id, user)

    async def gen():
        last_seq = 0
        last_status = None
        idle = 0
        t0 = _time.monotonic()
        while _time.monotonic() - t0 < SSE_MAX_SEC:
            if await request.is_disconnected():
                return
            # 每轮短生命周期会话（run_in_threadpool 避免同步 ORM 阻塞事件循环），
            # 注入的 db 仅用于流开始前的鉴权与 _get_own_job，不进入流循环。
            steps, current = await run_in_threadpool(_poll_once, job.id, last_seq)
            if steps:
                payload = [JobStepOut.model_validate(s).model_dump(mode="json") for s in steps]
                last_seq = steps[-1].seq
                if last_status is None:
                    stats_live = await run_in_threadpool(_stats_once, job.id, last_seq)
                    yield _sse("snapshot", {"status": current.status if current else None,
                                            "stats_live": stats_live, "steps": payload})
                    last_status = "init"
                else:
                    yield _sse("steps", {"steps": payload})
                idle = 0
            elif last_status is None:
                # No steps yet (or none ever): still emit an (empty) snapshot first.
                stats_live = await run_in_threadpool(_stats_once, job.id, last_seq)
                yield _sse("snapshot", {"status": current.status if current else None,
                                        "stats_live": stats_live, "steps": []})
                last_status = "init"
                idle = 0
            if current and current.status != last_status:
                last_status = current.status
                yield _sse("status", {"status": current.status, "stats": current.stats or {}})
                if current.status in _TERMINAL:
                    yield _sse("done", {"status": current.status})
                    return
                idle = 0
            idle += 1
            if idle >= _SSE_IDLE_PINGS:
                yield ": ping\n\n"
                idle = 0
            await anyio.sleep(SSE_POLL_SEC)
        yield _sse("done", {"status": "timeout"})

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/{job_id}/trace")
def trace(job_id: str, after: int = 0, user: User = Depends(get_current_user),
          db: Session = Depends(get_db)):
    job = _get_own_job(db, job_id, user)
    rows = db.scalars(select(JobStep).where(JobStep.job_id == job.id, JobStep.seq > after)
                      .order_by(JobStep.seq)).all()
    return {"steps": [JobStepOut.model_validate(r) for r in rows]}


@router.post("/{job_id}/cancel")
def cancel(job_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = _get_own_job(db, job_id, user)
    if job.status not in (JobStatus.QUEUED, JobStatus.RUNNING):
        raise HTTPException(409, f"cannot cancel job in status {job.status}")
    if job.celery_task_id:
        from app.worker.celery_app import celery_app
        try:
            celery_app.control.revoke(job.celery_task_id, terminate=True, signal="SIGTERM")
        except Exception:
            pass  # no broker in eager/test mode
    set_status(db, job.id, JobStatus.CANCELLED)
    return {"ok": True, "status": "cancelled"}


@router.delete("/{job_id}")
def delete(job_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = _get_own_job(db, job_id, user)
    # 立即批量删除子行：ORM 逐行 delete 会先 flush 父对象，PostgreSQL 上触发
    # job_steps_job_id_fkey 违反（模型未声明 relationship，unit-of-work 顺序不定）。
    db.execute(sa_delete(JobStep).where(JobStep.job_id == job.id))
    db.delete(job)
    db.commit()
    ws = get_settings().data_dir / job.id
    if ws.exists():
        shutil.rmtree(ws, ignore_errors=True)
    return {"ok": True}
