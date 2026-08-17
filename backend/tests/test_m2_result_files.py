"""M2-T1: GET /api/jobs/{id}/result + driver export into workspace; M2-T2: /files."""

PARA = "CC(=O)Nc1ccc(O)cc1"


# ── T1: driver export 落位 ──

def test_driver_exports_into_workspace(tmp_path):
    from tests.fakes import FakeRetroCmd, ListTrace
    from app.agent.llm_client import ToolCall, MockLLMClient
    from app.agent.driver import AgentDriver
    retro = FakeRetroCmd()
    d = AgentDriver(retro=retro, llm=MockLLMClient(script=[[ToolCall("c1", "finish", {"summary": "x"})]]),
                    trace=ListTrace(), task_prompt="t", name="n", workspace=tmp_path)
    d.run()
    export_args = [a for c, a in retro.calls if c == "export"][0]
    assert export_args["output_dir"] == str(tmp_path / "export")


# ── T1: /result ──

def test_result_aggregates_artifacts(client, db, auth_headers_user, tmp_path, monkeypatch):
    from pathlib import Path
    from app.api.admin import seed_default_provider
    from app.db.models import LlmProvider
    from sqlalchemy import select
    seed_default_provider(db)  # 测试库为空库，需先种一个 provider
    # mock 默认脚本无 init → RetroCmd 无 session.json → export 失败、stats 无 export_dir。
    # 注入 init+finish（同 T11 模式），让真实 export 写入 workspace/export（验证 driver 落位），
    # 随后用 demo fixture 覆盖，断言 /result 聚合。
    from app.agent.llm_client import MockLLMClient, ToolCall
    import app.api.admin as admin
    monkeypatch.setattr(admin, "get_active_client",
                        lambda db: MockLLMClient(script=[[ToolCall("c1", "init", {"target": PARA})],
                                                         [ToolCall("c2", "finish", {"summary": "mock"})]]))
    jid = client.post("/api/jobs", headers=auth_headers_user,
                      json={"smiles": PARA, "name": "para"}).json()["id"]
    export = tmp_path / jid / "export"
    assert export.is_dir()  # driver 已把 export 导到 workspace/export
    src = Path("examples/result_demo/export")
    for f in ("visualization.json", "terminals.json"):
        (export / f).write_text((src / f).read_text(encoding="utf-8"), encoding="utf-8")
    r = client.get(f"/api/jobs/{jid}/result", headers=auth_headers_user)
    assert r.status_code == 200
    body = r.json()
    assert body["job"]["id"] == jid
    assert len(body["visualization"]["nodes"]) == 28          # demo fixture 真实规模
    assert body["metrics"]["n_nodes"] == 28
    assert "terminals" in body


def test_result_degrades_without_artifacts(client, db, auth_headers_user):
    from app.db.models import Job, User
    u = db.query(User).filter_by(username="usr").first()  # 请求方用户（first() 是 admin）
    db.add(Job(id="jx", user_id=u.id, smiles="CCO", status="running")); db.commit()
    r = client.get("/api/jobs/jx/result", headers=auth_headers_user)
    assert r.status_code == 200 and r.json()["job"]["id"] == "jx"
    assert "visualization" not in r.json()


def test_result_other_user_404(client, db, auth_headers_admin, auth_headers_user):
    jid = client.post("/api/jobs", headers=auth_headers_user, json={"smiles": "CCO"}).json()["id"]
    client.post("/api/auth/register", json={"username": "m2eve", "password": "pw9"})
    tok = client.post("/api/auth/login", json={"username": "m2eve", "password": "pw9"}).json()["access_token"]
    assert client.get(f"/api/jobs/{jid}/result",
                      headers={"Authorization": f"Bearer {tok}"}).status_code == 404


# ── T2: /files ──

def test_files_serves_and_blocks_traversal(client, db, auth_headers_user, tmp_path):
    # data_dir 由 conftest autouse fixture（property 方式）指向 tmp_path；
    # 简单 setattr 会被 pydantic 实例 __dict__ 遮蔽，反而失效。
    jid = client.post("/api/jobs", headers=auth_headers_user, json={"smiles": "CCO"}).json()["id"]
    ws = tmp_path / jid; ws.mkdir(parents=True, exist_ok=True)
    (ws / "messages.jsonl").write_text('{"a":1}\n', encoding="utf-8")
    exp = ws / "export"; exp.mkdir(); (exp / "SYNTHESIS_REPORT.html").write_text("<html>r</html>", encoding="utf-8")
    ok1 = client.get(f"/api/jobs/{jid}/files/messages.jsonl", headers=auth_headers_user)
    assert ok1.status_code == 200 and ok1.headers["content-type"].startswith(("text/plain", "application/json"))  # .jsonl → json
    ok2 = client.get(f"/api/jobs/{jid}/files/export/SYNTHESIS_REPORT.html", headers=auth_headers_user)
    assert ok2.status_code == 200 and "text/html" in ok2.headers["content-type"]
    bad = client.get(f"/api/jobs/{jid}/files/../../etc/passwd", headers=auth_headers_user)
    assert bad.status_code in (404, 400)
    other = client.get(f"/api/jobs/{jid}/files/nope.bin", headers=auth_headers_user)
    assert other.status_code == 404
