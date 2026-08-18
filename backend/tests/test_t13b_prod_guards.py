"""T13b production guards: celery include, worker engine init, cancel race, llm retry."""
from types import SimpleNamespace

from app.agent.driver import AgentDriver, DriverResult
from app.db.models import Job, JobStatus
from tests.fakes import FakeRetroCmd, ListTrace, ToolCall


# ── C1: celery include ──
def test_celery_includes_worker_tasks():
    from app.worker.celery_app import celery_app
    assert "app.worker.tasks" in (celery_app.conf.include or [])


# ── C2: worker engine init ──
def test_ensure_engine_binds_when_unbound(tmp_path, monkeypatch):
    import app.db.session as dbs
    from app.worker.tasks import _ensure_engine

    saved_engine, saved_local = dbs.engine, dbs.SessionLocal
    dbs.engine = None
    monkeypatch.setattr(dbs, "get_settings",
                        lambda: SimpleNamespace(database_url=f"sqlite:///{tmp_path}/w.db"))
    try:
        _ensure_engine()
        assert dbs.engine is not None
        s = dbs.SessionLocal()
        s.close()
    finally:
        dbs.engine = saved_engine
        dbs.SessionLocal = saved_local
        if saved_engine is not None:
            dbs.SessionLocal.configure(bind=saved_engine)


def test_ensure_engine_idempotent_no_clobber():
    import app.db.session as dbs
    from app.worker.tasks import _ensure_engine
    _ensure_engine()  # engine already bound (by conftest/db fixtures or prior init)
    assert dbs.engine is not None


# ── I3: cancel race ──
class _FakeDriver:
    def __init__(self, result, on_run=None):
        self._result, self._on_run = result, on_run

    def run(self):
        if self._on_run:
            self._on_run()
        return self._result


def _make_job(db, monkeypatch):
    from sqlalchemy.orm import sessionmaker
    import app.db.session as dbs
    from app.db.models import User
    monkeypatch.setattr(dbs, "SessionLocal", sessionmaker(bind=db.get_bind()))
    # FK 强制开启后（make_engine PRAGMA foreign_keys=ON），user_id 必须指向真实用户
    if db.get(User, 1) is None:
        db.add(User(id=1, username="t13b", password_hash="x"))
        db.commit()
    job = Job(name="t", smiles="CCO", user_id=1)
    db.add(job)
    db.commit()
    return job.id


def test_cancelled_before_pickup_aborts_without_driver(db, monkeypatch):
    import app.worker.tasks as tasks_mod
    job_id = _make_job(db, monkeypatch)
    from app.services.jobs import set_status
    set_status(db, job_id, JobStatus.CANCELLED)

    def _boom(*a, **k):
        raise AssertionError("driver must not be built for cancelled job")
    monkeypatch.setattr(tasks_mod, "_build_driver", _boom)
    out = tasks_mod.run_retro_job(job_id)
    assert out == JobStatus.CANCELLED
    db.expire_all()
    assert db.get(Job, job_id).status == JobStatus.CANCELLED


def test_cancelled_during_run_not_overwritten(db, monkeypatch):
    import app.worker.tasks as tasks_mod
    from app.services.jobs import set_status
    job_id = _make_job(db, monkeypatch)

    def _cancel_mid_run():
        set_status(db, job_id, JobStatus.CANCELLED)

    fake = _FakeDriver(DriverResult(status="succeeded", reason="done"), on_run=_cancel_mid_run)
    monkeypatch.setattr(tasks_mod, "_build_driver", lambda *a, **k: fake)
    out = tasks_mod.run_retro_job(job_id)
    db.expire_all()
    job = db.get(Job, job_id)
    assert job.status == JobStatus.CANCELLED
    assert out == JobStatus.CANCELLED


# ── I4: llm retry ──
class _FlakyLLM:
    """Raises `fail_first` times, then returns a finish tool_call."""
    def __init__(self, fail_first: int):
        self.n, self.fail_first = 0, fail_first

    def chat(self, messages, tools):
        self.n += 1
        if self.n <= self.fail_first:
            raise RuntimeError(f"transient {self.n}")
        from app.agent.llm_client import ChatTurn
        return ChatTurn(tool_calls=[ToolCall(id="c1", name="finish", args={"summary": "ok"})])


def _driver_with(llm):
    return AgentDriver(retro=FakeRetroCmd(), llm=llm, trace=ListTrace(),
                       task_prompt="t", name="t",
                       limits=SimpleNamespace(max_steps=50, wall_clock_sec=600, keep_recent=10))


def test_llm_retries_survive_4_transient_errors():
    r = _driver_with(_FlakyLLM(4)).run()
    assert r.status == "succeeded"


def test_llm_5_consecutive_errors_fail():
    r = _driver_with(_FlakyLLM(5)).run()
    assert r.status == "failed" and "llm error" in r.reason
