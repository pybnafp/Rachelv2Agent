from app.agent.driver import AgentDriver, DriverLimits
from tests.fakes import FakeRetroCmd, ListTrace, mock, ToolCall  # noqa: F401


def _driver(script, retro=None, limits=None):
    retro = retro or FakeRetroCmd()
    trace = ListTrace()
    d = AgentDriver(retro=retro, llm=mock(script), trace=trace, limits=limits,
                    task_prompt="target: CCO", name="t")
    return d, retro, trace


def test_finish_triggers_finalize_export():
    d, retro, trace = _driver([[("next", {})], [("finish", {"summary": "done"})]])
    r = d.run()
    assert r.status == "succeeded" and retro.finalized and retro.exported
    assert retro.calls[-2][0] == "finalize" and retro.calls[-1][0] == "export"
    assert r.steps == 2


def test_max_steps_partial_rescue():
    script = [[("status", {})] for _ in range(5)]
    d, retro, trace = _driver(script, limits=DriverLimits(max_steps=3, wall_clock_sec=600, keep_recent=10))
    r = d.run()
    assert r.status == "partial" and "max_steps" in r.reason
    assert retro.finalized and retro.exported      # 抢救导出


def test_circuit_breaker_on_repeated_errors():
    retro = FakeRetroCmd(error_commands={"try_action"})
    script = [[("try_action", {"action_id": "a"})] for _ in range(12)]
    d, _, _ = _driver(script, retro=retro)
    r = d.run()
    assert r.status == "failed" and "try_action" in r.reason


def test_compaction_replaces_old_tool_results():
    script = [[("next", {})] for _ in range(15)] + [[("finish", {"summary": "x"})]]
    d, retro, trace = _driver(script, limits=DriverLimits(max_steps=100, wall_clock_sec=600, keep_recent=5))
    r = d.run()
    msgs = d.messages
    tool_msgs = [m for m in msgs if m["role"] == "tool"]
    full = [m for m in tool_msgs if "echo" in m["content"]]
    summarized = [m for m in tool_msgs if m["content"].startswith("step ")]
    assert len(full) <= 6 and len(summarized) >= 9    # 旧结果被摘要替换


def test_text_only_reply_nudge_then_fail():
    from app.agent.llm_client import ChatTurn as CT

    class TextOnly:
        def __init__(self):
            self.n = 0

        def chat(self, messages, tools):
            self.n += 1
            return CT(content="I think we should...", tool_calls=[], usage=None)

    retro = FakeRetroCmd(); trace = ListTrace()
    d = AgentDriver(retro=retro, llm=TextOnly(), trace=trace, task_prompt="t", name="t")
    r = d.run()
    assert r.status == "failed" and "no tool calls" in r.reason


def test_messages_jsonl_written(tmp_path):
    d, retro, trace = _driver([[("finish", {"summary": "x"})]])
    d.workspace = tmp_path
    r = d.run()
    assert (tmp_path / "messages.jsonl").exists()
