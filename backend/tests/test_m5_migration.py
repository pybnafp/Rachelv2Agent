"""M5-T1: PG-ready timezone columns + migration 0002 executable from scratch on sqlite."""
import os
import sqlite3

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TZ_COLUMNS = {
    "users": ["created_at"],
    "jobs": ["created_at", "started_at", "finished_at"],
    "job_steps": ["created_at"],
    "llm_providers": ["created_at"],
}


def test_models_datetime_columns_are_timezone_aware():
    """(a) model metadata declares DateTime(timezone=True) on all DateTime columns."""
    from app.db.base import Base
    import app.db.models  # noqa: F401

    for table, cols in TZ_COLUMNS.items():
        for col in cols:
            col_obj = Base.metadata.tables[table].columns[col]
            assert isinstance(col_obj.type, sa.DateTime), f"{table}.{col}: {col_obj.type}"
            assert col_obj.type.timezone is True, (
                f"{table}.{col}.type.timezone is {col_obj.type.timezone}"
            )
    # no DateTime column anywhere escaped the sweep
    for table in Base.metadata.tables.values():
        for col in table.columns:
            if isinstance(col.type, sa.DateTime):
                assert col.type.timezone is True, f"{table.name}.{col.name} missing timezone=True"


def _alembic_config(db_url: str) -> Config:
    cfg = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND_DIR, "alembic"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def test_fresh_sqlite_upgrade_head(tmp_path):
    """(b) full `alembic upgrade head` from empty sqlite works (timezone flag is a no-op there)."""
    db_path = tmp_path / "fresh.db"
    command.upgrade(_alembic_config(f"sqlite:///{db_path}"), "head")
    conn = sqlite3.connect(db_path)
    try:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()
    assert {"users", "jobs", "job_steps", "llm_providers", "alembic_version"} <= tables
    rev = sqlite3.connect(db_path).execute("SELECT version_num FROM alembic_version").fetchall()
    assert rev, "no alembic revision recorded"
