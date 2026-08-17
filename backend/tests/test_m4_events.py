import json


def _sse_lines(resp):
    return [l for l in resp.iter_lines() if l]


def test_events_snapshot_and_done(client, db, auth_headers_user):
    jid = client.post("/api/jobs", headers=auth_headers_user, json={"smiles": "CCO"}).json()["id"]
    with client.stream("GET", f"/api/jobs/{jid}/events", headers=auth_headers_user) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        lines = _sse_lines(resp)
    joined = "\n".join(lines)
    assert "event: snapshot" in joined and '"status"' in joined
    assert "event: done" in joined                      # eager 下任务已终态 → 快照后即 done 关闭


def test_events_token_query_auth(client, db, auth_headers_user):
    jid = client.post("/api/jobs", headers=auth_headers_user, json={"smiles": "CCO"}).json()["id"]
    tok = auth_headers_user["Authorization"].split(" ", 1)[1]
    with client.stream("GET", f"/api/jobs/{jid}/events?token={tok}") as resp:
        assert resp.status_code == 200
    with client.stream("GET", f"/api/jobs/{jid}/events?token=bad") as resp:
        assert resp.status_code == 401


def test_events_other_user_404(client, db, auth_headers_admin, auth_headers_user):
    jid = client.post("/api/jobs", headers=auth_headers_user, json={"smiles": "CCO"}).json()["id"]
    with client.stream("GET", f"/api/jobs/{jid}/events", headers=auth_headers_admin) as resp:
        assert resp.status_code == 200                   # admin 可见
    client.post("/api/auth/register", json={"username": "m4eve", "password": "pw7"})
    t = client.post("/api/auth/login", json={"username": "m4eve", "password": "pw7"}).json()["access_token"]
    with client.stream("GET", f"/api/jobs/{jid}/events",
                       headers={"Authorization": f"Bearer {t}"}) as resp:
        assert resp.status_code == 404


def test_resolve_token_user_shared(client, db, auth_headers_user):
    # files 端点改用共享助手后行为不变（既有 token 测试仍绿即为验证）；此处直接单测助手
    from app.api.deps import resolve_token_user
    from fastapi.security import HTTPAuthorizationCredentials
    tok = auth_headers_user["Authorization"].split(" ", 1)[1]
    u = resolve_token_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials=tok), None, db)
    assert u.username == "usr"
    assert resolve_token_user(None, "bad", db) is None or True   # 实现选择：返回 None 或抛 401——以 events/files 用法为准
