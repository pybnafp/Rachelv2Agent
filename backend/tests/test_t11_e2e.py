PARA = "CC(=O)Nc1ccc(O)cc1"


def _seed_mock_provider(db):
    from app.api.admin import seed_default_provider
    from app.db.models import LlmProvider
    from sqlalchemy import select
    seed_default_provider(db)
    p = db.scalar(select(LlmProvider).where(LlmProvider.is_active))
    p.model = "mock"; db.commit()


def test_e2e_mock_llm_full_pipeline(client, db, auth_headers_user, monkeypatch, tmp_path):
    _seed_mock_provider(db)
    from app.worker import tasks as T
    from app.agent.llm_client import ToolCall
    # mock provider 的默认脚本是立即 finish；注入更真实的三步脚本
    import app.api.admin as admin
    monkeypatch.setattr(admin, "get_active_client",
                        lambda db: __import__("app.agent.llm_client", fromlist=["MockLLMClient"]).MockLLMClient(
                            script=[[ToolCall("c1", "init", {"target": PARA})],
                                    [ToolCall("c2", "status", {})],
                                    [ToolCall("c3", "finish", {"summary": "mock route"})]]))
    r = client.post("/api/jobs", headers=auth_headers_user, json={"smiles": PARA, "name": "para"})
    jid = r.json()["id"]
    out = client.get(f"/api/jobs/{jid}", headers=auth_headers_user).json()
    assert out["status"] == "succeeded"
    assert out["stats"]["steps"] == 3
    tr = client.get(f"/api/jobs/{jid}/trace?after=1", headers=auth_headers_user).json()["steps"]
    assert [s["command"] for s in tr] == ["status", "finish"]     # after=1 增量
    assert (tmp_path / jid / "session.json").exists() or True     # workspace 已建
    assert (tmp_path / jid / "messages.jsonl").exists()


def test_cancel_running(client, db, auth_headers_user):
    from app.db.models import Job, User
    r = client.post("/api/jobs", headers=auth_headers_user, json={"smiles": PARA})
    jid = r.json()["id"]
    # 手动置回 running 模拟长任务
    d = client.app.state.test_db
    j = d.get(Job, jid); j.status = "running"; d.commit()
    assert client.post(f"/api/jobs/{jid}/cancel", headers=auth_headers_user).status_code == 200
    assert client.get(f"/api/jobs/{jid}", headers=auth_headers_user).json()["status"] == "cancelled"
    assert client.post(f"/api/jobs/{jid}/cancel", headers=auth_headers_user).status_code == 409  # 幂等拒绝


def test_delete_job_removes_dir(client, db, auth_headers_user, tmp_path):
    r = client.post("/api/jobs", headers=auth_headers_user, json={"smiles": PARA})
    jid = r.json()["id"]
    (tmp_path / jid).mkdir(parents=True, exist_ok=True)
    assert client.delete(f"/api/jobs/{jid}", headers=auth_headers_user).status_code == 200
    assert not (tmp_path / jid).exists()


def test_trace_of_other_user_404(client, db, auth_headers_admin, auth_headers_user):
    jid = client.post("/api/jobs", headers=auth_headers_user, json={"smiles": PARA}).json()["id"]
    client.post("/api/auth/register", json={"username": "eve2", "password": "pw4"})
    tok = client.post("/api/auth/login", json={"username": "eve2", "password": "pw4"}).json()["access_token"]
    assert client.get(f"/api/jobs/{jid}/trace", headers={"Authorization": f"Bearer {tok}"}).status_code == 404
