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


def resolve_token_user(
    cred: HTTPAuthorizationCredentials | None,
    token: str | None,
    db: Session,
) -> User | None:
    """Resolve Bearer credential or ?token= query (either one) to a User.

    Shared by /files and /events (channels that cannot send Authorization
    headers, e.g. iframe/<img>/EventSource). Returns None on any failure
    (missing/invalid token, unknown user); callers raise 401.
    """
    from app.core.security import decode_token
    raw = None
    if cred is not None and cred.credentials:
        raw = cred.credentials
    elif token:
        raw = token
    if not raw:
        return None
    payload = decode_token(raw)
    if not payload or "sub" not in payload:
        return None
    try:
        uid = int(payload["sub"])
    except (TypeError, ValueError):
        return None
    return db.get(User, uid)


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
