"""Fix B (text-only turn evidence) and Fix C (job error surfacing)."""
import json

from tests.fakes import FakeRetroCmd, ListTrace


class _TruncLLM:
    """Always returns cut-off text-only turns (finish_reason=length)."""
    def __init__(self, content="thinking about the route...", finish_reason="length"):
        self.content, self.finish_reason = content, finish_reason

    def chat(self, messages, tools):
        from app.agent.llm_client import ChatTurn
        return ChatTurn(content=self.content, tool_calls=[],
                        usage=None, finish_reason=self.finish_reason)


def _run_trunc(tmp_path):
    from app.agent.driver import AgentDriver
    d = AgentDriver(retro=FakeRetroCmd(), llm=_TruncLLM(), trace=ListTrace(),
                    task_prompt="t", name="t", workspace=tmp_path)
    return d.run(), d


def test_text_only_length_strikes_logged(tmp_path):
    result, d = _run_trunc(tmp_path)
    assert result.status == "failed" and "no tool calls" in result.reason
    records = [json.loads(l) for l in
               (tmp_path / "messages.jsonl").read_text(encoding="utf-8").splitlines()]
    text_only = [r for r in records if r.get("kind") == "text_only"]
    assert len(text_only) == 2
    assert all(r["finish_reason"] == "length" for r in text_only)
    assert [r["strike"] for r in text_only] == [1, 2]
    assert text_only[0]["content"].startswith("thinking")


def test_length_nudge_mentions_cut_off(tmp_path):
    _, d = _run_trunc(tmp_path)
    user_msgs = [m for m in d.messages if m["role"] == "user"]
    assert "cut off" in user_msgs[-1]["content"]


def test_openai_client_maps_finish_reason(monkeypatch):
    from app.agent import llm_client as lc
    class FakeResp:
        choices = [type("M", (), {"message": type("Msg", (), {"content": "", "tool_calls": []}),
                                  "finish_reason": "stop"})]
        usage = type("U", (), {"prompt_tokens": 1, "completion_tokens": 1})
    class FakeOpenAI:
        def __init__(self, **kw): pass
        class chat:
            @staticmethod
            def completions_create(**kw): return FakeResp()
    monkeypatch.setattr(lc, "OpenAI", FakeOpenAI)
    turn = lc.OpenAICompatClient("http://x", "k", "m").chat([], [])
    assert turn.finish_reason == "stop"


PARA = "CC(=O)Nc1ccc(O)cc1"


def test_failed_driver_reason_surfaced_in_error(client, db, auth_headers_user, monkeypatch):
    from app.agent.driver import DriverResult
    from app.worker import tasks as T
    monkeypatch.setattr(T, "_build_driver",
                        lambda job, ws: type("D", (), {"run": lambda self: DriverResult(
                            status="failed", reason="no tool calls in two consecutive turns")})())
    jid = client.post("/api/jobs", headers=auth_headers_user,
                      json={"smiles": PARA, "name": "p"}).json()["id"]
    out = client.get(f"/api/jobs/{jid}", headers=auth_headers_user).json()
    assert out["status"] == "failed"
    assert out["error"] == "no tool calls in two consecutive turns"
