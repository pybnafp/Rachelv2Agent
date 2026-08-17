# Rachel-v2 Backend (M1)

FastAPI + Celery backend for the Rachel-v2 retro-synthesis agent platform.

## 环境要求

- Python 3.11+（推荐 conda 环境 `rachel-v2`）
- Docker（可选，用于 Redis / PostgreSQL）
- Rachel-v2 源码仓库位于仓库根目录 `Rachel-v2/`（只读依赖）

## 快速开始

```bash
# 1. 安装依赖（在仓库根目录）
conda run -n rachel-v2 pip install -e "backend[dev]"

# 2. （可选）启动 Redis + PostgreSQL
docker compose -f deploy/docker-compose.yml up -d

# 3. 配置环境变量
cp .env.example .env   # 按需修改；开发默认 SQLite，不配 PG 也能跑

# 4. 数据库迁移（PG 部署时；SQLite 开发可跳过，应用启动时自动建表）
conda run -n rachel-v2 alembic upgrade head

# 5. 启动 API
conda run -n rachel-v2 uvicorn app.main:app --reload

# 6. 启动 Celery worker
# Windows:
conda run -n rachel-v2 celery -A app.worker.celery_app worker -P solo -c 1
# Linux:
conda run -n rachel-v2 celery -A app.worker.celery_app worker --concurrency=2

# 7. 运行测试
conda run -n rachel-v2 python -m pytest backend/tests -v

# 8. 冒烟脚本（真实化学链路，需已配置 LLM provider）
conda run -n rachel-v2 python scripts/smoke_retro.py
```

> **直接使用环境 Python**（跳过 `conda run`）：将上述命令中的
> `conda run -n rachel-v2 python` / `conda run -n rachel-v2` 替换为该环境的
> Python 可执行文件路径，例如本机开发时：
> `D:/Anaconda/envs/rachel-v2/python.exe -m pytest backend/tests -v`、
> `D:/Anaconda/envs/rachel-v2/python.exe -m uvicorn app.main:app --reload`。
> 注意机器相关路径不要写入文档/脚本之外的地方。

> `uvicorn` / `alembic` / `celery` 也可用模块方式调用：
> `python -m uvicorn app.main:app --reload`、`python -m alembic upgrade head`、
> `python -m celery -A app.worker.celery_app worker -P solo -c 1`。

## 认识的环境变量

配置由 `backend/app/core/config.py`（pydantic-settings）读取，大小写不敏感：

| Env | 字段 | 默认 | 说明 |
|---|---|---|---|
| `DATABASE_URL` | `database_url` | `sqlite:///./dev.db` | SQLAlchemy 连接串 |
| `REDIS_URL` | `redis_url` | `redis://localhost:6379/0` | Celery broker/backend |
| `JWT_SECRET` | `jwt_secret` | dev 占位 | 生产必须更换 |
| `JWT_EXPIRE_MINUTES` | `jwt_expire_minutes` | 720 | token 有效期 |
| `DATA_DIR`（别名 `data_dir`） | `data_dir` | `data/jobs` | 任务工作区目录 |
| `DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL` | 对应 `deepseek_*` | 见 .env.example | 种子默认 LLM 行 |
| `DEFAULT_LLM_NAME` | `default_llm_name` | `deepseek` | 默认激活 provider |
| `MAX_HEAVY_ATOMS` | `max_heavy_atoms` | 80 | 提交护栏 |
| `MAX_RUNNING_PER_USER` | `max_running_per_user` | 3 | 并发护栏 |
| `TESTING` | `testing` | false | 测试标记 |

## 部署基线

`deploy/docker-compose.yml` 提供 `redis:7-alpine`（6379）与 `postgres:16-alpine`
（5432，db/user `rachel`，含 `pgdata` 持久卷与健康检查）。
