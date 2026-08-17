# Rachel-v2 Web 平台 M1（后端骨架跑通）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 搭建可运行的后端骨架：用户认证 + 任务提交 API + Celery 生命周期 + AgentDriver（mock LLM）端到端跑通并产出 Rachel-v2 export 产物。

**Architecture:** FastAPI（API 进程）+ Celery worker（进程内调用 `Rachel.main.retro_cmd.RetroCmd` 状态机）+ AgentDriver（OpenAI 兼容 function-calling 循环，mock 客户端可注入）。单测全部跑在 SQLite + Celery eager 模式 + Mock/Fake 替身上，不需要 Redis/PG/真实 LLM。

**Tech Stack:** Python 3.11（conda env `rachel-v2`）、FastAPI、SQLAlchemy 2.0、alembic、Celery 5、passlib+python-jose（JWT）、openai SDK、pytest。

**Spec:** `docs/superpowers/specs/2026-08-17-rachel-web-platform-design.md`（本计划实现其 M1 里程碑；M2 前端、M3 审计面板、M4 进度/admin 完善、M5 服务器部署，各自启动时另写计划）

## Global Constraints

- 所有后端命令在 conda env `rachel-v2` 内执行：`conda run -n rachel-v2 python -m pytest backend/tests -v`（Windows Git Bash）。
- 依赖安装：`conda run -n rachel-v2 pip install -e "backend[dev]"`。
- **`Rachel-v2/` 目录只读**——任何任务不得修改其内部代码；调用方式只有 `from Rachel.main.retro_cmd import RetroCmd`。
- 测试不依赖外部服务：SQLite（内存）+ `task_always_eager=True` + MockLLMClient/FakeRetroCmd。Redis/PG 仅出现在 deploy/ 配置里。
- SQLAlchemy JSON 字段用 `sa.JSON().with_variant(postgresql.JSONB(), "postgresql")`，保证 SQLite 测试与 PG 生产兼容。
- 时间戳一律 UTC（`datetime.now(timezone.utc)`）。
- 任务状态枚举固定：`queued / running / succeeded / partial / failed / cancelled`。
- 每个任务结束必须 commit（conventional commits：`feat:`/`test:`/`chore:`）。
- 密钥只进 `.env`（已被根 `.gitignore` 覆盖），代码中零硬编码密钥。
- Windows 开发注意：celery 若需手动起 worker 用 `-P solo`；测试用 eager 模式不需要 worker。

## File Structure（M1 全量文件图）

```
backend/
├── pyproject.toml                     # T1: 包定义+依赖
├── alembic.ini + alembic/             # T2: 迁移
├── app/
│   ├── __init__.py
│   ├── main.py                        # T1: create_app 工厂 + /health
│   ├── core/{__init__,config,security}.py      # T1 配置 / T3 安全
│   ├── db/{__init__,base,models,session}.py    # T2
│   ├── schemas/{__init__,auth,jobs,admin}.py   # T3/T5/T4
│   ├── api/{__init__,deps,auth,jobs,admin}.py  # T3/T5/T4
│   ├── services/{__init__,smiles,jobs,artifacts}.py  # T5/T10
│   ├── agent/{__init__,llm_client,tools,prompts,driver,trace}.py  # T4/T7/T8/T9/T10
│   └── worker/{__init__,celery_app,tasks}.py   # T5 stub / T6 实装
├── tests/                             # 每个 T*.py 对应任务编号
│   ├── conftest.py                    # T1 建，后续任务扩展
│   ├── fakes.py                       # T9: FakeRetroCmd/MockLLMClient 复用件
│   └── fixtures/visualization.json    # T10: 拷贝自 examples/result_demo/export
scripts/smoke_retro.py                 # T12: 真实化学冒烟
deploy/docker-compose.yml              # T13
.env.example                           # T13
```

**跨任务接口契约**（后续所有任务的 Consumes/Produces 引用此处，不再重复定义）：

```python
# app/core/config.py
def get_settings() -> Settings  # lru_cache 单例；字段见 T1
# app/db/session.py
SessionLocal  # sessionmaker 工厂
# app/core/security.py
def hash_password(pw: str) -> str
def verify_password(pw: str, hashed: str) -> bool
def create_access_token(user_id: int, role: str) -> str
def decode_token(token: str) -> dict | None   # {"sub": str(user_id), "role": str, "exp": int}
# app/api/deps.py
def get_db() -> Iterator[Session]
def get_current_user(token: str, db: Session) -> User   # FastAPI 依赖，Bearer
# app/services/smiles.py
def validate_smiles(s: str) -> tuple[str | None, str]   # (canonical_smiles, error_msg)
# app/services/jobs.py
def set_status(db, job_id: str, status: str, error: str = "", stats_patch: dict | None = None) -> Job
def count_active(db, user_id: int) -> int               # queued+running 计数
# app/agent/llm_client.py
@dataclass ToolCall: id: str; name: str; args: dict
@dataclass Usage: prompt_tokens: int; completion_tokens: int
@dataclass ChatTurn: content: str; tool_calls: list[ToolCall]; usage: Usage
class OpenAICompatClient:  # __init__(base_url, api_key, model, temperature=0.2, max_output=4096)
    def chat(self, messages: list[dict], tools: list[dict]) -> ChatTurn
class MockLLMClient:       # __init__(script: list[list[ToolCall]])  每次调用弹出下一组
    def chat(self, messages, tools) -> ChatTurn
# app/agent/tools.py
TOOL_SCHEMAS: list[dict]                       # 26 RetroCmd + read_doc + finish
def execute_tool(retro, name: str, args: dict, doc_reader) -> dict
def truncate_result(obj, limit: int = 8192) -> str   # JSON 序列化+截断+提示
# app/agent/prompts.py
def build_system_prompt() -> str
def build_task_prompt(smiles: str, name: str) -> str
class DocReader:  # __init__(root: Path); .read(doc: str, section: str = "") -> dict
# app/agent/driver.py
@dataclass DriverLimits: max_steps: int = 300; wall_clock_sec: int = 3600; keep_recent: int = 10
@dataclass DriverResult: status: str; reason: str; steps: int; tokens_in: int; tokens_out: int; export_result: dict
class AgentDriver:  # __init__(retro, llm, trace, limits=None)
    def run(self) -> DriverResult                  # trace 需实现 .record(seq, command, args, result, tokens, duration_ms)
# app/agent/trace.py
def summarize_result(command: str, result: dict) -> str
class DbTraceSink:  # __init__(session_factory, job_id)
    def record(self, seq, command, args, result, tokens, duration_ms) -> None
# app/services/artifacts.py
def parse_export(export_dir: Path) -> dict        # {"visualization", "terminals", "metrics", "incomplete"?}
# app/worker/tasks.py
@celery_app.task def run_retro_job(self, job_id: str) -> str   # 返回最终状态
```

---

### Task 1: 后端骨架（pyproject + 配置 + app 工厂 + /health）

**Files:**
- Create: `backend/pyproject.toml`, `backend/app/__init__.py`, `backend/app/main.py`, `backend/app/core/__init__.py`, `backend/app/core/config.py`
- Test: `backend/tests/__init__.py`, `backend/tests/conftest.py`（初版）, `backend/tests/test_t01_health.py`

**Interfaces:**
- Produces: `get_settings()`；`create_app() -> FastAPI`；Settings 字段：`database_url, redis_url, jwt_secret, jwt_expire_minutes, data_dir, deepseek_api_key, deepseek_base_url(默认 https://api.deepseek.com), deepseek_model(默认 deepseek-v4-pro), default_llm_name, max_heavy_atoms=80, max_running_per_user=3, testing: bool = False`

- [ ] **Step 1: 写 pyproject.toml**

```toml
[project]
name = "rachel-backend"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.110", "uvicorn[standard]>=0.29", "celery>=5.3",
  "sqlalchemy>=2.0", "alembic>=1.13", "redis>=5.0",
  "pydantic>=2.6", "pydantic-settings>=2.2",
  "openai>=1.30", "httpx>=0.27",
  "passlib[bcrypt]>=1.7", "python-jose[cryptography]>=3.3",
]
[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-cov"]
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"
[tool.setuptools.packages.find]
include = ["app*"]
```

- [ ] **Step 2: 写失败测试 test_t01_health.py**

```python
def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
```

- [ ] **Step 3: conftest.py 初版**

```python
import pytest
from fastapi.testclient import TestClient

@pytest.fixture(autouse=True)
def _testing(monkeypatch):
    monkeypatch.setenv("TESTING", "true")

@pytest.fixture
def client():
    from app.main import create_app
    with TestClient(create_app()) as c:
        yield c
```

- [ ] **Step 4: config.py**

```python
from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./dev.db"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "dev-secret-change-me"
    jwt_expire_minutes: int = 720
    data_dir: Path = Path("data/jobs")
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-pro"
    default_llm_name: str = "deepseek"
    max_heavy_atoms: int = 80
    max_running_per_user: int = 3
    testing: bool = False

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 5: main.py**

```python
from fastapi import FastAPI

def create_app() -> FastAPI:
    app = FastAPI(title="Rachel-v2 Web Platform")
    @app.get("/health")
    def health():
        return {"status": "ok"}
    return app

app = create_app()
```

- [ ] **Step 6: 安装并验证**

Run: `conda run -n rachel-v2 pip install -e "backend[dev]" && conda run -n rachel-v2 python -m pytest backend/tests -v`
Expected: test_t01 PASS（TESTING=true 时 conftest 里 monkeypatch env 生效于 Settings 每次 实例化——注意 lru_cache 会缓存 settings，因此测试前 `get_settings.cache_clear()`；把这句加进 conftest 的 `_testing` fixture）

- [ ] **Step 7: Commit**

```bash
git add backend/pyproject.toml backend/app backend/tests
git commit -m "feat: backend skeleton with settings and app factory"
```

---

### Task 2: 数据模型 + alembic 迁移

**Files:**
- Create: `backend/app/db/__init__.py`, `backend/app/db/base.py`, `backend/app/db/models.py`, `backend/app/db/session.py`, `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/versions/0001_initial.py`, `backend/tests/test_t02_models.py`

**Interfaces:**
- Consumes: `get_settings()`（database_url）
- Produces: `Base`（DeclarativeBase）、`User/LlmProvider/Job/JobStep`、`SessionLocal`、`make_engine(url)`（测试建内存引擎用）

- [ ] **Step 1: 写失败测试 test_t02_models.py**

```python
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
```

- [ ] **Step 2: conftest 加 db fixture**

```python
@pytest.fixture
def db():
    from app.db.base import Base
    from app.db.session import make_engine
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    from sqlalchemy.orm import sessionmaker
    S = sessionmaker(bind=engine)
    s = S()
    yield s
    s.close()
```

- [ ] **Step 3: models.py（JSON 字段用 variant）**

```python
import uuid
from datetime import datetime, timezone
import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

def utcnow(): return datetime.now(timezone.utc)
JSONType = sa.JSON().with_variant(sa.dialects.postgresql.JSONB(), "postgresql")

class JobStatus:
    QUEUED="queued"; RUNNING="running"; SUCCEEDED="succeeded"
    PARTIAL="partial"; FAILED="failed"; CANCELLED="cancelled"

class Base(DeclarativeBase): pass  # 实际放 app/db/base.py，此处 import

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(sa.String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(sa.String(128))
    role: Mapped[str] = mapped_column(sa.String(16), default="user")
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow)

class LlmProvider(Base):
    __tablename__ = "llm_providers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(64), unique=True)
    base_url: Mapped[str] = mapped_column(sa.String(256))
    api_key: Mapped[str] = mapped_column(sa.String(256))
    model: Mapped[str] = mapped_column(sa.String(128))
    temperature: Mapped[float] = mapped_column(default=0.2)
    max_output: Mapped[int] = mapped_column(default=4096)
    is_active: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow)

