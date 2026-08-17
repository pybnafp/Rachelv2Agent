import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _testing(monkeypatch):
    monkeypatch.setenv("TESTING", "true")
    from app.core.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


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
