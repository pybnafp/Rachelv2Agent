from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.db.models import User
from app.schemas.auth import (ChangePasswordIn, LoginIn, MeOut, RegisterIn,
                              ResendIn, TokenOut, VerifyIn)
from app.services import email as email_svc

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _send_or_500(db: Session, email_addr: str) -> None:
    """签发并发送验证码；冷却 429；发送失败则 500（验证码已入库但用户收不到，
    等待冷却结束后可通过 resend 重发）。"""
    try:
        code = email_svc.issue_code(db, email_addr)
    except ValueError as e:  # 重发冷却
        raise HTTPException(429, str(e))
    try:
        email_svc.send_code(email_addr, code)
    except Exception:
        raise HTTPException(500, "邮件发送失败，请稍后重试")


@router.post("/register", status_code=202)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if not email_svc.EMAIL_RE.match(email):
        raise HTTPException(400, "邮箱格式不正确")
    if len(body.password) < 6:
        raise HTTPException(400, "密码至少 6 位")
    u = db.scalar(select(User).where(User.email == email))
    if u and u.is_verified:
        raise HTTPException(409, "邮箱已注册")
    if u:  # 未验证：更新密码后重发验证码（冷却适用）
        u.password_hash = hash_password(body.password)
        db.commit()
    else:
        u = User(email=email, password_hash=hash_password(body.password),
                 role="user", is_verified=False)
        db.add(u)
        db.commit()
    _send_or_500(db, email)
    return {"ok": True, "message": "验证码已发送至邮箱"}


@router.post("/verify", response_model=TokenOut)
def verify(body: VerifyIn, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    u = db.scalar(select(User).where(User.email == email))
    if not u or u.is_verified or not email_svc.verify_code(db, email, body.code):
        raise HTTPException(400, "验证码错误或已过期")
    u.is_verified = True
    others_verified = db.scalar(
        select(func.count()).select_from(User).where(User.is_verified.is_(True), User.id != u.id))
    if not others_verified:
        u.role = "admin"  # 首个完成验证的用户
    db.commit()
    return TokenOut(access_token=create_access_token(u.id, u.role), role=u.role)


@router.post("/resend")
def resend(body: ResendIn, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    u = db.scalar(select(User).where(User.email == email))
    if not u:
        raise HTTPException(404, "邮箱未注册")
    if u.is_verified:
        raise HTTPException(409, "已验证，请直接登录")
    _send_or_500(db, email)
    return {"ok": True}


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    u = db.scalar(select(User).where(User.email == email))
    if not u or not verify_password(body.password, u.password_hash):
        raise HTTPException(401, "邮箱或密码错误")
    if not u.is_verified:
        raise HTTPException(403, "邮箱未验证，请查收验证码")
    return TokenOut(access_token=create_access_token(u.id, u.role), role=u.role)


@router.post("/change-password")
def change_password(body: ChangePasswordIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """修改当前用户密码。

    注意：JWT 为无状态令牌，修改密码后已签发的 token 在过期前仍然有效。
    """
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(400, "旧密码不正确")
    if len(body.new_password) < 6:
        raise HTTPException(400, "新密码至少 6 位")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return {"ok": True}


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user)):
    return MeOut(id=user.id, email=user.email, role=user.role)
