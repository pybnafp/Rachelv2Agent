from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "Rachel-v2" / "Rachel"


def test_system_prompt_contains_skill_and_cheatsheet():
    from app.agent.prompts import build_system_prompt
    p = build_system_prompt()
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert skill[:200].strip() in p            # SKILL.md 内容嵌入
    assert "reaction_sites" in p               # 速查表
    assert "finalize" in p and "export" in p


def test_task_prompt_contains_target():
    from app.agent.prompts import build_task_prompt
    p = build_task_prompt("CC(=O)Nc1ccc(O)cc1", "paracetamol")
    assert "CC(=O)Nc1ccc(O)cc1" in p and "paracetamol" in p
    assert "export" in p                       # 明确要求最终 export


def test_doc_reader_workflow():
    from app.agent.prompts import DocReader
    dr = DocReader(ROOT)
    r = dr.read("workflow")
    assert r.get("ok") and len(r["content"]) > 100
    r2 = dr.read("nope")
    assert not r2.get("ok")


def test_doc_reader_truncates():
    from app.agent.prompts import DocReader
    dr = DocReader(ROOT)
    r = dr.read("workflow")
    assert len(r["content"]) <= 24000          # 内部上限 24000 字符
