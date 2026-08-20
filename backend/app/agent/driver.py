import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from app.agent.llm_client import Usage
from app.agent.prompts import DocReader, build_system_prompt
from app.agent.tools import TOOL_SCHEMAS, execute_tool, truncate_result


@dataclass
class DriverLimits:
    max_steps: int = 300
    wall_clock_sec: int = 3600
    keep_recent: int = 10


@dataclass
class DriverResult:
    status: str; reason: str = ""
    steps: int = 0; tokens_in: int = 0; tokens_out: int = 0
    export_result: dict = field(default_factory=dict)


class AgentDriver:
    def __init__(self, retro, llm, trace, task_prompt: str, name: str = "",
                 limits: DriverLimits | None = None, workspace: Path | None = None,
                 doc_reader: DocReader | None = None):
        self.retro, self.llm, self.trace = retro, llm, trace
        self.limits = limits or DriverLimits()
        self.workspace = workspace
        self.doc_reader = doc_reader or DocReader()
        self.name = name
        self.messages = [
            {"role": "system", "content": build_system_prompt()},
            {"role": "user", "content": task_prompt},
        ]
        self._seq = 0
        self._finalized = False
        self._finish_summary = ""  # LLM 在 finish 工具里给出的路线总结（用于自动 finalize）
        self._llm_consecutive_errors = 0
        self._consecutive_errors: dict[str, int] = {}

    def run(self) -> DriverResult:
        t0 = time.monotonic()
        usage_total = Usage()
        text_only_strikes = 0
        while True:
            if self._seq >= self.limits.max_steps:
                return self._finish("partial", f"max_steps={self.limits.max_steps} reached",
                                    usage_total, "max_steps")
            if time.monotonic() - t0 > self.limits.wall_clock_sec:
                return self._finish("partial", "wall clock limit reached", usage_total, "wall_clock")
            try:
                turn = self.llm.chat(self._wire_messages(), TOOL_SCHEMAS)
            except Exception as e:
                self._llm_consecutive_errors += 1
                if self._llm_consecutive_errors >= 5:  # spec §3.6: 5 consecutive failures
                    return self._finish("failed", f"llm error: {e}", usage_total, "llm_error")
                continue  # transient: retry same call
            self._llm_consecutive_errors = 0
            u = getattr(turn, "usage", None)
            if u is not None:
                usage_total.prompt_tokens += getattr(u, "prompt_tokens", 0)
                usage_total.completion_tokens += getattr(u, "completion_tokens", 0)
            if not turn.tool_calls:
                text_only_strikes += 1
                self._log_json({"kind": "text_only", "strike": text_only_strikes,
                                "finish_reason": getattr(turn, "finish_reason", ""),
                                "content": (turn.content or "")[:4000]})
                if text_only_strikes >= 2:
                    return self._finish("failed", "no tool calls in two consecutive turns",
                                        usage_total, "no_tool_calls")
                self.messages.append({"role": "assistant", "content": turn.content or ""})
                if getattr(turn, "finish_reason", "") == "length":
                    nudge = ("Your previous reply was cut off by the output token limit before any "
                             "tool call was emitted. Be concise and call a tool now (short reasoning, "
                             "then the tool call).")
                else:
                    nudge = ("Continue by calling one of the tools. "
                             "When the route is complete, call finish.")
                self.messages.append({"role": "user", "content": nudge})
                continue
            text_only_strikes = 0
            self.messages.append({"role": "assistant", "content": turn.content or "",
                                  "tool_calls": [{"id": c.id, "type": "function",
                                                  "function": {"name": c.name,
                                                               "arguments": json.dumps(c.args, ensure_ascii=False)}}
                                                 for c in turn.tool_calls]})
            finish_requested = False
            for call in turn.tool_calls:
                t1 = time.monotonic()
                result = execute_tool(self.retro, call.name, call.args, self.doc_reader)
                duration_ms = int((time.monotonic() - t1) * 1000)
                self._seq += 1
                summary = self._summary_line(self._seq, call.name, result)
                self.trace.record(self._seq, call.name, call.args, result,
                                  getattr(u, "completion_tokens", 0) if u is not None else 0,
                                  duration_ms)
                self.messages.append({"role": "tool", "tool_call_id": call.id,
                                      "content": truncate_result(result),
                                      "_summary": summary, "_seq": self._seq})
                if call.name == "finish":
                    finish_requested = True
                    summary = str(call.args.get("summary") or "")
                    if summary:
                        self._finish_summary = summary
                elif call.name == "finalize":
                    self._finalized = True  # LLM 已自行 finalize，自动收尾不得再覆盖
                self._track_errors(call.name, result)
                hot = max(self._consecutive_errors.values(), default=0)
                if hot >= 10:
                    bad = max(self._consecutive_errors, key=self._consecutive_errors.get)
                    return self._finish("failed",
                                        f"circuit breaker: 10 consecutive errors on '{bad}'",
                                        usage_total, "circuit_breaker")
            self._log_message(turn)
            if finish_requested:
                return self._finish("succeeded", "finished by llm", usage_total, "finish")
            self._compact()

    # ── helpers ──
    def _wire_messages(self) -> list[dict]:
        """Internal message view (with _summary/_seq/_compacted keys) stripped for the LLM."""
        return [{k: v for k, v in m.items() if not k.startswith("_")} for m in self.messages]

    def _finish(self, status: str, reason: str, usage: Usage, code: str) -> DriverResult:
        export_result = {}
        if status != "failed":
            export_result = self._finalize_export()
        return DriverResult(status=status, reason=reason, steps=self._seq,
                            tokens_in=usage.prompt_tokens, tokens_out=usage.completion_tokens,
                            export_result=export_result or {})

    def _finalize_export(self) -> dict:
        if not self._finalized:
            try:
                summary = self._finish_summary or f"auto-finalize ({self.name})"
                self.retro.execute("finalize", {"summary": summary})
            except Exception:
                pass
            self._finalized = True
        args = {"name": self.name}
        if self.workspace is not None:
            args["output_dir"] = str(self.workspace / "export")
        try:
            r = self.retro.execute("export", args)
            return r if isinstance(r, dict) else {}
        except Exception:
            return {}

    def _track_errors(self, name: str, result) -> None:
        if isinstance(result, dict) and result.get("error"):
            self._consecutive_errors[name] = self._consecutive_errors.get(name, 0) + 1
        else:
            self._consecutive_errors.pop(name, None)

    @staticmethod
    def _summary_line(seq: int, name: str, result) -> str:
        if isinstance(result, dict) and result.get("error"):
            return f"step {seq}: {name} → error: {str(result['error'])[:120]}"
        keys = {k: result[k] for k in ("ok", "action", "n_attempts", "terminal_count", "pending_count")
                if isinstance(result, dict) and k in result}
        return f"step {seq}: {name} → {keys or 'ok'}"

    def _compact(self) -> None:
        tool_idx = [i for i, m in enumerate(self.messages) if m.get("role") == "tool"]
        old = tool_idx[: max(0, len(tool_idx) - self.limits.keep_recent)]
        for i in old:
            m = self.messages[i]
            if m.get("_compacted"):
                continue
            m["content"] = m.get("_summary", "(summarized)")
            m["_compacted"] = True

    def _log_json(self, obj: dict) -> None:
        if self.workspace is None:
            return
        with open(self.workspace / "messages.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False, default=str) + "\n")

    def _log_message(self, turn) -> None:
        self._log_json({"tool_calls": [{"name": c.name, "args": c.args}
                                       for c in turn.tool_calls]})
