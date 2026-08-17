def test_admin_list_requires_admin(client, db, auth_headers_user):
    assert client.get("/api/admin/llm-providers", headers=auth_headers_user).status_code == 403

def test_admin_crud_and_switch(client, db, auth_headers_admin):
    r = client.get("/api/admin/llm-providers", headers=auth_headers_admin)
    assert r.status_code == 200 and len(r.json()) >= 1   # seed 行存在
    deepseek = next(p for p in r.json() if p["name"] == "deepseek")
    assert deepseek["is_active"] is True and deepseek["model"] == "deepseek-v4-pro"
    # 新增并切换 active
    r = client.put("/api/admin/llm-providers", headers=auth_headers_admin, json={
        "name": "glm", "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "api_key": "k2", "model": "glm-4.7", "is_active": True})
    pid = r.json()["id"]
    rows = client.get("/api/admin/llm-providers", headers=auth_headers_admin).json()
    assert next(p for p in rows if p["id"] == pid)["is_active"] is True
    assert next(p for p in rows if p["name"] == "deepseek")["is_active"] is False
    assert "api_key" not in rows[0]  # 响应不回显 key

def test_mock_llm_client_replays_script():
    from app.agent.llm_client import MockLLMClient, ToolCall
    mock = MockLLMClient(script=[[ToolCall("c1", "next", {})], [ToolCall("c2", "finish", {"summary": "done"})]])
    t1 = mock.chat([], [])
    assert t1.tool_calls[0].name == "next"
    t2 = mock.chat([], [])
    assert t2.tool_calls[0].name == "finish"

def test_openai_client_maps_tool_calls(monkeypatch):
    from app.agent import llm_client as lc
    class FakeResp:
        choices = [type("M", (), {"message": type("Msg", (), {"content": "", "tool_calls": [
            type("TC", (), {"id": "c1", "function": type("F", (), {"name": "next", "arguments": "{}"})})]}),
            "finish_reason": "tool_calls"})()]
        usage = type("U", (), {"prompt_tokens": 10, "completion_tokens": 5})
    captured = {}
    class FakeOpenAI:
        def __init__(self, **kw): pass
        class chat:
            @staticmethod
            def completions_create(**kw): captured.update(kw); return FakeResp()
    monkeypatch.setattr(lc, "OpenAI", FakeOpenAI)
    c = lc.OpenAICompatClient("http://x", "k", "m1")
    turn = c.chat([{"role": "user", "content": "hi"}], [{"type": "function", "function": {"name": "next"}}])
    assert turn.tool_calls[0].name == "next" and turn.usage.prompt_tokens == 10
    assert captured["model"] == "m1" and captured["tools"][0]["function"]["name"] == "next"
