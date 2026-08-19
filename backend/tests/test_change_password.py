import pytest
from tests.conftest import verify_email


@pytest.fixture
def user_headers(client, db):
    client.post("/api/auth/register", json={"email": "alice@t.local", "password": "secret1"})
    tok = verify_email(client, "alice@t.local")["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def test_change_password_requires_auth(client, db):
    r = client.post("/api/auth/change-password", json={"old_password": "a", "new_password": "b"})
    assert r.status_code == 401


def test_change_password_wrong_old(client, db, user_headers):
    r = client.post(
        "/api/auth/change-password",
        json={"old_password": "bad", "new_password": "newpass"},
        headers=user_headers,
    )
    assert r.status_code == 400
    assert r.json()["error"] == "旧密码不正确"


def test_change_password_short_new(client, db, user_headers):
    r = client.post(
        "/api/auth/change-password",
        json={"old_password": "secret1", "new_password": "abc"},
        headers=user_headers,
    )
    assert r.status_code == 400
    assert r.json()["error"] == "新密码至少 6 位"


def test_change_password_success(client, db, user_headers):
    r = client.post(
        "/api/auth/change-password",
        json={"old_password": "secret1", "new_password": "newpass1"},
        headers=user_headers,
    )
    assert r.status_code == 200 and r.json() == {"ok": True}
    # 旧密码失效
    assert client.post("/api/auth/login", json={"email": "alice@t.local", "password": "secret1"}).status_code == 401
    # 新密码可登录并返回 token
    tok = client.post("/api/auth/login", json={"email": "alice@t.local", "password": "newpass1"}).json()["access_token"]
    assert tok
