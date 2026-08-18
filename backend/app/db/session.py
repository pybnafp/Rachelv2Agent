import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker
from app.core.config import get_settings


def make_engine(url: str | None = None, **kwargs) -> sa.Engine:
    engine = sa.create_engine(url or get_settings().database_url, pool_pre_ping=True, **kwargs)
    if engine.url.get_backend_name() == "sqlite":
        # SQLite 默认不校验外键（PostgreSQL 会）→ 测试盲区来源。
        # 对所有 sqlite 连接强制开启外键约束，与生产 PG 行为一致；PG 引擎不会注册此监听。
        from sqlalchemy import event

        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_connection, _record):  # pragma: no cover - trivial driver hook
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    return engine


engine = None  # 惰性创建，避免 import 时连库
SessionLocal = sessionmaker()


def init_engine():
    global engine
    engine = make_engine()
    SessionLocal.configure(bind=engine)
