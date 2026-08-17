import json
from pathlib import Path
FIX = Path(__file__).parent / "fixtures"

def test_summarize_result():
    from app.agent.trace import summarize_result
    assert "error" in summarize_result("commit", {"error": "gate blocked"})
    s = summarize_result("reaction_sites", {"sites": [{"site_id": "s1"}, {"site_id": "s2"}]})
    assert "s1" not in s            # 摘要只保留计数，不展开 payload
    assert "2" in s or "sites" in s

def test_db_trace_sink_roundtrip(db):
    from app.agent.trace import DbTraceSink
    from app.db.models import Job, JobStep, User
    db.add(User(username="t", password_hash="x")); db.flush()
    db.add(Job(id="j9", user_id=1, smiles="CCO")); db.commit()
    from sqlalchemy.orm import sessionmaker
    sink = DbTraceSink(sessionmaker(bind=db.get_bind()), "j9")
    sink.record(1, "init", {"target": "CCO"}, {"ok": True}, 0, 12)
    sink.record(2, "next", {}, {"smiles": "CCO"}, 0, 5)
    rows = db.query(JobStep).filter_by(job_id="j9").order_by(JobStep.seq).all()
    assert [r.command for r in rows] == ["init", "next"]
    assert rows[0].result_summary and rows[0].duration_ms == 12

def test_parse_export_real_fixture():
    from app.services.artifacts import parse_export
    out = parse_export(FIX)
    assert out["metrics"]["n_nodes"] == len(out["visualization"]["nodes"])
    assert out["metrics"]["n_nodes"] >= 10        # demo 数据真实规模
    assert out["metrics"]["n_terminals"] >= 2
    assert not out.get("incomplete")

def test_parse_export_missing_dir(tmp_path):
    from app.services.artifacts import parse_export
    out = parse_export(tmp_path / "nope")
    assert out.get("incomplete") is True and "visualization" not in out
