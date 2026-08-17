import shutil
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.deps import get_current_user, get_db
from app.core.config import get_settings
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
    if export_dir and Path(export_dir).exists():
        parsed = parse_export(Path(export_dir))
        out.visualization = parsed.get("visualization")
        out.terminals = parsed.get("terminals")
        out.metrics = parsed.get("metrics")
    return out


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
    for row in db.scalars(select(JobStep).where(JobStep.job_id == job.id)):
        db.delete(row)
    db.delete(job)
    db.commit()
    ws = get_settings().data_dir / job.id
    if ws.exists():
        shutil.rmtree(ws, ignore_errors=True)
    return {"ok": True}
