import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker
from app.core.config import get_settings


def make_engine(url: str | None = None) -> sa.Engine:
    return sa.create_engine(url or get_settings().database_url, pool_pre_ping=True)


engine = None  # 惰性创建，避免 import 时连库
SessionLocal = sessionmaker()


def init_engine():
    global engine
    engine = make_engine()
    SessionLocal.configure(bind=engine)
