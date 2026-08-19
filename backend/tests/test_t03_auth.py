"""邮箱验证体系下的基础 auth 行为（详细覆盖见 test_email_auth.py）。"""
from tests.conftest import verify_email


def test_register_returns_202_and_sends_code(client, db):
    r = client.post("/api/auth/register", json={"email": "alice@t.local", "password": "secret1"})
    assert r.status_code == 202 and r.json()["ok"] is True


def test_login_wrong_password_401(client, db):
    client.post("/api/auth/register", json={"email": "alice@t.local", "password": "secret1"})
    verify_email(client, "alice@t.local")
    assert client.post("/api/auth/login", json={"email": "alice@t.local", "password": "bad"}).status_code == 401


def test_me_requires_token(client, db):
    assert client.get("/api/auth/me").status_code == 401


def test_me_roundtrip(client, db):
    client.post("/api/auth/register", json={"email": "alice@t.local", "password": "secret1"})
    tok = verify_email(client, "alice@t.local")["access_token"]
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200 and r.json()["email"] == "alice@t.local"
