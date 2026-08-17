import shutil
from pathlib import Path

FIXT = Path("examples/result_demo/export")
PARA = "CC(=O)Nc1ccc(O)cc1"


def test_audit_offline_produces_local_results(tmp_path):
    # 复制 fixture 到 tmp（审计会写 terminal_audit.json，不能污染 examples/）
    dst = tmp_path / "export"
    shutil.copytree(FIXT, dst)
    from app.services.terminal_audit import run_terminal_audit
    payload = run_terminal_audit(dst, offline=True)
    assert payload["available"] is True and payload["offline"] is True
    assert len(payload["results"]) == 6                       # demo terminals 数
    r0 = payload["results"][0]
    assert "pubchem_metrics" in r0 and "buyability_decision" in r0
    assert (dst / "terminal_audit.json").exists()
    # 幂等：重跑覆盖
    payload2 = run_terminal_audit(dst, offline=True)
    assert payload2["available"] is True


def test_audit_missing_terminals_degrades(tmp_path):
    from app.services.terminal_audit import run_terminal_audit
    payload = run_terminal_audit(tmp_path, offline=True)
    assert payload["available"] is False and "terminals" in payload["error"]


def test_audit_exception_never_raises(tmp_path, monkeypatch):
    import app.services.terminal_audit as ta
    monkeypatch.setattr(ta, "load_terminal_records",
                        lambda p: (_ for _ in ()).throw(RuntimeError("boom")))
    payload = ta.run_terminal_audit(tmp_path, offline=True)
    assert payload["available"] is False and "boom" in payload["error"]


def test_worker_runs_audit_after_export_and_degrades(client, db, auth_headers_user, monkeypatch, tmp_path):
    # mock driver：init + finish → 立即 finalize+export。init 后的会话导出 terminals.json
    # 仅含目标本身 → 审计离线跑通（available=True、1 条结果）；缺 terminals.json 的降级
    # 路径由 test_audit_missing_terminals_degrades 覆盖。此处验证端到端 wiring。
    from app.db.models import LlmProvider
    from sqlalchemy import select
    p = db.scalar(select(LlmProvider)); p.model = "mock"; db.commit()
    from app.agent.llm_client import ToolCall, MockLLMClient
    import app.api.admin as admin
    monkeypatch.setattr(admin, "get_active_client",
                        lambda db: MockLLMClient(script=[
                            [ToolCall("c1", "init", {"target": PARA})],
                            [ToolCall("c2", "finish", {"summary": "mock route"})]]))
    r = client.post("/api/jobs", headers=auth_headers_user,
                    json={"smiles": PARA, "name": "m3"})
    jid = r.json()["id"]
    stats = client.get(f"/api/jobs/{jid}", headers=auth_headers_user).json()["stats"]
    assert "terminal_audit_summary" in stats
    body = client.get(f"/api/jobs/{jid}/result", headers=auth_headers_user).json()
    ta = body["terminal_audit"]
    assert ta["available"] is True and ta["offline"] is True
    assert len(ta["results"]) == 1            # init-only 会话：目标即唯一终点
    assert "summary" in ta
    assert (tmp_path / jid / "export" / "terminal_audit.json").exists()


def test_parse_export_includes_terminal_audit(tmp_path):
    from app.services.artifacts import parse_export
    shutil.copytree(FIXT, tmp_path / "export")
    from app.services.terminal_audit import run_terminal_audit
    run_terminal_audit(tmp_path / "export", offline=True)
    out = parse_export(tmp_path / "export")
    assert out.get("terminal_audit", {}).get("available") is True
    # 缺审计文件不改变 incomplete 判定（terminal_audit 可缺省）
    out2 = parse_export(FIXT)
    assert "terminal_audit" not in out2 and out2["incomplete"] is False
