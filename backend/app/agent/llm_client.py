import json
from dataclasses import dataclass, field
from openai import OpenAI


@dataclass
class ToolCall:
    id: str; name: str; args: dict = field(default_factory=dict)


@dataclass
class Usage:
    prompt_tokens: int = 0; completion_tokens: int = 0


@dataclass
class ChatTurn:
    content: str = ""; tool_calls: list = field(default_factory=list); usage: Usage = field(default_factory=Usage)
    finish_reason: str = ""


class OpenAICompatClient:
    def __init__(self, base_url, api_key, model, temperature=0.2, max_output=4096):
        self._cli = OpenAI(base_url=base_url, api_key=api_key)
        self.model, self.temperature, self.max_output = model, temperature, max_output
        # Real OpenAI SDK: chat.completions.create; some test doubles expose chat.completions_create
        self._create = getattr(self._cli.chat, "completions_create", None) or self._cli.chat.completions.create

    def chat(self, messages, tools):
        resp = self._create(
            model=self.model, messages=messages, tools=tools,
            temperature=self.temperature, max_tokens=self.max_output)
        msg = resp.choices[0].message
        calls = []
        for tc in (msg.tool_calls or []):
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {"_raw": tc.function.arguments}
            calls.append(ToolCall(id=tc.id, name=tc.function.name, args=args))
        u = getattr(resp, "usage", None)
        usage = Usage(u.prompt_tokens if u else 0, u.completion_tokens if u else 0)
        finish_reason = getattr(resp.choices[0], "finish_reason", "") or ""
        return ChatTurn(content=msg.content or "", tool_calls=calls, usage=usage,
                        finish_reason=finish_reason)


class MockLLMClient:
    """按脚本回放 tool_calls，用于测试与无 LLM 环境。"""
    def __init__(self, script: list[list[ToolCall]]):
        self.script = list(script); self.calls = 0
        self.usage = Usage()

    def chat(self, messages, tools):
        if self.calls >= len(self.script):
            raise RuntimeError("MockLLMClient script exhausted")
        turns = self.script[self.calls]; self.calls += 1
        return ChatTurn(tool_calls=turns)
