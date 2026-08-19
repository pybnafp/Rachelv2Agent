from tests.conftest import verify_email
PARACETAMOL = "CC(=O)Nc1ccc(O)cc1"


def test_submit_invalid_smiles_400(client, db, auth_headers_user):
    r = client.post("/api/jobs", headers=auth_headers_user, json={"smiles": "not-a-smiles"})
    assert r.status_code == 400 and "error" in r.json()


def test_submit_canonicalized(client, db, auth_headers_user):
    r = client.post("/api/jobs", headers=auth_headers_user, json={"smiles": "C1=CC=CC=C1"})  # 非规范苯
    assert r.status_code == 201
    assert r.json()["smiles"] == "c1ccccc1"     # RDKit 规范化
    assert r.json()["status"] in ("queued", "succeeded", "failed")  # eager: T9 前无 driver → failed


def test_submit_too_heavy_400(client, db, auth_headers_user, monkeypatch):
    from app.core.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setenv("MAX_HEAVY_ATOMS", "5")
    r = client.post("/api/jobs", headers=auth_headers_user, json={"smiles": PARACETAMOL})
    assert r.status_code == 400
    get_settings.cache_clear()


def test_list_shows_only_own(client, db, auth_headers_admin, auth_headers_user):
    client.post("/api/jobs", headers=auth_headers_user, json={"smiles": PARACETAMOL})
    mine = client.get("/api/jobs?mine=1", headers=auth_headers_user).json()
    assert len(mine) == 1
    other = client.get("/api/jobs?mine=1", headers=auth_headers_admin).json()
    assert len(other) == 0


def test_detail_of_other_user_404(client, db, auth_headers_admin, auth_headers_user):
    jid = client.post("/api/jobs", headers=auth_headers_user, json={"smiles": PARACETAMOL}).json()["id"]
    assert client.get(f"/api/jobs/{jid}", headers=auth_headers_admin).status_code in (200, 404)
    assert client.get(f"/api/jobs/{jid}", headers=auth_headers_admin).status_code == 200  # admin 可见
    # 第三个无关用户不可见
    client.post("/api/auth/register", json={"email": "eve@t.local", "password": "evepass3"})
    tok = verify_email(client, "eve@t.local")["access_token"]
    assert client.get(f"/api/jobs/{jid}", headers={"Authorization": f"Bearer {tok}"}).status_code == 404


def test_running_quota_429(client, db, auth_headers_user, monkeypatch):
    from app.core.config import get_settings
    get_settings.cache_clear(); monkeypatch.setenv("MAX_RUNNING_PER_USER", "1")
    assert client.post("/api/jobs", headers=auth_headers_user, json={"smiles": PARACETAMOL}).status_code == 201
    # stub 会立即 succeeded，为测配额先手工塞一条 running
    from app.db.models import Job
    d = client.app.state.test_db
    u = d.query(Job).first().user_id
    d.add(Job(id="manual1", user_id=u, smiles="CCO", status="running")); d.commit()
    assert client.post("/api/jobs", headers=auth_headers_user, json={"smiles": "CCOc1ccccc1"}).status_code == 429
    get_settings.cache_clear()


def _submit_job_with_steps(client, db, auth_headers_user, monkeypatch):
    """eager 模式跑一个带 job_steps 的任务（M2 同款 mock provider 注入）。"""
    from app.api.admin import seed_default_provider
    from app.agent.llm_client import MockLLMClient, ToolCall
    import app.api.admin as admin
    seed_default_provider(db)
    monkeypatch.setattr(admin, "get_active_client",
                        lambda db: MockLLMClient(script=[[ToolCall("c1", "init", {"target": PARACETAMOL})],
                                                         [ToolCall("c2", "finish", {"summary": "mock"})]]))
    return client.post("/api/jobs", headers=auth_headers_user,
                       json={"smiles": PARACETAMOL, "name": "fk"}).json()["id"]


def test_delete_job_with_steps(client, db, auth_headers_user, monkeypatch):
    # 生产 bug 复现：PostgreSQL 上 job_steps_job_id_fkey 违反 → 500。
    # sqlite 外键现已强制开启（make_engine PRAGMA），本测试在修复前应失败。
    from sqlalchemy import func, select
    from app.db.models import Job, JobStep
    jid = _submit_job_with_steps(client, db, auth_headers_user, monkeypatch)
    assert db.scalar(select(func.count()).select_from(JobStep).where(JobStep.job_id == jid)) > 0
    r = client.delete(f"/api/jobs/{jid}", headers=auth_headers_user)
    assert r.status_code == 200
    assert db.get(Job, jid) is None
    assert db.scalar(select(func.count()).select_from(JobStep).where(JobStep.job_id == jid)) == 0
