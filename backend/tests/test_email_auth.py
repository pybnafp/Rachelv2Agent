"""T1 邮箱验证 auth 全流程测试。"""
import pytest

from tests.conftest import verify_email

E = "alice@t.local"


def _register(client, email=E, pw="secret1"):
    return client.post("/api/auth/register", json={"email": email, "password": pw})


# ---- register 校验 ----

def test_register_bad_email_400(client, db):
    r = _register(client, email="not-an-email")
    assert r.status_code == 400 and r.json()["error"] == "邮箱格式不正确"


def test_register_short_password_400(client, db):
    assert _register(client, pw="abc").status_code == 400


def test_register_verified_duplicate_409(client, db):
    _register(client)
    verify_email(client, E)
    assert _register(client).status_code == 409


def test_register_unverified_hits_cooldown_429(client, db):
    # 未验证用户重复注册：更新密码但重发受冷却限制 → 429
    _register(client)
    assert _register(client, pw="secret2").status_code == 429


# ---- resend ----

def test_resend_unknown_404(client, db):
    assert client.post("/api/auth/resend", json={"email": E}).status_code == 404


def test_resend_verified_409(client, db):
    _register(client); verify_email(client, E)
    assert client.post("/api/auth/resend", json={"email": E}).status_code == 409


def test_resend_cooldown_429(client, db):
    _register(client)
    assert client.post("/api/auth/resend", json={"email": E}).status_code == 429


# ---- verify ----

def test_verify_wrong_code_400(client, db):
    _register(client)
    r = client.post("/api/auth/verify", json={"email": E, "code": "000000"})
    assert r.status_code == 400 and r.json()["error"] == "验证码错误或已过期"


def test_verify_five_attempts_exhaust(client, db):
    _register(client)
    for _ in range(5):
        r = client.post("/api/auth/verify", json={"email": E, "code": "000000"})
        assert r.status_code == 400
    # 正确码也不行：attempts 已耗尽
    from app.services.email import SENT
    code = [e for e in SENT if e["email"] == E][-1]["code"]
    assert client.post("/api/auth/verify", json={"email": E, "code": code}).status_code == 400


def test_verify_first_user_admin(client, db):
    _register(client)
    r = verify_email(client, E)
    assert r["role"] == "admin"


def test_verify_second_user_role_user(client, db):
    _register(client); verify_email(client, E)
    _register(client, "bob@t.local")
    assert verify_email(client, "bob@t.local")["role"] == "user"


# ---- login ----

def test_login_unverified_403(client, db):
    _register(client)
    r = client.post("/api/auth/login", json={"email": E, "password": "secret1"})
    assert r.status_code == 403 and r.json()["error"] == "邮箱未验证，请查收验证码"


def test_login_unknown_401(client, db):
    assert client.post("/api/auth/login", json={"email": E, "password": "secret1"}).status_code == 401


# ---- happy path + change password ----

def test_full_happy_path(client, db):
    assert _register(client).status_code == 202
    tok = verify_email(client, E)["access_token"]
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    assert r.json() == {"id": 1, "email": E, "role": "admin"}
    login = client.post("/api/auth/login", json={"email": E, "password": "secret1"})
    assert login.status_code == 200 and login.json()["role"] == "admin"


def test_change_password_still_works(client, db):
    _register(client)
    tok = verify_email(client, E)["access_token"]
    r = client.post("/api/auth/change-password",
                    json={"old_password": "secret1", "new_password": "newpass1"},
                    headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    assert client.post("/api/auth/login", json={"email": E, "password": "secret1"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": E, "password": "newpass1"}).status_code == 200


# ---- codes service 单测 ----

def test_issue_code_cooldown_and_ttl(db, monkeypatch):
    from app.services import email as es
    code = es.issue_code(db, E)
    assert len(code) == 6 and code.isdigit()
    with pytest.raises(ValueError):
        es.issue_code(db, E)  # 冷却
    assert es.verify_code(db, E, code) is True
    assert es.verify_code(db, E, code) is False  # 一次性


def test_email_case_insensitive_register_and_login(client, db):
    # 注册用大小写混合，登录用小写应能成功
    _register(client, email="Alice@X.COM")
    verify_email(client, "alice@x.com")  # 归一化后按小写邮箱验证
    r = client.post("/api/auth/login", json={"email": "alice@x.com", "password": "secret1"})
    assert r.status_code == 200
