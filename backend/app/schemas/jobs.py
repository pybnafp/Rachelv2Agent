from datetime import datetime
from pydantic import BaseModel


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
