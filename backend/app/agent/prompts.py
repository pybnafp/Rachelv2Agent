from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3] / "Rachel-v2" / "Rachel"
DOC_FILES = {"workflow": "workflow.md", "experience": "experience_cards.md"}
DOC_LIMIT = 24000

CHEATSHEET = """
## 快速流程参考（cheat sheet）
标准流程: init(target) → next → [route_plan] → reaction_sites → explore_site(site_id)
  → try_action(action_id) → (gate 通过) commit(idx, reasoning) → next → …
  → 全部叶子 terminal 后 next 返回 queue_empty → finalize(summary) → export → finish
要点:
- 每步决策绑定当前 active node；先 next 再 reaction_sites，不要并行猜测。
- try_action 失败或 gate 非 pass 时：换 action、propose_action 自提、或 route_sketch 救援。
- commit 必须写清 reasoning（机理/骨架守恒/被拒理由）；accept 需给 reason。
- 沙盒多方案时先 sandbox_list 比较，再 select(idx) + commit(idx)。
- 长会话优先用细粒度命令（explore_site 单 site）而非 context(full)。
"""


def build_system_prompt() -> str:
    skill = (_ROOT / "SKILL.md").read_text(encoding="utf-8")
    return f"# Rachel-v2 Skill Instructions\n\n{skill}\n\n{CHEATSHEET}"


def build_task_prompt(smiles: str, name: str) -> str:
    label = f"（名称: {name}）" if name else ""
    return (
        f"目标分子{label}: {smiles}\n\n"
        f"请按照 skill 流程完成完整逆合成路线规划：驱动状态机直到所有叶子 terminal，"
        f"然后 finalize 并 export，最后调用 finish 工具并给出一段路线总结。"
    )


class DocReader:
    def __init__(self, root: Path | None = None):
        self.root = root or _ROOT

    def read(self, doc: str, section: str = "") -> dict:
        fname = DOC_FILES.get(doc)
        if not fname:
            return {"ok": False, "error": f"unknown doc: {doc}; options: {list(DOC_FILES)}"}
        path = self.root / fname
        if not path.exists():
            return {"ok": False, "error": f"file not found: {fname}"}
        text = path.read_text(encoding="utf-8")
        if section:
            hit = self._section(text, section)
            if hit is None:
                return {"ok": False, "error": f"section not found: {section}"}
            text = hit
        if len(text) > DOC_LIMIT:
            notice = f"\n...[truncated at {DOC_LIMIT} chars]"
            text = text[: DOC_LIMIT - len(notice)] + notice
        return {"ok": True, "doc": doc, "section": section, "content": text}

    @staticmethod
    def _section(text: str, title: str) -> str | None:
        lines, buf, capturing = text.splitlines(), [], False
        for ln in lines:
            if ln.startswith("#"):
                if capturing:
                    break
                if title.lower() in ln.lower():
                    capturing = True
            if capturing:
                buf.append(ln)
        return "\n".join(buf) if capturing else None
