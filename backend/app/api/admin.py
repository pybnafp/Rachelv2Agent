from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.deps import get_current_user, get_db
from app.db.models import LlmProvider, User
from app.schemas.admin import ProviderIn, ProviderOut

router = APIRouter(prefix="/api/admin", tags=["admin"])


def seed_default_provider(db: Session) -> None:
    from app.core.config import get_settings
    if db.scalar(select(LlmProvider).limit(1)) is not None:
        return
    s = get_settings()
    db.add(LlmProvider(name=s.default_llm_name, base_url=s.deepseek_base_url,
                       api_key=s.deepseek_api_key or "", model=s.deepseek_model, is_active=True))
    db.commit()


def get_active_client(db: Session):
    p = db.scalar(select(LlmProvider).where(LlmProvider.is_active))
    if p is None:
        return None
    if p.model == "mock":
        from app.agent.llm_client import MockLLMClient, ToolCall
        return MockLLMClient(script=[[ToolCall("auto", "finish", {"summary": "mock"})]])
    from app.agent.llm_client import OpenAICompatClient
    return OpenAICompatClient(p.base_url, p.api_key, p.model, p.temperature, p.max_output)


@router.get("/llm-providers", response_model=list[ProviderOut])
def list_providers(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_admin(user)
    return db.scalars(select(LlmProvider)).all()


@router.put("/llm-providers", response_model=ProviderOut)
def upsert_provider(body: ProviderIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_admin(user)
    p = db.scalar(select(LlmProvider).where(LlmProvider.name == body.name))
    if p is None:
        p = LlmProvider(name=body.name, api_key="")
    for k in ("base_url", "model", "temperature", "max_output", "is_active"):
        setattr(p, k, getattr(body, k))
    if p.id is None:
        db.add(p)
        db.flush()  # assign p.id before deactivating others
    if body.api_key:
        p.api_key = body.api_key
    if body.is_active:
        for other in db.scalars(select(LlmProvider).where(LlmProvider.id != p.id)).all():
            other.is_active = False
    db.commit()
    db.refresh(p)
    return p


def _require_admin(user: User):
    if user.role != "admin":
        raise HTTPException(403, "admin only")
