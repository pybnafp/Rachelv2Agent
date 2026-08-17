"""M5 生产序回归：worker 任务须在创建 Session 前自行完成 engine 绑定。"""


def test_run_retro_job_binds_engine_before_session(tmp_path, monkeypatch):
    """生产序回归：SessionLocal 未预绑定 + engine 未初始化时，任务必须自行完成绑定。"""
    import app.db.session as dbs
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import create_engine
    db_file = tmp_path / "prod_sim.db"
    url = f"sqlite:///{db_file}"
    # 模拟全新进程：engine=None，SessionLocal 为未绑定的全新工厂
    monkeypatch.setattr(dbs, "engine", None)
    fresh = sessionmaker()
    monkeypatch.setattr(dbs, "SessionLocal", fresh)
    import app.core.config as cfg
    monkeypatch.setattr(cfg.Settings, "data_dir", property(lambda self: tmp_path), raising=False)
    monkeypatch.setenv("DATABASE_URL", url)
    cfg.get_settings.cache_clear()
    # 在该库中预置 job（绕开 fresh 工厂，用显式 engine 建表插行）
    from app.db.base import Base
    import app.db.models  # noqa
    eng = create_engine(url)
    Base.metadata.create_all(eng)
    S = sessionmaker(bind=eng)
    s = S()
    from app.db.models import User, Job
    u = User(username="prodsim", password_hash="x", role="user")
    s.add(u)
    s.commit()
    s.add(Job(id="jprod", user_id=u.id, smiles="CCO", status="queued"))
    s.commit()
    s.close()
    # mock driver（真 LLM 不需要）
    from app.worker import tasks as T

    class R:
        status = "succeeded"
        reason = ""
        steps = 1
        tokens_in = 1
        tokens_out = 1
        export_result = {}

    class D:
        def __init__(self, *a, **k):
            pass

        def run(self):
            return R()

    monkeypatch.setattr(T, "_build_driver", lambda job, ws: D())
    # 关键：不经 API/eager（那些路径已被 conftest 污染）——直接调任务函数体
    result = T.run_retro_job.apply(args=["jprod"]).get()
    assert result == "succeeded"
    s2 = S()
    assert s2.get(Job, "jprod").status == "succeeded"
    s2.close()
    # 还原全局
    cfg.get_settings.cache_clear()