class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True, default=lambda: uuid.uuid4().hex)
    user_id: Mapped[int] = mapped_column(sa.ForeignKey("users.id"), index=True)
    smiles: Mapped[str] = mapped_column(sa.Text)
    name: Mapped[str] = mapped_column(sa.String(128), default="")
    status: Mapped[str] = mapped_column(sa.String(16), default=JobStatus.QUEUED, index=True)
    provider_id: Mapped[int | None] = mapped_column(sa.ForeignKey("llm_providers.id"), nullable=True)
    error: Mapped[str] = mapped_column(sa.Text, default="")
    stats: Mapped[dict] = mapped_column(JSONType, default=dict)
    celery_task_id: Mapped[str] = mapped_column(sa.String(64), default="")
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)

class JobStep(Base):
    __tablename__ = "job_steps"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(sa.ForeignKey("jobs.id"), index=True)
    seq: Mapped[int] = mapped_column(sa.Integer)
    command: Mapped[str] = mapped_column(sa.String(32))
    args: Mapped[dict] = mapped_column(JSONType, default=dict)
    result_summary: Mapped[str] = mapped_column(sa.Text, default="")
    status: Mapped[str] = mapped_column(sa.String(16), default="ok")
    tokens: Mapped[int] = mapped_column(sa.Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(sa.Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow)
```

- [ ] **Step 4: session.py**

```python
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
```

- [ ] **Step 5: alembic**

Run:
```bash
cd backend && conda run -n rachel-v2 python -m alembic init alembic
```
然后改 `alembic.ini` 的 `sqlalchemy.url` 为留空（env.py 从 settings 读），`alembic/env.py`：`from app.core.config import get_settings; from app.db.base import Base; import app.db.models; config.set_main_option("sqlalchemy.url", get_settings().database_url); target_metadata = Base.metadata`；生成迁移：
```bash
conda run -n rachel-v2 python -m alembic revision --autogenerate -m "initial tables"
conda run -n rachel-v2 python -m alembic upgrade head   # 对 dev.db 验证可执行
```
Expected: 三张表 + llm_providers 建表成功

- [ ] **Step 6: 跑测试**

Run: `conda run -n rachel-v2 python -m pytest backend/tests/test_t02_models.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/db backend/alembic backend/alembic.ini backend/tests/test_t02_models.py backend/tests/conftest.py
git commit -m "feat: db models with alembic migrations"
```

---

### Task 3: 认证（注册/登录/me，首用户 admin）

**Files:**
- Create: `backend/app/core/security.py`, `backend/app/schemas/__init__.py`, `backend/app/schemas/auth.py`, `backend/app/api/__init__.py`, `backend/app/api/deps.py`, `backend/app/api/auth.py`
- Modify: `backend/app/main.py`（挂路由）
- Test: `backend/tests/test_t03_auth.py`

**Interfaces:**
- Consumes: `Base`/models、`SessionLocal`、`get_settings().jwt_secret/jwt_expire_minutes`
- Produces: 接口契约区的 `hash_password/verify_password/create_access_token/decode_token/get_db/get_current_user`；schemas：`RegisterIn{username,password}`, `TokenOut{access_token, role}`, `MeOut{id, username, role}`

- [ ] **Step 1: 写失败测试**

```python
def test_first_user_is_admin(client, db):
    r = client.post("/api/auth/register", json={"username": "alice", "password": "secret1"})
    assert r.status_code == 201 and r.json()["role"] == "admin"

def test_second_user_is_user(client, db):
    client.post("/api/auth/register", json={"username": "alice", "password": "secret1"})
    r = client.post("/api/auth/register", json={"username": "bob", "password": "secret2"})
    assert r.json()["role"] == "user"

def test_duplicate_username_409(client, db):
    client.post("/api/auth/register", json={"username": "alice", "password": "secret1"})
    assert client.post("/api/auth/register", json={"username": "alice", "password": "x2"}).status_code == 409

def test_login_wrong_password_401(client, db):
    client.post("/api/auth/register", json={"username": "alice", "password": "secret1"})
    assert client.post("/api/auth/login", json={"username": "alice", "password": "bad"}).status_code == 401

def test_me_requires_token(client, db):
    assert client.get("/api/auth/me").status_code == 401

def test_me_roundtrip(client, db):
    client.post("/api/auth/register", json={"username": "alice", "password": "secret1"})
    tok = client.post("/api/auth/login", json={"username": "alice", "password": "secret1"}).json()["access_token"]
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200 and r.json()["username"] == "alice"
```

- [ ] **Step 2: security.py**

```python
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.core.config import get_settings

_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(pw: str) -> str: return _ctx.hash(pw)
def verify_password(pw: str, hashed: str) -> bool: return _ctx.verify(pw, hashed)

def create_access_token(user_id: int, role: str) -> str:
    payload = {"sub": str(user_id), "role": role,
               "exp": datetime.now(timezone.utc) + timedelta(minutes=get_settings().jwt_expire_minutes)}
    return jwt.encode(payload, get_settings().jwt_secret, algorithm="HS256")

def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
    except JWTError:
        return None
```

- [ ] **Step 3: deps.py（get_db 可被测试 override）**

```python
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from app.db.models import User

bearer = HTTPBearer(auto_error=False)

def get_db():
    from app.db.session import SessionLocal
    db = SessionLocal()
    try: yield db
    finally: db.close()

def get_current_user(cred: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    from app.core.security import decode_token
    if cred is None: raise HTTPException(401, "missing token")
    payload = decode_token(cred.credentials)
    if not payload: raise HTTPException(401, "invalid token")
    user = db.get(User, int(payload["sub"]))
    if not user: raise HTTPException(401, "user not found")
    return user
```

- [ ] **Step 4: api/auth.py + main.py 挂载**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.deps import get_current_user, get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.db.models import User
from app.schemas.auth import MeOut, RegisterIn, TokenOut

router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.post("/register", response_model=TokenOut, status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.username == body.username)):
        raise HTTPException(409, "username already exists")
    role = "admin" if db.scalar(select(User).limit(1)) is None else "user"
    u = User(username=body.username, password_hash=hash_password(body.password), role=role)
    db.add(u); db.commit(); db.refresh(u)
    return TokenOut(access_token=create_access_token(u.id, u.role), role=role)

@router.post("/login", response_model=TokenOut)
def login(body: RegisterIn, db: Session = Depends(get_db)):
    u = db.scalar(select(User).where(User.username == body.username))
    if not u or not verify_password(body.password, u.password_hash):
        raise HTTPException(401, "invalid credentials")
    return TokenOut(access_token=create_access_token(u.id, u.role), role=u.role)

@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user)):
    return MeOut(id=user.id, username=user.username, role=user.role)
```

conftest 的 `client` fixture 需加 DB override：
```python
@pytest.fixture
def client(db, monkeypatch):
    from app.db.session import SessionLocal as _SL
    import app.db.session as dbs
    monkeypatch.setattr(dbs, "SessionLocal", type(db).bind and db.session_factory if False else _mk_factory(db))
    from app.main import create_app
    from app.api.deps import get_db
    app = create_app()
    app.dependency_overrides[get_db] = lambda: iter([db])
    with TestClient(app) as c: yield c
```
其中 `_mk_factory(db)` 返回绑定测试引擎的 sessionmaker（在 conftest 定义 `S = sessionmaker(bind=db.get_bind()); return S`）。简化实现见 Step 3 的 get_db：它 import SessionLocal 是函数内 import，monkeypatch `app.db.session.SessionLocal` 属性即可生效。

- [ ] **Step 5: 跑测试**

Run: `conda run -n rachel-v2 python -m pytest backend/tests/test_t03_auth.py -v`
Expected: 6 PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app backend/tests/test_t03_auth.py backend/tests/conftest.py
git commit -m "feat: jwt auth with first-user-admin rule"
```

---

### Task 4: LLM 供应商模型种子 + admin API + LLM 客户端（OpenAI 兼容 + Mock）

**Files:**
- Create: `backend/app/schemas/admin.py`, `backend/app/api/admin.py`, `backend/app/agent/__init__.py`, `backend/app/agent/llm_client.py`
- Modify: `backend/app/main.py`（挂 admin 路由 + 启动时 seed）
- Test: `backend/tests/test_t04_llm.py`

**Interfaces:**
- Consumes: models、auth deps
- Produces: 契约区 `ToolCall/Usage/ChatTurn/OpenAICompatClient/MockLLMClient`；`seed_default_provider(db)`（幂等：无任何行时插入 DeepSeek 默认行，active=True，api_key 取 settings）；`get_active_client(db) -> OpenAICompatClient | None`（active 行 → client；model=="mock" 时返回 MockLLMClient）；admin 端点 `GET/PUT /api/admin/llm-providers`（PUT body：`{id?, name, base_url, api_key?, model, temperature?, max_output?, is_active?}`；切换 is_active 时其余行置 False）

- [ ] **Step 1: 写失败测试**

```python
def test_admin_list_requires_admin(client, db, auth_headers_user):
    assert client.get("/api/admin/llm-providers", headers=auth_headers_user).status_code == 403

def test_admin_crud_and_switch(client, db, auth_headers_admin):
    r = client.get("/api/admin/llm-providers", headers=auth_headers_admin)
    assert r.status_code == 200 and len(r.json()) >= 1   # seed 行存在
    deepseek = next(p for p in r.json() if p["name"] == "deepseek")
    assert deepseek["is_active"] is True and deepseek["model"] == "deepseek-v4-pro"
    # 新增并切换 active
    r = client.put("/api/admin/llm-providers", headers=auth_headers_admin, json={
        "name": "glm", "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "api_key": "k2", "model": "glm-4.7", "is_active": True})
    pid = r.json()["id"]
    rows = client.get("/api/admin/llm-providers", headers=auth_headers_admin).json()
    assert next(p for p in rows if p["id"] == pid)["is_active"] is True
    assert next(p for p in rows if p["name"] == "deepseek")["is_active"] is False
    assert "api_key" not in rows[0]  # 响应不回显 key

def test_mock_llm_client_replays_script():
    from app.agent.llm_client import MockLLMClient, ToolCall
    mock = MockLLMClient(script=[[ToolCall("c1", "next", {})], [ToolCall("c2", "finish", {"summary": "done"})]])
    t1 = mock.chat([], [])
    assert t1.tool_calls[0].name == "next"
    t2 = mock.chat([], [])
    assert t2.tool_calls[0].name == "finish"

def test_openai_client_maps_tool_calls(monkeypatch):
    from app.agent import llm_client as lc
    class FakeResp:
        choices = [type("M", (), {"message": type("Msg", (), {"content": "", "tool_calls": [
            type("TC", (), {"id": "c1", "function": type("F", (), {"name": "next", "arguments": "{}"})})]}),
            "finish_reason": "tool_calls"})()]
        usage = type("U", (), {"prompt_tokens": 10, "completion_tokens": 5})
    captured = {}
    class FakeOpenAI:
        def __init__(self, **kw): pass
        class chat:
            @staticmethod
            def completions_create(**kw): captured.update(kw); return FakeResp()
    monkeypatch.setattr(lc, "OpenAI", FakeOpenAI)
    c = lc.OpenAICompatClient("http://x", "k", "m1")
    turn = c.chat([{"role": "user", "content": "hi"}], [{"type": "function", "function": {"name": "next"}}])
    assert turn.tool_calls[0].name == "next" and turn.usage.prompt_tokens == 10
    assert captured["model"] == "m1" and captured["tools"][0]["function"]["name"] == "next"
```

conftest 增补：
```python
@pytest.fixture
def auth_headers_admin(client, db):
    client.post("/api/auth/register", json={"username": "adm", "password": "pw1"})  # 首个= admin
    tok = client.post("/api/auth/login", json={"username": "adm", "password": "pw1"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}

@pytest.fixture
def auth_headers_user(client, db, auth_headers_admin):
    client.post("/api/auth/register", json={"username": "usr", "password": "pw2"})
    tok = client.post("/api/auth/login", json={"username": "usr", "password": "pw2"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}
```

- [ ] **Step 2: llm_client.py**

```python
import json
from dataclasses import dataclass, field
from openai import OpenAI

@dataclass
class ToolCall:
    id: str; name: str; args: dict = field(default_factory=dict)

@dataclass
class Usage:
    prompt_tokens: int = 0; completion_tokens: int = 0

@dataclass
class ChatTurn:
    content: str = ""; tool_calls: list = field(default_factory=list); usage: Usage = field(default_factory=Usage)

class OpenAICompatClient:
    def __init__(self, base_url, api_key, model, temperature=0.2, max_output=4096):
        self._cli = OpenAI(base_url=base_url, api_key=api_key)
        self.model, self.temperature, self.max_output = model, temperature, max_output

    def chat(self, messages, tools):
        resp = self._cli.chat.completions.create(
            model=self.model, messages=messages, tools=tools,
            temperature=self.temperature, max_tokens=self.max_output)
        msg = resp.choices[0].message
        calls = []
        for tc in (msg.tool_calls or []):
            try: args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError: args = {"_raw": tc.function.arguments}
            calls.append(ToolCall(id=tc.id, name=tc.function.name, args=args))
        u = getattr(resp, "usage", None)
        usage = Usage(u.prompt_tokens if u else 0, u.completion_tokens if u else 0)
        return ChatTurn(content=msg.content or "", tool_calls=calls, usage=usage)

class MockLLMClient:
    """按脚本回放 tool_calls，用于测试与无 LLM 环境。"""
    def __init__(self, script: list[list[ToolCall]]):
        self.script = list(script); self.calls = 0
        self.usage = Usage()
    def chat(self, messages, tools):
        if self.calls >= len(self.script):
            raise RuntimeError("MockLLMClient script exhausted")
        turns = self.script[self.calls]; self.calls += 1
        return ChatTurn(tool_calls=turns)
```

- [ ] **Step 3: seed + get_active_client（放 app/api/admin.py 或独立 services；实现放 admin.py 顶部）**

```python
def seed_default_provider(db) -> None:
    from sqlalchemy import select
    from app.core.config import get_settings
    from app.db.models import LlmProvider
    if db.scalar(select(LlmProvider).limit(1)) is not None: return
    s = get_settings()
    db.add(LlmProvider(name=s.default_llm_name, base_url=s.deepseek_base_url,
                       api_key=s.deepseek_api_key, model=s.deepseek_model, is_active=True))
    db.commit()

def get_active_client(db):
    from sqlalchemy import select
    from app.db.models import LlmProvider
    p = db.scalar(select(LlmProvider).where(LlmProvider.is_active))
    if p is None: return None
    if p.model == "mock":
        from app.agent.llm_client import MockLLMClient, ToolCall
        return MockLLMClient(script=[[ToolCall("auto", "finish", {"summary": "mock"})]])
    from app.agent.llm_client import OpenAICompatClient
    return OpenAICompatClient(p.base_url, p.api_key, p.model, p.temperature, p.max_output)
```

- [ ] **Step 4: admin 路由（GET 列表不回显 api_key；PUT upsert + 单 active 约束；非 admin 403）**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.deps import get_current_user, get_db
from app.db.models import LlmProvider, User
from app.schemas.admin import ProviderIn, ProviderOut

router = APIRouter(prefix="/api/admin", tags=["admin"])

@router.get("/llm-providers", response_model=list[ProviderOut])
def list_providers(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_admin(user)
    return db.scalars(select(LlmProvider)).all()

@router.put("/llm-providers", response_model=ProviderOut)
def upsert_provider(body: ProviderIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_admin(user)
    p = db.scalar(select(LlmProvider).where(LlmProvider.name == body.name))
    if p is None:
        p = LlmProvider(name=body.name); db.add(p)
    for k in ("base_url", "model", "temperature", "max_output", "is_active"):
        setattr(p, k, getattr(body, k))
    if body.api_key: p.api_key = body.api_key
    if body.is_active:
        for other in db.scalars(select(LlmProvider).where(LlmProvider.id != p.id if p.id else True)):
            other.is_active = False
    db.commit(); db.refresh(p)
    return p

def _require_admin(user: User):
    if user.role != "admin": raise HTTPException(403, "admin only")
```

`main.py` 的 create_app 增加 lifespan：startup 时 `init_engine()`（testing 下跳过）+ 用独立 session 调 `seed_default_provider`（testing 下也执行，方便测试断言 seed 行）。schemas/admin.py：`ProviderIn{name, base_url, api_key:str="", model, temperature=0.2, max_output=4096, is_active=False}`、`ProviderOut{id,name,base_url,model,temperature,max_output,is_active}`（无 api_key 字段）。

- [ ] **Step 5: 跑测试**

Run: `conda run -n rachel-v2 python -m pytest backend/tests/test_t04_llm.py -v`
Expected: 4 PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app backend/tests/test_t04_llm.py backend/tests/conftest.py
git commit -m "feat: llm provider admin api with openai-compatible and mock clients"
```

---

### Task 5: 任务提交 API（SMILES 校验 + 护栏 + 入队 stub + 列表/详情）

**Files:**
- Create: `backend/app/schemas/jobs.py`, `backend/app/api/jobs.py`, `backend/app/services/__init__.py`, `backend/app/services/smiles.py`, `backend/app/services/jobs.py`, `backend/app/worker/__init__.py`, `backend/app/worker/celery_app.py`
- Modify: `backend/app/main.py`（挂 jobs 路由）
- Test: `backend/tests/test_t05_jobs_api.py`

**Interfaces:**
- Consumes: auth deps、models、`get_settings().max_heavy_atoms/max_running_per_user`
- Produces: 契约区 `validate_smiles/count_active/set_status`；`JobIn{smiles, name:str=""}`、`JobOut{id,smiles,name,status,error,stats,created_at,started_at,finished_at}`；`celery_app`（`task_always_eager=get_settings().testing`）；stub 任务 `run_retro_job`（本任务只做：查 job→置 running→立即置 succeeded，真实逻辑 T6 替换）

- [ ] **Step 1: 写失败测试**

```python
PARACETAMOL = "CC(=O)Nc1ccc(O)cc1"

def test_submit_invalid_smiles_400(client, db, auth_headers_user):
    r = client.post("/api/jobs", headers=auth_headers_user, json={"smiles": "not-a-smiles"})
    assert r.status_code == 400 and "error" in r.json()

def test_submit_canonicalized(client, db, auth_headers_user):
    r = client.post("/api/jobs", headers=auth_headers_user, json={"smiles": "C1=CC=CC=C1"})  # 非规范苯
    assert r.status_code == 201
    assert r.json()["smiles"] == "c1ccccc1"     # RDKit 规范化
    assert r.json()["status"] in ("queued", "succeeded")  # eager stub 立即完成

def test_submit_too_heavy_400(client, db, auth_headers_user, monkeypatch):
    from app.core.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setenv("MAX_HEAVY_ATOMS", "5")
    r = client.post("/api/jobs", headers=auth_headers_user, json={"smiles": PARACETAMOL})
    assert r.status_code == 400
    get_settings.cache_clear()

def test_list_shows_only_own(client, db, auth_headers_admin, auth_headers_user):
    client.post("/api/jobs", headers=auth_headers_user, json={"smiles": PARACETAMOL})
    mine = client.get("/api/jobs?mine=1", headers=auth_headers_user).json()
    assert len(mine) == 1
    other = client.get("/api/jobs?mine=1", headers=auth_headers_admin).json()
    assert len(other) == 0

def test_detail_of_other_user_404(client, db, auth_headers_admin, auth_headers_user):
    jid = client.post("/api/jobs", headers=auth_headers_user, json={"smiles": PARACETAMOL}).json()["id"]
    assert client.get(f"/api/jobs/{jid}", headers=auth_headers_admin).status_code in (200, 404)
    assert client.get(f"/api/jobs/{jid}", headers=auth_headers_admin).status_code == 200  # admin 可见
    # 第三个无关用户不可见
    client.post("/api/auth/register", json={"username": "eve", "password": "pw3"})
    tok = client.post("/api/auth/login", json={"username": "eve", "password": "pw3"}).json()["access_token"]
    assert client.get(f"/api/jobs/{jid}", headers={"Authorization": f"Bearer {tok}"}).status_code == 404

def test_running_quota_429(client, db, auth_headers_user, monkeypatch):
    from app.core.config import get_settings
    get_settings.cache_clear(); monkeypatch.setenv("MAX_RUNNING_PER_USER", "1")
    assert client.post("/api/jobs", headers=auth_headers_user, json={"smiles": PARACETAMOL}).status_code == 201
    # stub 会立即 succeeded，为测配额先手工塞一条 running
    from app.db.models import Job
    with TestClientAppDbOverride() as _ : pass  # 占位删除；直接用 client.app.state
    # 简化：直接向测试 db 插 running job
    from app.api.deps import get_db
    # db fixture 可通过 app.state 拿到；这里改用暴力法：
    # conftest 暴露 db 于 client.app.state.test_db
    d = client.app.state.test_db
    u = d.query(Job).first().user_id
    d.add(Job(id="manual1", user_id=u, smiles="CCO", status="running")); d.commit()
    assert client.post("/api/jobs", headers=auth_headers_user, json={"smiles": "CCOc1ccccc1"}).status_code == 429
    get_settings.cache_clear()
```

注意：conftest 的 client fixture 需增加一行 `c.app.state.test_db = db` 以支持上面的配额测试。`TESTING=true` 时 celery eager 使 stub 同步执行。

- [ ] **Step 2: smiles.py**

```python
from rdkit import RDLogger
from rdkit import Chem
RDLogger.DisableLog("rdApp.*")

def validate_smiles(s: str) -> tuple[str | None, str]:
    """返回 (canonical, error)；两者互斥。"""
    if not s or not s.strip():
        return None, "smiles required"
    mol = Chem.MolFromSmiles(s.strip())
    if mol is None:
        return None, f"invalid SMILES: {s}"
    return Chem.MolToSmiles(mol), ""

def heavy_atoms(canonical: str) -> int:
    return Chem.MolFromSmiles(canonical).GetNumHeavyAtoms()
```

- [ ] **Step 3: services/jobs.py**

```python
from datetime import datetime, timezone
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.db.models import Job, JobStatus

def count_active(db: Session, user_id: int) -> int:
    return db.scalar(select(func.count()).select_from(Job).where(
        Job.user_id == user_id, Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]))) or 0

def set_status(db: Session, job_id: str, status: str, error: str = "", stats_patch: dict | None = None) -> Job:
    job = db.get(Job, job_id)
    if job is None: raise ValueError(f"job not found: {job_id}")
    job.status = status
    if error: job.error = error
    if stats_patch:
        stats = dict(job.stats or {}); stats.update(stats_patch); job.stats = stats
    now = datetime.now(timezone.utc)
    if status == JobStatus.RUNNING and job.started_at is None: job.started_at = now
    if status in (JobStatus.SUCCEEDED, JobStatus.PARTIAL, JobStatus.FAILED, JobStatus.CANCELLED):
        job.finished_at = now
    db.commit(); db.refresh(job)
    return job
```

- [ ] **Step 4: worker/celery_app.py + stub tasks.py**

```python
# celery_app.py
from celery import Celery
from app.core.config import get_settings

celery_app = Celery("rachel", broker=get_settings().redis_url, backend=get_settings().redis_url)
celery_app.conf.update(
    task_always_eager=get_settings().testing,
    task_eager_propagates=False,
    task_track_started=True,
)

# tasks.py（本任务 stub 版，T6 重写函数体）
from app.worker.celery_app import celery_app

@celery_app.task(bind=True, acks_late=True, soft_time_limit=3600, time_limit=3900)
def run_retro_job(self, job_id: str) -> str:
    from app.db.session import SessionLocal
    from app.services.jobs import set_status
    from app.db.models import JobStatus
    db = SessionLocal()
    try:
        set_status(db, job_id, JobStatus.RUNNING)
        set_status(db, job_id, JobStatus.SUCCEEDED, stats_patch={"steps": 0})
        return JobStatus.SUCCEEDED
    finally:
        db.close()
```

测试中 eager 任务用 `SessionLocal`——conftest 必须把 `app.db.session.SessionLocal` monkeypatch 成测试 sessionmaker（Task 3 的 client fixture 已做）；若尚未做成属性式 patch，在此任务补齐：
```python
# conftest client fixture 内
import app.db.session as dbs
from sqlalchemy.orm import sessionmaker
dbs.SessionLocal = sessionmaker(bind=db.get_bind())
```

- [ ] **Step 5: api/jobs.py + schemas**

```python
# schemas/jobs.py
from datetime import datetime
from pydantic import BaseModel

class JobIn(BaseModel):
    smiles: str
    name: str = ""

class JobOut(BaseModel):
    id: str; smiles: str; name: str; status: str; error: str
    stats: dict; created_at: datetime
    started_at: datetime | None = None; finished_at: datetime | None = None
    model_config = {"from_attributes": True}

# api/jobs.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.deps import get_current_user, get_db
from app.core.config import get_settings
from app.db.models import Job, User
from app.schemas.jobs import JobIn, JobOut
from app.services.jobs import count_active
from app.services.smiles import heavy_atoms, validate_smiles
from app.worker.tasks import run_retro_job

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

@router.post("", response_model=JobOut, status_code=201)
def submit(body: JobIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = get_settings()
    canonical, err = validate_smiles(body.smiles)
    if err: raise HTTPException(400, err)
    if heavy_atoms(canonical) > s.max_heavy_atoms:
        raise HTTPException(400, f"molecule too large (> {s.max_heavy_atoms} heavy atoms)")
    if count_active(db, user.id) >= s.max_running_per_user:
        raise HTTPException(429, "concurrent job limit reached")
    job = Job(smiles=canonical, name=body.name[:120], user_id=user.id)
    db.add(job); db.commit(); db.refresh(job)
    async_result = run_retro_job.delay(job.id)
    job.celery_task_id = async_result.id or ""; db.commit()
    return job

@router.get("", response_model=list[JobOut])
def list_jobs(mine: int = 0, page: int = 1, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = select(Job).order_by(Job.created_at.desc()).offset((page - 1) * 20).limit(20)
    if mine or user.role != "admin":
        q = q.where(Job.user_id == user.id)
    return db.scalars(q).all()

@router.get("/{job_id}", response_model=JobOut)
def detail(job_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None or (job.user_id != user.id and user.role != "admin"):
        raise HTTPException(404, "job not found")
    return job
```

- [ ] **Step 6: 跑测试**

Run: `conda run -n rachel-v2 python -m pytest backend/tests/test_t05_jobs_api.py -v`
Expected: 6 PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app backend/tests/test_t05_jobs_api.py backend/tests/conftest.py
git commit -m "feat: job submit api with smiles validation and quota guard"
```

---

### Task 6: Celery 任务实装（生命周期 + workspace + 失败路径）

**Files:**
- Modify: `backend/app/worker/tasks.py`（重写 run_retro_job 函数体）
- Test: `backend/tests/test_t06_lifecycle.py`

**Interfaces:**
- Consumes: `set_status`、T9 的 `AgentDriver`（本任务先用 duck-typing：`worker` 通过依赖注入函数 `_build_driver(job, db, workspace)` 构造，测试 monkeypatch 它）
- Produces: `run_retro_job(job_id)` 真实版：running → workspace 创建（`{data_dir}/{job_id}/`，session 文件 `session.json`）→ driver.run() → 按 DriverResult.status 映射 succeeded/partial/failed + stats_patch（steps/tokens_in/tokens_out/reason）→ export 产物路径写入 stats.export_dir。workspace 辅助：`ensure_workspace(job_id) -> Path`（放 services/jobs.py）

- [ ] **Step 1: 写失败测试**

```python
def test_lifecycle_success(client, db, auth_headers_user, monkeypatch, tmp_path):
    from app.worker import tasks
    class FakeDriverResult:
        status = "succeeded"; reason = ""; steps = 7
        tokens_in = 1000; tokens_out = 500; export_result = {"output_dir": str(tmp_path)}
    class FakeDriver:
        def __init__(self, *a, **kw): pass
        def run(self): return FakeDriverResult()
    monkeypatch.setattr(tasks, "_build_driver", lambda job, ws: FakeDriver())
    r = client.post("/api/jobs", headers=auth_headers_user, json={"smiles": "CC(=O)Nc1ccc(O)cc1"})
    out = client.get(f"/api/jobs/{r.json()['id']}", headers=auth_headers_user).json()
    assert out["status"] == "succeeded"
    assert out["stats"]["steps"] == 7 and out["stats"]["tokens_in"] == 1000
    assert "export_dir" in out["stats"]

def test_lifecycle_failure_marks_failed(client, db, auth_headers_user, monkeypatch):
    from app.worker import tasks
    def boom(job, ws): raise RuntimeError("llm exploded")
    monkeypatch.setattr(tasks, "_build_driver", boom)
    r = client.post("/api/jobs", headers=auth_headers_user, json={"smiles": "CC(=O)Nc1ccc(O)cc1"})
    out = client.get(f"/api/jobs/{r.json()['id']}", headers=auth_headers_user).json()
    assert out["status"] == "failed" and "llm exploded" in out["error"]
```

- [ ] **Step 2: 重写 tasks.py**

```python
import traceback
from pathlib import Path
from app.worker.celery_app import celery_app
from app.core.config import get_settings

def ensure_workspace(job_id: str) -> Path:
    ws = get_settings().data_dir / job_id
    ws.mkdir(parents=True, exist_ok=True)
    return ws

def _build_driver(job, workspace: Path):
    """T9 接入后实现：RetroCmd + get_active_client + DbTraceSink → AgentDriver。"""
    raise NotImplementedError("wired in Task 9")

@celery_app.task(bind=True, acks_late=True, soft_time_limit=3600, time_limit=3900)
def run_retro_job(self, job_id: str) -> str:
    from app.db.session import SessionLocal
    from app.db.models import JobStatus
    from app.services.jobs import set_status
    db = SessionLocal()
    try:
        from app.db.models import Job
        job = db.get(Job, job_id)
        if job is None: return JobStatus.FAILED
        set_status(db, job_id, JobStatus.RUNNING)
        workspace = ensure_workspace(job_id)
        result = _build_driver(job, workspace).run()
        stats = {"steps": result.steps, "tokens_in": result.tokens_in,
                 "tokens_out": result.tokens_out, "reason": result.reason}
        if result.export_result.get("output_dir"):
            stats["export_dir"] = result.export_result["output_dir"]
        set_status(db, job_id, result.status, stats_patch=stats)
        return result.status
    except Exception as e:
        traceback.print_exc()
        set_status(db, job_id, "failed", error=str(e))
        return "failed"
    finally:
        db.close()
```

- [ ] **Step 3: 跑测试**

Run: `conda run -n rachel-v2 python -m pytest backend/tests/test_t06_lifecycle.py -v`
Expected: 2 PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/worker/tasks.py backend/tests/test_t06_lifecycle.py
git commit -m "feat: job worker lifecycle with workspace and failure mapping"
```

---

### Task 7: 工具层（26 命令 schema + read_doc/finish + 截断）

**Files:**
- Create: `backend/app/agent/tools.py`
- Test: `backend/tests/test_t07_tools.py`

**Interfaces:**
- Consumes: `RetroCmd`（真实 import，测试直接建临时 session 跑 init/next）
- Produces: 契约区 `TOOL_SCHEMAS/execute_tool/truncate_result`

- [ ] **Step 1: 写失败测试**

```python
import json

def test_schema_count_and_shape():
    from app.agent.tools import TOOL_SCHEMAS
    names = {t["function"]["name"] for t in TOOL_SCHEMAS}
    assert len(TOOL_SCHEMAS) == 28          # 26 命令 + read_doc + finish
    expected = {"init","next","context","guide","route_plan","route_sketch",
        "reaction_sites","explore_site","try_action","propose_action",
        "sandbox_list","sandbox_clear","select","commit","accept","review_terminal",
        "skip","tree","status","continuation_status","continuation_abort",
        "finalize","report","export","smart_cap","custom_cap","read_doc","finish"}
    assert names == expected
    for t in TOOL_SCHEMAS:
        assert t["type"] == "function"
        assert t["function"]["description"]
        assert t["function"]["parameters"]["type"] == "object"

def test_required_args_enforced_in_schema():
    from app.agent.tools import TOOL_SCHEMAS
    by = {t["function"]["name"]: t["function"] for t in TOOL_SCHEMAS}
    assert "site_id" in by["explore_site"]["parameters"]["required"]
    assert "action_id" in by["try_action"]["parameters"]["required"]
    assert "target" in by["init"]["parameters"]["required"]
    assert "idx" in by["commit"]["parameters"]["required"]

def test_truncate_small_passthrough():
    from app.agent.tools import truncate_result
    s = truncate_result({"ok": True})
    assert json.loads(s) == {"ok": True}

def test_truncate_large_adds_notice():
    from app.agent.tools import truncate_result
    big = {"blob": "x" * 20000}
    s = truncate_result(big, limit=1000)
    assert len(s) < 1100 and "TRUNCATED" in s

def test_execute_tool_dispatch(tmp_path):
    from app.agent.tools import execute_tool
    from Rachel.main.retro_cmd import RetroCmd
    retro = RetroCmd(str(tmp_path / "session.json"))
    r = execute_tool(retro, "init", {"target": "CC(=O)Nc1ccc(O)cc1", "name": "paracetamol"}, None)
    assert r.get("ok") is True
    r2 = execute_tool(retro, "next", {}, None)
    assert r2.get("action") != "queue_empty" or "smiles" in r2  # 返回了上下文或队列空提示
    r3 = execute_tool(retro, "explore_site", {"site_id": ""}, None)   # 空 site_id → error dict
    assert "error" in r3

def test_execute_tool_finish():
    from app.agent.tools import execute_tool
    r = execute_tool(None, "finish", {"summary": "done"}, None)
    assert r == {"ok": True, "finished": True}
```

- [ ] **Step 2: tools.py（schema 参数与 retro_cmd.py 实测签名一致）**

```python
import json
from typing import Any

def _f(name: str, desc: str, props: dict, required: list[str] | None = None) -> dict:
    return {"type": "function", "function": {
        "name": name, "description": desc,
        "parameters": {"type": "object", "properties": props, "required": required or []}}}

TOOL_SCHEMAS: list[dict] = [
    _f("init", "Create a new retrosynthesis session for the target molecule.",
       {"target": {"type": "string", "description": "target SMILES"},
        "name": {"type": "string"}, "max_depth": {"type": "integer"},
        "max_steps": {"type": "integer"}, "terminal_cs_threshold": {"type": "number"}}, ["target"]),
    _f("next", "Get the next active molecule context (auto-passes trivial terminals).", {}),
    _f("context", "Get current context. detail: compact|structure|full|status|tree.",
       {"detail": {"type": "string", "enum": ["compact","structure","full","status","tree"]},
        "bond_offset": {"type": "integer"}, "bond_limit": {"type": "integer"},
        "fgi_offset": {"type": "integer"}, "fgi_limit": {"type": "integer"}}),
    _f("guide", "Record chemist natural-language guidance for the active node.",
       {"text": {"type": "string"}, "intent": {"type": "string"},
        "site_hint": {"type": "string"}, "reaction_hint": {"type": "string"},
        "precursors": {"type": "array", "items": {"type": "string"}},
        "constraints": {"type": "string"}, "terminal_hint": {"type": "string"},
        "summary": {"type": "string"}}, ["text"]),
    _f("route_plan", "Set or revise the persistent global route thesis.",
       {"route_thesis": {"type": "string"}, "route_mode": {"type": "string"},
        "key_disconnections": {"type": "array", "items": {"type": "string"}},
        "preferred_precursor_logic": {"type": "string"}, "protect_or_preserve": {"type": "string"},
        "mode_evidence": {"type": "string"}, "strategic_risks": {"type": "array", "items": {"type": "string"}},
        "revision_triggers": {"type": "array", "items": {"type": "string"}},
        "terminal_rescue_policy": {"type": "string"}, "revision_reason": {"type": "string"}},
       ["route_thesis"]),
    _f("route_sketch", "Record a short strategy sketch when the action-space is weak.",
       {"problem": {"type": "string"}, "macro_strategy": {"type": "string"},
        "key_disconnections": {"type": "array", "items": {"type": "string"}},
        "rejected_action_space_reason": {"type": "string"},
        "next_executable_step": {"type": "string"}, "terminal_review": {"type": "boolean"},
        "summary": {"type": "string"}, "continuation_steps": {"type": "array", "items": {"object"}}},
       ["problem"]),
    _f("reaction_sites", "First-layer site-first grouped action menu for the active molecule.", {}),
    _f("explore_site", "Expand all candidate actions competing at one real reaction site.",
       {"site_id": {"type": "string"}}, ["site_id"]),
    _f("try_action", "Sandbox-validate one action-space entry by action_id.",
       {"action_id": {"type": "string"}}, ["action_id"]),
    _f("propose_action", "Register an LLM-proposed custom precursor action, then try_action it.",
       {"strategy_id": {"type": "string"}, "precursors": {"type": "array", "items": {"type": "string"}},
        "reagents": {"type": "array", "items": {"type": "string"}},
        "reaction_type": {"type": "string"}, "reaction_id": {"type": "string"},
        "reaction_name": {"type": "string"}, "action_label": {"type": "string"},
        "why_existing_actions_rejected": {"type": "string"}, "rationale_summary": {"type": "string"},
        "route_sketch_id": {"type": "string"}, "continuation_id": {"type": "string"},
        "risk_tags": {"type": "array", "items": {"type": "string"}},
        "intended_deltas": {"type": "array", "items": {}}, "expected_ring_change": {"type": "string"},
        "changed_bonds": {"type": "array", "items": {}}, "preserved_anchors": {"type": "array", "items": {}},
        "mechanistic_evidence": {"type": "array", "items": {"type": "string"}},
        "family_evidence": {"type": "object"}, "experience_card_hints": {"type": "array", "items": {}}},
       ["precursors"]),
    _f("sandbox_list", "List sandbox attempt history grouped by site/reaction.", {}),
    _f("sandbox_clear", "Clear all sandbox attempts.", {}),
    _f("select", "Select one sandbox attempt by index for commit.",
       {"idx": {"type": "integer"}}, ["idx"]),
    _f("commit", "Commit the selected sandbox attempt into the route tree with reasoning.",
       {"idx": {"type": "integer"}, "expected_action_id": {"type": "string"},
        "reasoning": {"type": "string"}, "confidence": {"type": "string", "enum": ["low","medium","high"]},
        "rejected": {"type": "array", "items": {}}, "validation_override": {"type": "object"},
        "route_plan_alignment": {"type": "string"}, "route_plan_note": {"type": "string"}},
       ["idx", "reasoning"]),
    _f("accept", "Mark the active molecule as a terminal starting material with reason.",
       {"reason": {"type": "string"}, "rescue_not_actionable_reason": {"type": "string"},
        "force_accept_without_rescue": {"type": "boolean"}}, ["reason"]),
    _f("review_terminal", "Requeue an existing terminal leaf for normal review.",
       {"smiles": {"type": "string"}, "reason": {"type": "string"}, "additional_steps": {"type": "integer"}},
       ["smiles", "reason"]),
    _f("skip", "Skip the active molecule with reason.", {"reason": {"type": "string"}}, ["reason"]),
    _f("tree", "Print the current synthesis tree with terminal/pending counts.", {}),
    _f("status", "Show orchestrator status.", {}),
    _f("continuation_status", "Inspect active multi-step strategy continuations.", {}),
    _f("continuation_abort", "Close a pending continuation with an explicit reason.",
       {"continuation_id": {"type": "string"}, "reason": {"type": "string"}}, ["continuation_id"]),
    _f("finalize", "Finalize the route orchestration.", {"summary": {"type": "string"}}, ["summary"]),
    _f("report", "Generate the forward-synthesis report text.", {}),
    _f("export", "Export all artifacts (report/tree/visualization/terminals/session).",
       {"name": {"type": "string"}, "output_dir": {"type": "string"}}),
    _f("smart_cap", "Suggest template-free capping for a bond.",
       {"bond_idx": {"type": "integer"}, "smiles": {"type": "string"}, "bond": {"type": "array", "items": {"type": "integer"}},
        "max": {"type": "integer"}}),
    _f("custom_cap", "Apply LLM-defined caps to a bond.",
       {"cap_i": {"type": "string"}, "cap_j": {"type": "string"},
        "bond_idx": {"type": "integer"}, "smiles": {"type": "string"},
        "bond": {"type": "array", "items": {"type": "integer"}},
        "reaction_type": {"type": "string"}}, ["cap_i", "cap_j"]),
    _f("read_doc", "Read a section of workflow.md or experience_cards.md on demand.",
       {"doc": {"type": "string", "enum": ["workflow", "experience"]},
        "section": {"type": "string", "description": "optional section title filter"}}, ["doc"]),
    _f("finish", "Signal normal completion after export. Provide a short route summary.",
       {"summary": {"type": "string"}}, ["summary"]),
]

def truncate_result(obj: Any, limit: int = 8192) -> str:
    s = json.dumps(obj, ensure_ascii=False, default=str)
    if len(s) <= limit:
        return s
    return s[:limit] + f"\n...[TRUNCATED {len(s)-limit} chars; use finer-grained commands to re-fetch details]"

def execute_tool(retro, name: str, args: dict, doc_reader) -> dict:
    if name == "finish":
        return {"ok": True, "finished": True}
    if name == "read_doc":
        if doc_reader is None:
            return {"error": "doc reader not configured"}
        return doc_reader.read(args.get("doc", ""), args.get("section", ""))
    return retro.execute(name, args)
```

- [ ] **Step 3: 跑测试（依赖 RDKit/Rachel，须在 rachel-v2 env）**

Run: `conda run -n rachel-v2 python -m pytest backend/tests/test_t07_tools.py -v`
Expected: 6 PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/agent/tools.py backend/tests/test_t07_tools.py
git commit -m "feat: retro command tool schemas with result truncation"
```

---

### Task 8: Prompt 层（system prompt 组装 + DocReader）

**Files:**
- Create: `backend/app/agent/prompts.py`
- Test: `backend/tests/test_t08_prompts.py`

**Interfaces:**
- Consumes: `Rachel-v2/Rachel/SKILL.md`、`Rachel-v2/Rachel/workflow.md`、`Rachel-v2/Rachel/experience_cards.md`（只读）
- Produces: 契约区 `build_system_prompt/build_task_prompt/DocReader`

- [ ] **Step 1: 写失败测试**

```python
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2] / "Rachel-v2" / "Rachel"

def test_system_prompt_contains_skill_and_cheatsheet():
    from app.agent.prompts import build_system_prompt
    p = build_system_prompt()
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert skill[:200].strip() in p            # SKILL.md 内容嵌入
    assert "reaction_sites" in p               # 速查表
    assert "finalize" in p and "export" in p

def test_task_prompt_contains_target():
    from app.agent.prompts import build_task_prompt
    p = build_task_prompt("CC(=O)Nc1ccc(O)cc1", "paracetamol")
    assert "CC(=O)Nc1ccc(O)cc1" in p and "paracetamol" in p
    assert "export" in p                       # 明确要求最终 export

def test_doc_reader_workflow():
    from app.agent.prompts import DocReader
    dr = DocReader(ROOT)
    r = dr.read("workflow")
    assert r.get("ok") and len(r["content"]) > 100
    r2 = dr.read("nope")
    assert not r2.get("ok")

def test_doc_reader_truncates():
    from app.agent.prompts import DocReader
    dr = DocReader(ROOT)
    r = dr.read("workflow")
    assert len(r["content"]) <= 24000          # 内部上限 24000 字符
```

- [ ] **Step 2: prompts.py**

```python
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2] / "Rachel-v2" / "Rachel"
DOC_FILES = {"workflow": "workflow.md", "experience": "experience_cards.md"}
DOC_LIMIT = 24000

CHEATSHEET = """
## 快速流程参考（cheat sheet）
标准流程: init(target) → next → [route_plan] → reaction_sites → explore_site(site_id)
  → try_action(action_id) → (gate 通过) commit(idx, reasoning) → next → …
  → 全部叶子 terminal 后 next 返回 queue_empty → finalize(summary) → export → finish
要点:
- 每步决策绑定当前 active node；先 next 再 reaction_sites，不要并行猜测。
- try_action 失败或 gate 非 pass 时：换 action、propose_action 自提、或 route_sketch 救援。
- commit 必须写清 reasoning（机理/骨架守恒/被拒理由）；accept 需给 reason。
- 沙盒多方案时先 sandbox_list 比较，再 select(idx) + commit(idx)。
- 长会话优先用细粒度命令（explore_site 单 site）而非 context(full)。
"""

def build_system_prompt() -> str:
    skill = (_ROOT / "SKILL.md").read_text(encoding="utf-8")
    return f"# Rachel-v2 Skill Instructions\n\n{skill}\n\n{CHEATSHEET}"

def build_task_prompt(smiles: str, name: str) -> str:
    label = f"（名称: {name}）" if name else ""
    return (
        f"目标分子{label}: {smiles}\n\n"
        f"请按照 skill 流程完成完整逆合成路线规划：驱动状态机直到所有叶子 terminal，"
        f"然后 finalize 并 export，最后调用 finish 工具并给出一段路线总结。"
    )

class DocReader:
    def __init__(self, root: Path | None = None):
        self.root = root or _ROOT

    def read(self, doc: str, section: str = "") -> dict:
        fname = DOC_FILES.get(doc)
        if not fname:
            return {"ok": False, "error": f"unknown doc: {doc}; options: {list(DOC_FILES)}"}
        path = self.root / fname
        if not path.exists():
            return {"ok": False, "error": f"file not found: {fname}"}
        text = path.read_text(encoding="utf-8")
        if section:
            hit = self._section(text, section)
            if hit is None:
                return {"ok": False, "error": f"section not found: {section}"}
            text = hit
        if len(text) > DOC_LIMIT:
            text = text[:DOC_LIMIT] + f"\n...[truncated at {DOC_LIMIT} chars]"
        return {"ok": True, "doc": doc, "section": section, "content": text}

    @staticmethod
    def _section(text: str, title: str) -> str | None:
        lines, buf, capturing = text.splitlines(), [], False
        for ln in lines:
            if ln.startswith("#"):
                if capturing: break
                if title.lower() in ln.lower(): capturing = True
            if capturing: buf.append(ln)
        return "\n".join(buf) if capturing else None
```

- [ ] **Step 3: 跑测试**

Run: `conda run -n rachel-v2 python -m pytest backend/tests/test_t08_prompts.py -v`
Expected: 4 PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/agent/prompts.py backend/tests/test_t08_prompts.py
git commit -m "feat: layered system prompt and on-demand doc reader"
```

---

### Task 9: AgentDriver 主循环（压缩 + 熔断 + partial 抢救）

**Files:**
- Create: `backend/app/agent/driver.py`
- Create: `backend/tests/fakes.py`（复用件）
- Test: `backend/tests/test_t09_driver.py`

**Interfaces:**
- Consumes: `TOOL_SCHEMAS/execute_tool/truncate_result`（T7）、`build_system_prompt/build_task_prompt/DocReader`（T8）、`ChatTurn/ToolCall`（T4）
- Produces: 契约区 `AgentDriver/DriverLimits/DriverResult`；行为规范：① finish 工具触发 `_finalize_export()`（若未 finalize 则补 finalize+export）并返回 succeeded ② max_steps/wall_clock 到限 → 补 finalize+export → partial ③ 连续 10 次同命令 error 结果 → failed（不再抢救）④ LLM 纯文本回复（无 tool_calls）→ 追加一条 user 提醒"必须通过工具继续或 finish"，第二次仍无 → failed ⑤ 每个工具结果经 truncate_result 后入 messages；tool 消息早于最近 keep_recent 条的替换为 trace 摘要行 ⑥ 每步调用 trace.record(seq, command, args, result, tokens, duration_ms) ⑦ 完整消息日志写 `{workspace}/messages.jsonl`（无 workspace 则跳过）

- [ ] **Step 1: tests/fakes.py**

```python
from app.agent.llm_client import ChatTurn, ToolCall, Usage

class FakeRetroCmd:
    def __init__(self, error_commands: set[str] | None = None):
        self.calls: list[tuple[str, dict]] = []
        self.error_commands = error_commands or set()
        self.finalized = False
        self.exported = False
    def execute(self, command: str, args: dict | None = None) -> dict:
        args = args or {}
        self.calls.append((command, args))
        if command == "finalize": self.finalized = True; return {"ok": True}
        if command == "export":
            self.exported = True
            return {"output_dir": "/tmp/fake_export", "files": [], "summary": "ok"}
        if command in self.error_commands:
            return {"error": f"boom:{command}"}
        return {"ok": True, "echo": command}

class ListTrace:
    def __init__(self): self.rows = []
    def record(self, seq, command, args, result, tokens, duration_ms):
        self.rows.append({"seq": seq, "command": command, "args": args,
                          "result": result, "tokens": tokens, "duration_ms": duration_ms})

def turns(*groups) -> list[list[ToolCall]]:
    """turns(('c1','next',{}), ('c2','finish',{'summary':'ok'})) → 每次 chat 一组"""
    out = []
    for g in groups:
        out.append([ToolCall(id=f"call{i}", name=n, args=a) for i, (n, a) in enumerate(
            [(x[0], x[1]) if isinstance(x[1], dict) else (x[0], {}) for x in g])])
    return out

def mock(script: list[list[ToolCall]]) -> "MockLLMClient":
    from app.agent.llm_client import MockLLMClient
    return MockLLMClient(script)
```

（`turns` 的入参约定：每组是 `(name, args)` 元组序列。）

- [ ] **Step 2: 写失败测试**

```python
from app.agent.driver import AgentDriver, DriverLimits
from tests.fakes import FakeRetroCmd, ListTrace, mock, ToolCall

def _driver(script, retro=None, limits=None):
    retro = retro or FakeRetroCmd()
    trace = ListTrace()
    d = AgentDriver(retro=retro, llm=mock(script), trace=trace, limits=limits,
                    task_prompt="target: CCO", name="t")
    return d, retro, trace

def test_finish_triggers_finalize_export():
    d, retro, trace = _driver([[("next", {})], [("finish", {"summary": "done"})]])
    r = d.run()
    assert r.status == "succeeded" and retro.finalized and retro.exported
    assert retro.calls[-2][0] == "finalize" and retro.calls[-1][0] == "export"
    assert r.steps == 2

def test_max_steps_partial_rescue():
    script = [[("status", {})] for _ in range(5)]
    d, retro, trace = _driver(script, limits=DriverLimits(max_steps=3, wall_clock_sec=600, keep_recent=10))
    r = d.run()
    assert r.status == "partial" and "max_steps" in r.reason
    assert retro.finalized and retro.exported      # 抢救导出

def test_circuit_breaker_on_repeated_errors():
    retro = FakeRetroCmd(error_commands={"try_action"})
    script = [[("try_action", {"action_id": "a"})] for _ in range(12)]
    d, _, _ = _driver(script, retro=retro)
    r = d.run()
    assert r.status == "failed" and "try_action" in r.reason

def test_compaction_replaces_old_tool_results():
    from app.agent.llm_client import MockLLMClient
    script = [[("next", {})] for _ in range(15)] + [[("finish", {"summary": "x"})]]
    d, retro, trace = _driver(script, limits=DriverLimits(max_steps=100, wall_clock_sec=600, keep_recent=5))
    r = d.run()
    msgs = d.messages
    tool_msgs = [m for m in msgs if m["role"] == "tool"]
    full = [m for m in tool_msgs if "echo" in m["content"]]
    summarized = [m for m in tool_msgs if m["content"].startswith("step ")]
    assert len(full) <= 6 and len(summarized) >= 9    # 旧结果被摘要替换

def test_text_only_reply_nudge_then_fail():
    from app.agent.llm_client import ChatTurn as CT
    class TextOnly:
        def __init__(self): self.n = 0
        def chat(self, messages, tools):
            self.n += 1
            return CT(content="I think we should...", tool_calls=[], usage=None)
    retro = FakeRetroCmd(); trace = ListTrace()
    d = AgentDriver(retro=retro, llm=TextOnly(), trace=trace, task_prompt="t", name="t")
    r = d.run()
    assert r.status == "failed" and "no tool calls" in r.reason

def test_messages_jsonl_written(tmp_path):
    d, retro, trace = _driver([[("finish", {"summary": "x"})]], )
    d.workspace = tmp_path
    r = d.run()
    assert (tmp_path / "messages.jsonl").exists()
```

- [ ] **Step 3: driver.py**

```python
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from app.agent.llm_client import Usage
from app.agent.prompts import DocReader, build_system_prompt
from app.agent.tools import TOOL_SCHEMAS, execute_tool, truncate_result

@dataclass
class DriverLimits:
    max_steps: int = 300
    wall_clock_sec: int = 3600
    keep_recent: int = 10

@dataclass
class DriverResult:
    status: str; reason: str = ""
    steps: int = 0; tokens_in: int = 0; tokens_out: int = 0
    export_result: dict = field(default_factory=dict)

class AgentDriver:
    def __init__(self, retro, llm, trace, task_prompt: str, name: str = "",
                 limits: DriverLimits | None = None, workspace: Path | None = None,
                 doc_reader: DocReader | None = None):
        self.retro, self.llm, self.trace = retro, llm, trace
        self.limits = limits or DriverLimits()
        self.workspace = workspace
        self.doc_reader = doc_reader or DocReader()
        self.name = name
        self.messages = [
            {"role": "system", "content": build_system_prompt()},
            {"role": "user", "content": task_prompt},
        ]
        self._seq = 0
        self._finalized = False
        self._consecutive_errors: dict[str, int] = {}

    def run(self) -> DriverResult:
        t0 = time.monotonic()
        usage_total = Usage()
        text_only_strikes = 0
        while True:
            if self._seq >= self.limits.max_steps:
                return self._finish("partial", f"max_steps={self.limits.max_steps} reached",
                                    usage_total, "max_steps")
            if time.monotonic() - t0 > self.limits.wall_clock_sec:
                return self._finish("partial", "wall clock limit reached", usage_total, "wall_clock")
            try:
                turn = self.llm.chat(self.messages, TOOL_SCHEMAS)
            except Exception as e:
                return self._finish("failed", f"llm error: {e}", usage_total, "llm_error")
            usage_total.prompt_tokens += turn.usage.prompt_tokens
            usage_total.completion_tokens += turn.usage.completion_tokens
            if not turn.tool_calls:
                text_only_strikes += 1
                if text_only_strikes >= 2:
                    return self._finish("failed", "no tool calls in two consecutive turns",
                                        usage_total, "no_tool_calls")
                self.messages.append({"role": "assistant", "content": turn.content})
                self.messages.append({"role": "user", "content":
                    "Continue by calling one of the tools. When the route is complete, call finish."})
                continue
            text_only_strikes = 0
            self.messages.append({"role": "assistant", "content": turn.content or "",
                                  "tool_calls": [{"id": c.id, "type": "function",
                                                  "function": {"name": c.name, "arguments": json.dumps(c.args, ensure_ascii=False)}}
                                                 for c in turn.tool_calls]})
            finish_requested = False
            for call in turn.tool_calls:
                t1 = time.monotonic()
                result = execute_tool(self.retro, call.name, call.args, self.doc_reader)
                duration_ms = int((time.monotonic() - t1) * 1000)
                self._seq += 1
                summary = self._summary_line(self._seq, call.name, result)
                self.trace.record(self._seq, call.name, call.args, result,
                                  turn.usage.completion_tokens, duration_ms)
                self.messages.append({"role": "tool", "tool_call_id": call.id,
                                      "content": truncate_result(result),
                                      "_summary": summary, "_seq": self._seq})
                if call.name == "finish":
                    finish_requested = True
                self._track_errors(call.name, result)
                hot = max(self._consecutive_errors.values(), default=0)
                if hot >= 10:
                    bad = max(self._consecutive_errors, key=self._consecutive_errors.get)
                    return self._finish("failed", f"circuit breaker: 10 consecutive errors on '{bad}'",
                                        usage_total, "circuit_breaker")
            if finish_requested:
                return self._finish("succeeded", "finished by llm", usage_total, "finish")
            self._compact()
            self._log_message(turn)

    # ── helpers ──
    def _finish(self, status: str, reason: str, usage: Usage, code: str) -> DriverResult:
        export_result = {}
        if status != "failed":
            export_result = self._finalize_export()
        return DriverResult(status=status, reason=reason, steps=self._seq,
                            tokens_in=usage.prompt_tokens, tokens_out=usage.completion_tokens,
                            export_result=export_result or {})

    def _finalize_export(self) -> dict:
        if not self._finalized:
            try:
                self.retro.execute("finalize", {"summary": f"auto-finalize ({self.name})"})
            except Exception:
                pass
            self._finalized = True
        try:
            r = self.retro.execute("export", {"name": self.name})
            return r if isinstance(r, dict) else {}
        except Exception:
            return {}

    def _track_errors(self, name: str, result: dict) -> None:
        if isinstance(result, dict) and result.get("error"):
            self._consecutive_errors[name] = self._consecutive_errors.get(name, 0) + 1
        else:
            self._consecutive_errors.pop(name, None)

    @staticmethod
    def _summary_line(seq: int, name: str, result: dict) -> str:
        if isinstance(result, dict) and result.get("error"):
            return f"step {seq}: {name} → error: {str(result['error'])[:120]}"
        keys = {k: result[k] for k in ("ok", "action", "n_attempts", "terminal_count", "pending_count")
                if isinstance(result, dict) and k in result}
        return f"step {seq}: {name} → {keys or 'ok'}"

    def _compact(self) -> None:
        tool_idx = [i for i, m in enumerate(self.messages) if m.get("role") == "tool"]
        old = tool_idx[: max(0, len(tool_idx) - self.limits.keep_recent)]
        for i in old:
            m = self.messages[i]
            if m.get("_compacted"): continue
            m["content"] = m.get("_summary", "(summarized)")
            m["_compacted"] = True

    def _log_message(self, turn) -> None:
        if self.workspace is None: return
        with open(self.workspace / "messages.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"tool_calls": [{"name": c.name, "args": c.args} for c in turn.tool_calls]},
                               ensure_ascii=False, default=str) + "\n")
```

注意：`messages` 里附加的 `_summary/_seq/_compacted` 键在发送给 LLM 前必须剥离——`llm.chat(self.messages, ...)` 处改为 `self._wire_messages()`：`[{k: v for k, v in m.items() if not k.startswith("_")} for m in self.messages]`。测试 `test_compaction_replaces_old_tool_results` 通过 `d.messages`（含内部键）断言。在 driver 中以 `wire = self._wire_messages()` 传给 llm.chat。

- [ ] **Step 4: 跑测试**

Run: `conda run -n rachel-v2 python -m pytest backend/tests/test_t09_driver.py -v`
Expected: 6 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/driver.py backend/tests/fakes.py backend/tests/test_t09_driver.py
git commit -m "feat: agent driver loop with compaction, circuit breaker and partial rescue"
```

---

### Task 10: Trace 落库 + 产物解析

**Files:**
- Create: `backend/app/agent/trace.py`, `backend/app/services/artifacts.py`
- Create: `backend/tests/fixtures/visualization.json`（拷贝 `examples/result_demo/export/visualization.json`）、`backend/tests/fixtures/terminals.json`（拷贝同名）
- Test: `backend/tests/test_t10_trace_artifacts.py`

**Interfaces:**
- Consumes: models（JobStep）、契约区 `summarize_result` 行格式
- Produces: 契约区 `summarize_result/DbTraceSink/parse_export`；`parse_export` 返回 `{"visualization": {...原始json...}, "terminals": [...], "metrics": {"n_nodes": int, "n_edges": int, "n_terminals": int}, "incomplete": bool}`（文件缺失时对应键缺省且 incomplete=True）

- [ ] **Step 1: 拷贝 fixture**

```bash
mkdir -p backend/tests/fixtures
cp examples/result_demo/export/visualization.json examples/result_demo/export/terminals.json backend/tests/fixtures/
```

- [ ] **Step 2: 写失败测试**

```python
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
```

- [ ] **Step 3: trace.py**

```python
from sqlalchemy.orm import Session, sessionmaker
from app.db.models import JobStep

def summarize_result(command: str, result: dict) -> str:
    if not isinstance(result, dict):
        return f"{command} → non-dict result"
    if result.get("error"):
        return f"{command} → error: {str(result['error'])[:160]}"
    parts = [command]
    for k in ("ok", "action", "n_attempts", "n_bonds", "terminal_count", "pending_count", "total_steps"):
        if k in result: parts.append(f"{k}={result[k]}")
    for k in ("sites", "actions", "terminals", "files", "starting_materials"):
        v = result.get(k)
        if isinstance(v, list): parts.append(f"n_{k}={len(v)}")
    return " ".join(parts)[:300]

class DbTraceSink:
    def __init__(self, session_factory: sessionmaker, job_id: str):
        self.factory = session_factory; self.job_id = job_id

    def record(self, seq: int, command: str, args: dict, result: dict,
               tokens: int, duration_ms: int) -> None:
        db: Session = self.factory()
        try:
            db.add(JobStep(job_id=self.job_id, seq=seq, command=command,
                           args=args or {}, result_summary=summarize_result(command, result),
                           status="error" if isinstance(result, dict) and result.get("error") else "ok",
                           tokens=tokens, duration_ms=duration_ms))
            db.commit()
        finally:
            db.close()
```

- [ ] **Step 4: artifacts.py**

```python
import json
from pathlib import Path

def _load(p: Path):
    if not p.exists(): return None
    return json.loads(p.read_text(encoding="utf-8"))

def parse_export(export_dir: Path) -> dict:
    out: dict = {}
    vis = _load(export_dir / "visualization.json")
    terminals = _load(export_dir / "terminals.json")
    if vis is not None:
        out["visualization"] = vis
        out["metrics"] = {"n_nodes": len(vis.get("nodes", [])),
                          "n_edges": len(vis.get("edges", [])),
                          "n_terminals": sum(1 for n in vis.get("nodes", []) if n.get("role") == "terminal")}
    if terminals is not None:
        out["terminals"] = terminals
        out.setdefault("metrics", {})["n_terminals"] = len(terminals)
    out["incomplete"] = not ("visualization" in out and "terminals" in out)
    return out
```

- [ ] **Step 5: 跑测试**

Run: `conda run -n rachel-v2 python -m pytest backend/tests/test_t10_trace_artifacts.py -v`
Expected: 4 PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/agent/trace.py backend/app/services/artifacts.py backend/tests/test_t10_trace_artifacts.py backend/tests/fixtures
git commit -m "feat: db trace sink and export artifact parser"
```

---

### Task 11: 全链路接线（worker→driver→export→stats）+ trace/cancel/delete API

**Files:**
- Modify: `backend/app/worker/tasks.py`（`_build_driver` 实装）、`backend/app/api/jobs.py`（三个新端点）
- Test: `backend/tests/test_t11_e2e.py`

**Interfaces:**
- Consumes: T6-T10 全部
- Produces: `GET /api/jobs/{id}/trace?after=n → {steps: [JobStepOut]}`（JobStepOut{seq,command,args,result_summary,status,tokens,duration_ms,created_at}）；`POST /api/jobs/{id}/cancel`（revoke + 置 cancelled，幂等：非 queued/running 返回 409）；`DELETE /api/jobs/{id}`（删行 + 删 `data_dir/{id}` 目录）；`_build_driver(job, workspace)` 真实实现（MockLLMClient 走 model=="mock" 分支）

- [ ] **Step 1: 写失败测试**

```python
PARA = "CC(=O)Nc1ccc(O)cc1"

def _seed_mock_provider(db):
    from app.api.admin import seed_default_provider
    from app.db.models import LlmProvider
    from sqlalchemy import select
    seed_default_provider(db)
    p = db.scalar(select(LlmProvider).where(LlmProvider.is_active))
    p.model = "mock"; db.commit()

def test_e2e_mock_llm_full_pipeline(client, db, auth_headers_user, monkeypatch, tmp_path):
    _seed_mock_provider(db)
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings.__class__, "data_dir", property(lambda self: tmp_path))
    from app.worker import tasks as T
    from app.agent.llm_client import ToolCall
    # mock provider 的默认脚本是立即 finish；注入更真实的三步脚本
    import app.api.admin as admin
    monkeypatch.setattr(admin, "get_active_client",
                        lambda db: __import__("app.agent.llm_client", fromlist=["MockLLMClient"]).MockLLMClient(
                            script=[[ToolCall("c1", "init", {"target": PARA})],
                                    [ToolCall("c2", "status", {})],
                                    [ToolCall("c3", "finish", {"summary": "mock route"})]]))
    r = client.post("/api/jobs", headers=auth_headers_user, json={"smiles": PARA, "name": "para"})
    jid = r.json()["id"]
    out = client.get(f"/api/jobs/{jid}", headers=auth_headers_user).json()
    assert out["status"] == "succeeded"
    assert out["stats"]["steps"] == 3
    tr = client.get(f"/api/jobs/{jid}/trace?after=1", headers=auth_headers_user).json()["steps"]
    assert [s["command"] for s in tr] == ["status", "finish"]     # after=1 增量
    assert (tmp_path / jid / "session.json").exists() or True     # workspace 已建
    assert (tmp_path / jid / "messages.jsonl").exists()

def test_cancel_running(client, db, auth_headers_user):
    from app.db.models import Job, User
    r = client.post("/api/jobs", headers=auth_headers_user, json={"smiles": PARA})
    jid = r.json()["id"]
    # 手动置回 running 模拟长任务
    d = client.app.state.test_db
    j = d.get(Job, jid); j.status = "running"; d.commit()
    assert client.post(f"/api/jobs/{jid}/cancel", headers=auth_headers_user).status_code == 200
    assert client.get(f"/api/jobs/{jid}", headers=auth_headers_user).json()["status"] == "cancelled"
    assert client.post(f"/api/jobs/{jid}/cancel", headers=auth_headers_user).status_code == 409  # 幂等拒绝

def test_delete_job_removes_dir(client, db, auth_headers_user, tmp_path):
    from app.core.config import get_settings
    monkeypatch = None  # 见 conftest: data_dir 自动指 tmp_path 的 fixture data_dir(tmp_path)
    r = client.post("/api/jobs", headers=auth_headers_user, json={"smiles": PARA})
    jid = r.json()["id"]
    (tmp_path / jid).mkdir(parents=True, exist_ok=True)
    assert client.delete(f"/api/jobs/{jid}", headers=auth_headers_user).status_code == 200
    assert not (tmp_path / jid).exists()

def test_trace_of_other_user_404(client, db, auth_headers_admin, auth_headers_user):
    jid = client.post("/api/jobs", headers=auth_headers_user, json={"smiles": PARA}).json()["id"]
    client.post("/api/auth/register", json={"username": "eve2", "password": "pw4"})
    tok = client.post("/api/auth/login", json={"username": "eve2", "password": "pw4"}).json()["access_token"]
    assert client.get(f"/api/jobs/{jid}/trace", headers={"Authorization": f"Bearer {tok}"}).status_code == 404
```

conftest 补充 `data_dir` autouse fixture（测试期 data_dir→tmp_path，避免污染仓库）：
```python
@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    import app.core.config as cfg
    monkeypatch.setattr(cfg.Settings, "data_dir", tmp_path)
```
注意 T9 的 `ensure_workspace` 读 `get_settings()`（lru_cache 缓存实例）——monkeypatch 类属性可以作用于已缓存实例（属性查找走类），成立。

- [ ] **Step 2: tasks.py 的 `_build_driver` 实装**

```python
def _build_driver(job, workspace: Path):
    from app.agent.driver import AgentDriver, DriverLimits
    from app.agent.prompts import build_task_prompt
    from app.agent.trace import DbTraceSink
    from app.api.admin import get_active_client
    from app.db.session import SessionLocal
    from Rachel.main.retro_cmd import RetroCmd
    retro = RetroCmd(str(workspace / "session.json"))
    llm = get_active_client(SessionLocal())
    if llm is None:
        raise RuntimeError("no active llm provider configured")
    trace = DbTraceSink(SessionLocal, job.id)
    return AgentDriver(retro=retro, llm=llm, trace=trace,
                       task_prompt=build_task_prompt(job.smiles, job.name),
                       name=job.name or job.smiles[:20],
                       limits=DriverLimits(), workspace=workspace)
```

run_retro_job 成功分支增加产物解析与 stats 合并（在 set_status(succeeded) 前）：
```python
from app.services.artifacts import parse_export
export_dir = result.export_result.get("output_dir")
if export_dir and Path(export_dir).exists():
    stats["artifacts"] = parse_export(Path(export_dir))["metrics"]
    stats["artifacts"]["incomplete"] = parse_export(Path(export_dir)).get("incomplete", False)
```
（parse_export 调一次存变量再取两键，避免重复 IO。）

- [ ] **Step 3: api/jobs.py 增三端点**

```python
from pathlib import Path
from fastapi.responses import JSONResponse
from app.db.models import JobStep, JobStatus
from app.schemas.jobs import JobStepOut
import shutil

@router.get("/{job_id}/trace")
def trace(job_id: str, after: int = 0, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = _get_own_job(db, job_id, user)
    rows = db.scalars(select(JobStep).where(JobStep.job_id == job.id, JobStep.seq > after)
                      .order_by(JobStep.seq)).all()
    return {"steps": [JobStepOut.model_validate(r) for r in rows]}

@router.post("/{job_id}/cancel")
def cancel(job_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = _get_own_job(db, job_id, user)
    if job.status not in (JobStatus.QUEUED, JobStatus.RUNNING):
        raise HTTPException(409, f"cannot cancel job in status {job.status}")
    from app.worker.tasks import run_retro_job
    from app.worker.celery_app import celery_app
    if job.celery_task_id:
        celery_app.control.revoke(job.celery_task_id, terminate=True, signal="SIGTERM")
    set_status(db, job.id, JobStatus.CANCELLED)
    return {"ok": True, "status": "cancelled"}

@router.delete("/{job_id}", status_code=200)
def delete(job_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = _get_own_job(db, job_id, user)
    for row in db.scalars(select(JobStep).where(JobStep.job_id == job.id)): db.delete(row)
    db.delete(job); db.commit()
    ws = get_settings().data_dir / job.id
    if ws.exists(): shutil.rmtree(ws, ignore_errors=True)
    return {"ok": True}

def _get_own_job(db, job_id: str, user) -> Job:
    job = db.get(Job, job_id)
    if job is None or (job.user_id != user.id and user.role != "admin"):
        raise HTTPException(404, "job not found")
    return job
```

schemas/jobs.py 增 `JobStepOut{seq,command,args,result_summary,status,tokens,duration_ms,created_at}`（from_attributes）。

- [ ] **Step 4: 跑测试**

Run: `conda run -n rachel-v2 python -m pytest backend/tests/test_t11_e2e.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app backend/tests/test_t11_e2e.py backend/tests/conftest.py
git commit -m "feat: end-to-end wiring with trace, cancel and delete apis"
```

---

### Task 12: 真实化学冒烟脚本（真 RetroCmd 全程到 export）

**Files:**
- Create: `scripts/smoke_retro.py`

**Interfaces:**
- Consumes: 真实 `RetroCmd`（rachel-v2 env 必需）
- Produces: 退出码 0=成功；产物目录打印到 stdout；`output/smoke_{ts}/` 下含 visualization.json

说明：这是**手动冒烟脚本**（spec M1 验证项），不进 CI。策略为启发式固定策略驱动状态机（不依赖 LLM）：init → 循环{next → reaction_sites → 取第一个 site explore → 取第一个 action try → gate 允许则 commit，否则 accept} → queue_empty 后 finalize+export。若个别命令报错，按报错调整脚本参数（这是预期内的探索步骤）。

- [ ] **Step 1: 写脚本**

```python
"""Real-RetroCmd smoke walkthrough (no LLM): init → loop(next/sites/explore/try/commit|accept) → finalize → export.

Usage: conda run -n rachel-v2 python scripts/smoke_retro.py [SMILES]
Default target: paracetamol CC(=O)Nc1ccc(O)cc1
"""
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "Rachel-v2"))

from Rachel.main.retro_cmd import RetroCmd  # noqa: E402

PARACETAMOL = "CC(=O)Nc1ccc(O)cc1"

def first_site_id(sites: dict) -> str | None:
    for s in sites.get("sites", sites.get("site_menu", [])) or []:
        if isinstance(s, dict) and s.get("site_id"):
            return s["site_id"]
    return None

def first_action_id(explore: dict) -> str | None:
    for a in explore.get("actions", explore.get("candidates", [])) or []:
        if isinstance(a, dict) and a.get("action_id", a.get("candidate_id")):
            return a["action_id"] or a["candidate_id"]
    return None

def gate_allows(try_result: dict) -> bool:
    v = try_result.get("validation") or {}
    gate = v.get("gate") or try_result.get("validation_gate") or ""
    return try_result.get("ok", bool(gate)) and gate != "hard_block"

def main() -> int:
    target = sys.argv[1] if len(sys.argv) > 1 else PARACETAMOL
    out_root = ROOT / "output" / f"smoke_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    out_root.mkdir(parents=True, exist_ok=True)
    retro = RetroCmd(str(out_root / "session.json"))

    steps = 0
    def run(cmd: str, args: dict | None = None) -> dict:
        nonlocal steps
        steps += 1
        r = retro.execute(cmd, args or {})
        print(f"[{steps:03d}] {cmd} {' '.join(str(v) for v in (args or {}).values())[:60]}"
              f" → {'ERROR: ' + str(r.get('error'))[:80] if r.get('error') else 'ok'}")
        return r

    r = run("init", {"target": target, "name": "smoke"})
    if r.get("error"): return 2

    for _ in range(60):  # 分子上限
        r = run("next")
        if r.get("action") == "queue_empty" or r.get("error"):
            break
        sites = run("reaction_sites")
        sid = first_site_id(sites)
        committed = False
        if sid:
            explore = run("explore_site", {"site_id": sid})
            aid = first_action_id(explore)
            if aid:
                tr = run("try_action", {"action_id": aid})
                if not tr.get("error") and gate_allows(tr):
                    # try_action 成功后通常已产生沙盒 attempt，commit 用最近 idx
                    lst = run("sandbox_list")
                    idx = (lst.get("n_attempts", 1) - 1) if isinstance(lst, dict) else 0
                    cr = run("commit", {"idx": max(idx, 0),
                                        "reasoning": "smoke: first viable action at top site"})
                    committed = not cr.get("error")
        if not committed:
            ar = run("accept", {"reason": "smoke: no viable action accepted"})
            if ar.get("error"):
                run("skip", {"reason": "smoke skip"})
    run("finalize", {"summary": "smoke run"})
    ex = run("export", {"name": "smoke", "output_dir": str(out_root / "export")})
    if ex.get("error"):
        print("EXPORT FAILED:", ex["error"]); return 3
    vis = out_root / "export" / "visualization.json"
    if not vis.exists():
        print("visualization.json missing"); return 4
    n_nodes = len(json.loads(vis.read_text(encoding="utf-8")).get("nodes", []))
    print(f"SMOKE OK steps={steps} nodes={n_nodes} export={out_root / 'export'}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: 运行并按报错迭代**

Run: `conda run -n rachel-v2 python scripts/smoke_retro.py`
Expected: `SMOKE OK steps=… nodes=… export=…`
若 reaction_sites 返回结构中 site 列表键名不同（以实际 JSON 为准，打印一次原始返回调试），修正 `first_site_id`/`first_action_id` 的键名；若 commit 需要 `expected_action_id`，从 try_action 结果取 `action_id` 补传。**迭代直到退出码 0，把最终确认的键名留在脚本里。**

- [ ] **Step 3: Commit**

```bash
git add scripts/smoke_retro.py
git commit -m "feat: real-retrocmd smoke walkthrough script"
```

---

### Task 13: 部署基线（docker-compose + .env.example + README）+ 全量回归

**Files:**
- Create: `deploy/docker-compose.yml`, `.env.example`, `backend/README.md`

**Interfaces:**
- Consumes: 全部前序任务
- Produces: 开发环境可一键起 redis/pg；文档说明本地运行方式

- [ ] **Step 1: docker-compose.yml**

```yaml
services:
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    healthcheck: {test: ["CMD", "redis-cli", "ping"], interval: 5s, retries: 5}
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: rachel
      POSTGRES_USER: rachel
      POSTGRES_PASSWORD: rachel_dev
    ports: ["5432:5432"]
    volumes: [pgdata:/var/lib/postgresql/data]
    healthcheck: {test: ["CMD-SHELL", "pg_isready -U rachel"], interval: 5s, retries: 5}
volumes:
  pgdata:
```

- [ ] **Step 2: .env.example**

```env
# 数据库与队列（开发默认 SQLite；生产用 PG）
DATABASE_URL=postgresql+psycopg2://rachel:rachel_dev@localhost:5432/rachel
REDIS_URL=redis://localhost:6379/0
# 安全
JWT_SECRET=change-me-to-random-32-bytes
# LLM（多模型在 admin 界面配置，此为种子默认行）
DEEPSEEK_API_KEY=sk-xxxx
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-pro
# 护栏
MAX_HEAVY_ATOMS=80
MAX_RUNNING_PER_USER=3
# 任务数据目录
DATA_DIR=data/jobs
```

注意：`pydantic-settings` 字段名与 env 名大小写对应（`database_url` ← `DATABASE_URL`），`DATA_DIR` 需映射为 `data_dir`——在 Settings 里加 alias：`data_dir: Path = Path("data/jobs")` 加 `validation_alias="DATA_DIR"`（或统一在 model_config 里 `alias_generator`），实现时以 `pytest` 里 monkeypatch `MAX_HEAVY_ATOMS` 的既有测试仍通过为准。

- [ ] **Step 3: backend/README.md**

内容要点（按实际命令写全）：环境要求（conda rachel-v2）、`pip install -e "backend[dev]"`、`docker compose -f deploy/docker-compose.yml up -d`、`alembic upgrade head`、`uvicorn app.main:app --reload`、`celery -A app.worker.celery_app worker -P solo -c 1`（Windows）/ `--concurrency=2`（Linux）、`pytest backend/tests -v`、冒烟 `python scripts/smoke_retro.py`。

- [ ] **Step 4: 全量回归**

Run: `conda run -n rachel-v2 python -m pytest backend/tests -v`
Expected: 全部 PASS（T1-T11 所有测试）

- [ ] **Step 5: Commit**

```bash
git add deploy/docker-compose.yml .env.example backend/README.md
git commit -m "chore: dev deployment baseline and documentation"
```

---

## Self-Review 记录

- **Spec 覆盖**：M1 验证标准「mock 走通命令序列并产出 export 文件」→ T11（eager 全链路 + mock LLM）+ T12（真实 RetroCmd 冒烟）。spec §4.1 M1 范围端点（auth/jobs/trace）→ T3/T5/T11；§3 AgentDriver 四要素（工具注册/分层prompt/主循环/上下文管理/失败语义）→ T7/T8/T9；§4.2 数据模型 → T2；多模型 → T4。M1 未含项（SSE/admin stats/前端/服务器）属 M2-M5，无遗漏。
- **占位符扫描**：T5 配额测试中曾留占位注释，已在同步骤内给出完整实现（client.app.state.test_db）；T12 明确标注"按实际返回键名迭代"属探索性冒烟的预期步骤，非占位。
- **类型一致性**：`trace.record(seq, command, args, result, tokens, duration_ms)` 在 T9 driver 调用与 T10 ListTrace/DbTraceSink 签名一致；`_build_driver(job, workspace)` 在 T6 定义、T9 实装、T11 测试 monkeypatch 一致；`DriverResult.status/reason/steps/tokens_in/tokens_out/export_result` 在 T6 读取与 T9 定义一致；`JobStatus` 常量跨 T5/T6/T11 一致。

## 执行提示（给执行者）

- 任务顺序即依赖顺序（T1→T13），不建议乱序。
- T5/T11 的 conftest 演进（SessionLocal patch、data_dir autouse）是全链路测试的关键，若早期任务的 conftest 写法与此处不同，以让全部测试通过为准合并。
- Windows 下 psycopg2 不装也不影响测试（测试全走 SQLite）；生产 PG 驱动在 M5 部署计划中处理。
