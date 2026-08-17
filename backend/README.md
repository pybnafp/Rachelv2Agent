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
| `PUBCHEM_OFFLINE` | `pubchem_offline` | false | 无外网的服务器设 `true`：终点审计走离线本地分类，不请求 PubChem；审计产物写入 `export/terminal_audit.json` |
| `TESTING` | `testing` | false | 测试标记 |

## 部署基线

`deploy/docker-compose.yml` 提供 `redis:7-alpine`（6379）与 `postgres:16-alpine`
（5432，db/user `rachel`，含 `pgdata` 持久卷与健康检查）。

## 前端（M2 起）

前端为 React 19 + Vite + TypeScript + Tailwind 的 SPA，位于 `frontend/`：

```bash
cd frontend
npm install        # 安装依赖（postinstall 自动拷贝 RDKit WASM 到 public/rdkit/）
npm run dev        # 开发服务器 http://localhost:5173（Vite proxy 将 /api 转发到 :8000）
npm test           # Vitest + Testing Library（--run 一次性跑完）
npm run build      # 产出 dist/ 静态文件（index.html + assets + rdkit WASM）
```

- 后端先启动（见上文），前端 dev 服务器通过 Vite proxy 访问 `http://localhost:8000/api/*`。
- `dist/` 为生产静态产物，生产环境由 Nginx 托管（M5 部署阶段）。

### 联调脚本

`scripts/m2_integration_check.sh` 对运行中的后端做全链路 API 验证
（注册 → me → 提交任务 → 列表 → trace → result → 文件 → 删除），
逐项输出 PASS/FAIL 并汇总：

```bash
# 终端1（仓库根目录）启动后端
D:/Anaconda/envs/rachel-v2/python.exe -m uvicorn app.main:app --port 8000 --app-dir backend
# 终端2
bash scripts/m2_integration_check.sh [base_url]   # 默认 http://127.0.0.1:8000
```

> 说明：不启动 Redis 时 Celery 无法投递（任务停留在 queued 且提交可能 500）。
> 无 Redis 的本机联调可用 eager 模式内联执行任务（见 M2-T11 报告）；有 Redis 时
> 需另起 Celery worker。LLM provider 无有效 key 时任务按预期进入 failed 且 error 有值。

## 部署（M5）

服务器为 Ubuntu 22.04，nginx 已有现有站点占用 80/443（**严禁改动**）。
本项目作为独立 server block 监听 **8080**：静态文件 `/var/www/rachelv2`，
`/api/` 反代到 `127.0.0.1:8000`（uvicorn，systemd 托管），Celery worker
并发 1。数据库 PostgreSQL 14，消息队列 Redis（均 apt 安装）。conda 环境
`/root/miniconda3/envs/rachel-v2`，项目位于 `/root/Rachelv2Agent`。

### 首次初始化

在服务器上执行一次（幂等，可重复运行）：

```bash
bash /root/Rachelv2Agent/deploy/init_server.sh
```

脚本完成：apt 依赖 → PG 建角色/库（rachel）→ 生成 `.env`（含随机
JWT_SECRET 与 PG 密码）→ miniconda（TUNA 镜像）→ conda env →
`pip install -e "backend[dev]"` → `alembic upgrade head` → 前端构建并
拷贝到 `/var/www/rachelv2` → systemd 单元（rachel-api / rachel-worker）
→ nginx 8080 站点启用。

### 日常发布

代码更新到 `/root/Rachelv2Agent` 后，在服务器上执行：

```bash
bash /root/Rachelv2Agent/deploy/update.sh
```

（pip install → alembic upgrade head → 前端构建拷贝 → 重启两服务 → nginx -t && reload）

> 代码上采用工作树 tar 直传（字节保真，避免 git archive 的 EOL 转换破坏 release
> manifest 校验）——见 M5 部署记录；`.condarc` 需配置 TUNA conda-forge 镜像
> （pkgs/r 已失效，只留 main + cloud/conda-forge）。

### 日志排查

```bash
journalctl -u rachel-api -f      # API 日志
journalctl -u rachel-worker -f   # Celery worker 日志
```

### 数据库迁移说明

- 模型所有 DateTime 列均为 `DateTime(timezone=True)`，PG 中即
  `TIMESTAMP WITH TIME ZONE`（迁移 0002 完成 ALTER）。
- SQLite 忽略 timezone 标志，故本地 dev.db 与测试不受影响，
  迁移在两种库上均可执行。
- 服务器上如需手动迁移：`cd /root/Rachelv2Agent/backend &&
  /root/miniconda3/envs/rachel-v2/bin/alembic upgrade head`
  （读取 `/root/Rachelv2Agent/.env` 中的 `DATABASE_URL`）。

### PUBCHEM_OFFLINE 开关

`.env` 中 `PUBCHEM_OFFLINE=true` 时所有 PubChem 查询走本地离线
fixtures，不触网（初始化默认 true）；需要真实在线查询时改为 `false`
并 `systemctl restart rachel-api rachel-worker`。
