from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.deps import get_current_user, get_db
from app.core.config import get_settings
from app.db.models import Job, User
from app.schemas.jobs import JobIn, JobOut
from app.services.jobs import count_active
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
    job = db.get(Job, job_id)
    if job is None or (job.user_id != user.id and user.role != "admin"):
        raise HTTPException(404, "job not found")
    return job
