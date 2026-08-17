from datetime import datetime
from pydantic import BaseModel


class JobStepOut(BaseModel):
    seq: int
    command: str
    args: dict
    result_summary: str
    status: str
    tokens: int
    duration_ms: int
    created_at: datetime
    model_config = {"from_attributes": True}


class JobIn(BaseModel):
    smiles: str
    name: str = ""


class JobOut(BaseModel):
    id: str
    smiles: str
    name: str
    status: str
    error: str
    stats: dict
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    model_config = {"from_attributes": True}


class ResultOut(BaseModel):
    job: JobOut
    visualization: dict | None = None
    terminals: list | None = None
    metrics: dict | None = None
    terminal_audit: dict | None = None
