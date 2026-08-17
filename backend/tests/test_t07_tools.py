import json


def test_schema_count_and_shape():
    from app.agent.tools import TOOL_SCHEMAS
    names = {t["function"]["name"] for t in TOOL_SCHEMAS}
    assert len(TOOL_SCHEMAS) == 28          # 26 命令 + read_doc + finish
    expected = {"init","next","context","guide","route_plan","route_sketch",
        "reaction_sites","explore_site","try_action","propose_action",
        "sandbox_list","sandbox_clear","select","commit","accept","review_terminal",
        "skip","tree","status","continuation_status","continuation_abort",
        "finalize","report","export","smart_cap","custom_cap","read_doc","finish"}
    assert names == expected
    for t in TOOL_SCHEMAS:
        assert t["type"] == "function"
        assert t["function"]["description"]
        assert t["function"]["parameters"]["type"] == "object"


def test_required_args_enforced_in_schema():
    from app.agent.tools import TOOL_SCHEMAS
    by = {t["function"]["name"]: t["function"] for t in TOOL_SCHEMAS}
    assert "site_id" in by["explore_site"]["parameters"]["required"]
    assert "action_id" in by["try_action"]["parameters"]["required"]
    assert "target" in by["init"]["parameters"]["required"]
    assert "idx" in by["commit"]["parameters"]["required"]


def test_truncate_small_passthrough():
    from app.agent.tools import truncate_result
    s = truncate_result({"ok": True})
    assert json.loads(s) == {"ok": True}


def test_truncate_large_adds_notice():
    from app.agent.tools import truncate_result
    big = {"blob": "x" * 20000}
    s = truncate_result(big, limit=1000)
    assert len(s) < 1100 and "TRUNCATED" in s


def test_execute_tool_dispatch(tmp_path):
    from app.agent.tools import execute_tool
    from Rachel.main.retro_cmd import RetroCmd
    retro = RetroCmd(str(tmp_path / "session.json"))
    r = execute_tool(retro, "init", {"target": "CC(=O)Nc1ccc(O)cc1", "name": "paracetamol"}, None)
    assert r.get("ok") is True
    r2 = execute_tool(retro, "next", {}, None)
    assert r2.get("action") != "queue_empty" or "smiles" in r2  # 返回了上下文或队列空提示
    r3 = execute_tool(retro, "explore_site", {"site_id": ""}, None)   # 空 site_id → error dict
    assert "error" in r3


def test_execute_tool_finish():
    from app.agent.tools import execute_tool
    r = execute_tool(None, "finish", {"summary": "done"}, None)
    assert r == {"ok": True, "finished": True}
