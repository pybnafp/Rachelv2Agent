"""邮件验证码：发送（console/smtp）与签发/校验。

console 后端将 {"email", "code"} 记录到模块级 SENT 列表（测试钩子 + 日志行）。
"""
import hashlib
import logging
import re
import secrets
from datetime import timedelta, timezone

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import EmailCode, utcnow

logger = logging.getLogger(__name__)

# console 后端发送记录：[{"email": ..., "code": ...}, ...]（测试读取验证码用）
SENT: list[dict] = []

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def send_code(email: str, code: str) -> None:
    """发送验证码。console 后端打日志并记录 SENT；smtp 后端 SMTP_SSL 真发信，失败抛异常。"""
    s = get_settings()
    if s.email_backend == "smtp":
        import smtplib
        from email.message import EmailMessage
        msg = EmailMessage()
        msg["Subject"] = "Rachel-v2 验证码"
        msg["From"] = s.smtp_from or s.smtp_user
        msg["To"] = email
        msg.set_content(f"你的验证码是 {code}，{s.code_ttl_min} 分钟内有效。")
        with smtplib.SMTP_SSL(s.smtp_host, s.smtp_port) as server:
            server.login(s.smtp_user, s.smtp_pass)
            server.send_message(msg)
    else:  # console
        SENT.append({"email": email, "code": code})
        logger.info("[email:console] to=%s code=%s", email, code)


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def issue_code(db: Session, email: str) -> str:
    """签发 6 位验证码：sha256 存储；作废该邮箱此前未用码；执行重发冷却。

    冷却期内重发 raise ValueError("发送过于频繁，请稍后再试")。
    """
    s = get_settings()
    latest = db.scalar(
        sa.select(EmailCode).where(EmailCode.email == email)
        .order_by(EmailCode.created_at.desc(), EmailCode.id.desc()).limit(1)
    )
    if latest is not None:
        created = latest.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)  # sqlite 存 naive（UTC）
        if utcnow() - created < timedelta(seconds=s.resend_cooldown_sec):
            raise ValueError("发送过于频繁，请稍后再试")
        # 作废此前所有未用码
        for c in db.scalars(sa.select(EmailCode).where(EmailCode.email == email, EmailCode.used.is_(False))):
            c.used = True
    code = f"{secrets.randbelow(1000000):06d}"
    db.add(EmailCode(email=email, code_hash=_hash(code),
                     expires_at=utcnow() + timedelta(minutes=s.code_ttl_min)))
    db.commit()
    return code


def verify_code(db: Session, email: str, code: str) -> bool:
    """校验验证码：未用/未过期/尝试<5；错则 attempts+1，成功置 used。"""
    c = db.scalar(
        sa.select(EmailCode).where(EmailCode.email == email, EmailCode.used.is_(False))
        .order_by(EmailCode.created_at.desc(), EmailCode.id.desc()).limit(1)
    )
    if c is None:
        return False
    if c.attempts >= 5:
        return False
    exp = c.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)  # sqlite 存 naive（UTC）
    if c.code_hash == _hash(code) and utcnow() <= exp:
        c.used = True
        db.commit()
        return True
    c.attempts += 1
    db.commit()
    return False
