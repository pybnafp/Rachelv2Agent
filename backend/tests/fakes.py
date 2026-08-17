from app.agent.llm_client import ChatTurn, ToolCall, Usage  # noqa: F401


class FakeRetroCmd:
    def __init__(self, error_commands: set[str] | None = None):
        self.calls: list[tuple[str, dict]] = []
        self.error_commands = error_commands or set()
        self.finalized = False
        self.exported = False

    def execute(self, command: str, args: dict | None = None) -> dict:
        args = args or {}
        self.calls.append((command, args))
        if command == "finalize":
            self.finalized = True
            return {"ok": True}
        if command == "export":
            self.exported = True
            return {"output_dir": "/tmp/fake_export", "files": [], "summary": "ok"}
        if command in self.error_commands:
            return {"error": f"boom:{command}"}
        return {"ok": True, "echo": command}


class ListTrace:
    def __init__(self):
        self.rows = []

    def record(self, seq, command, args, result, tokens, duration_ms):
        self.rows.append({"seq": seq, "command": command, "args": args,
                          "result": result, "tokens": tokens,
                          "duration_ms": duration_ms})


def turns(*groups) -> list[list[ToolCall]]:
    """turns([('next', {}), ...], [('finish', {...})]) -> one ToolCall group per chat."""
    out = []
    for g in groups:
        out.append([ToolCall(id=f"call{i}", name=n, args=a)
                    for i, (n, a) in enumerate(
                        (x[0], x[1]) if isinstance(x[1], dict) else (x[0], {})
                        for x in g)])
    return out


def _as_calls(group):
    return [c if isinstance(c, ToolCall) else ToolCall(id=f"call{i}", name=c[0],
                                                       args=c[1] if len(c) > 1 and isinstance(c[1], dict) else {})
            for i, c in enumerate(group)]


def mock(script):
    """MockLLMClient whose script groups may be tuples (name, args) or ToolCall."""
    from app.agent.llm_client import MockLLMClient
    return MockLLMClient([_as_calls(g) for g in script])
