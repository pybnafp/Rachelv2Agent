import sys as _sys
from pathlib import Path as _Path
_RACHEL_ROOT = _Path(__file__).resolve().parents[2] / "Rachel-v2"
if str(_RACHEL_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_RACHEL_ROOT))

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _testing(monkeypatch):
    monkeypatch.setenv("TESTING", "true")
    monkeypatch.setenv("PUBCHEM_OFFLINE", "true")  # 测试永不触网；审计 offline 参数仍可显式覆盖
    from app.core.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    import app.core.config as cfg
    # pydantic v2: plain class attr is shadowed by instance __dict__;
    # a property (data descriptor) takes precedence for all instances.
    monkeypatch.setattr(cfg.Settings, "data_dir", property(lambda self: tmp_path), raising=False)


@pytest.fixture(autouse=True)
def _clear_sent():
    """每个测试重置 console 邮件后端的发送记录。"""
    from app.services.email import SENT
    SENT.clear()
    yield
    SENT.clear()


@pytest.fixture
def client(db):
    from sqlalchemy.orm import sessionmaker
    import app.db.session as dbs
    from app.main import create_app
    from app.api.deps import get_db

    # Points SessionLocal at the test engine for code paths that call it directly
    dbs.SessionLocal = sessionmaker(bind=db.get_bind())
    app = create_app()
    def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    app.state.test_db = db
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db():
    from app.db.base import Base
    from app.db.session import make_engine
    import app.db.models  # register tables on Base
    from sqlalchemy.pool import StaticPool
    engine = make_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    from sqlalchemy.orm import sessionmaker
    S = sessionmaker(bind=engine)
    s = S()
    yield s
    s.close()


def verify_email(client, email: str) -> dict:
    """读取 console 后端 SENT 中该邮箱最新验证码并完成 verify，返回响应 JSON。"""
    from app.services.email import SENT
    code = [e for e in SENT if e["email"] == email][-1]["code"]
    r = client.post("/api/auth/verify", json={"email": email, "code": code})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def auth_headers_admin(client, db):
    client.post("/api/auth/register", json={"email": "adm@t.local", "password": "admpass1"})
    tok = verify_email(client, "adm@t.local")["access_token"]  # 首个验证用户 = admin
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
def auth_headers_user(client, db, auth_headers_admin):
    client.post("/api/auth/register", json={"email": "usr@t.local", "password": "usrpass2"})
    tok = verify_email(client, "usr@t.local")["access_token"]
    return {"Authorization": f"Bearer {tok}"}
