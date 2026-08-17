from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.db.models import User
from app.schemas.auth import MeOut, RegisterIn, TokenOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=TokenOut, status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.username == body.username)):
        raise HTTPException(409, "username already exists")
    role = "admin" if db.scalar(select(User).limit(1)) is None else "user"
    u = User(username=body.username, password_hash=hash_password(body.password), role=role)
    db.add(u)
    db.commit()
    db.refresh(u)
    return TokenOut(access_token=create_access_token(u.id, u.role), role=role)


@router.post("/login", response_model=TokenOut)
def login(body: RegisterIn, db: Session = Depends(get_db)):
    u = db.scalar(select(User).where(User.username == body.username))
    if not u or not verify_password(body.password, u.password_hash):
        raise HTTPException(401, "invalid credentials")
    return TokenOut(access_token=create_access_token(u.id, u.role), role=u.role)


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user)):
    return MeOut(id=user.id, username=user.username, role=user.role)
