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
def client():
    from app.main import create_app
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def db():
    from app.db.base import Base
    from app.db.session import make_engine
    import app.db.models  # register tables on Base
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    from sqlalchemy.orm import sessionmaker
    S = sessionmaker(bind=engine)
    s = S()
    yield s
    s.close()
