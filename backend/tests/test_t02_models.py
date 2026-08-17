def test_job_step_roundtrip(db):
    from app.db.models import User, Job, JobStep
    u = User(username="alice", password_hash="x", role="admin")
    db.add(u); db.flush()
    j = Job(id="j1", user_id=u.id, smiles="CCO", name="ethanol")
    db.add(j); db.flush()
    db.add(JobStep(job_id="j1", seq=1, command="init", args={"target": "CCO"},
                   result_summary="ok", status="ok"))
    db.commit()
    from app.db.models import JobStatus  # 常量类
    assert j.status == JobStatus.QUEUED
    steps = db.query(JobStep).filter_by(job_id="j1").all()
    assert len(steps) == 1 and steps[0].command == "init"
