from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db.models import User

bearer = HTTPBearer(auto_error=False)


def get_db():
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    cred: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    from app.core.security import decode_token
    if cred is None:
        raise HTTPException(401, "missing token")
    payload = decode_token(cred.credentials)
    if not payload:
        raise HTTPException(401, "invalid token")
    user = db.get(User, int(payload["sub"]))
    if not user:
        raise HTTPException(401, "user not found")
    return user
