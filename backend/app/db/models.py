import uuid
from datetime import datetime, timezone
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


def utcnow(): return datetime.now(timezone.utc)
JSONType = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


class JobStatus:
    QUEUED = "queued"; RUNNING = "running"; SUCCEEDED = "succeeded"
    PARTIAL = "partial"; FAILED = "failed"; CANCELLED = "cancelled"


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(sa.String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(sa.String(128))
    role: Mapped[str] = mapped_column(sa.String(16), default="user")
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=utcnow)


class LlmProvider(Base):
    __tablename__ = "llm_providers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(64), unique=True)
    base_url: Mapped[str] = mapped_column(sa.String(256))
    api_key: Mapped[str] = mapped_column(sa.String(256))
    model: Mapped[str] = mapped_column(sa.String(128))
    temperature: Mapped[float] = mapped_column(default=0.2)
    max_output: Mapped[int] = mapped_column(default=4096)
    is_active: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=utcnow)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True, default=lambda: uuid.uuid4().hex)
    user_id: Mapped[int] = mapped_column(sa.ForeignKey("users.id"), index=True)
    smiles: Mapped[str] = mapped_column(sa.Text)
    name: Mapped[str] = mapped_column(sa.String(128), default="")
    status: Mapped[str] = mapped_column(sa.String(16), default=JobStatus.QUEUED, index=True)
    provider_id: Mapped[int | None] = mapped_column(sa.ForeignKey("llm_providers.id"), nullable=True)
    error: Mapped[str] = mapped_column(sa.Text, default="")
    stats: Mapped[dict] = mapped_column(JSONType, default=dict)
    celery_task_id: Mapped[str] = mapped_column(sa.String(64), default="")
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)


class JobStep(Base):
    __tablename__ = "job_steps"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(sa.ForeignKey("jobs.id"), index=True)
    seq: Mapped[int] = mapped_column(sa.Integer)
    command: Mapped[str] = mapped_column(sa.String(32))
    args: Mapped[dict] = mapped_column(JSONType, default=dict)
    result_summary: Mapped[str] = mapped_column(sa.Text, default="")
    status: Mapped[str] = mapped_column(sa.String(16), default="ok")
    tokens: Mapped[int] = mapped_column(sa.Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(sa.Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=utcnow)
