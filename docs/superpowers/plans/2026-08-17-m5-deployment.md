# Rachel-v2 Web 平台 M5（服务器部署与验收）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 平台部署至 Linux 服务器（121.196.149.121，/root/Rachelv2Agent，端口 8080，零打扰共存于现有 bio.evotrek.cn 站点），完成真实 DeepSeek LLM 端到端验收。

**Architecture:** apt 原生 redis+postgresql（127.0.0.1）；Miniconda(TUNA) + conda env rachel-v2；uvicorn + celery systemd 单元；nginx 新 server block :8080（静态 /var/www/rachelv2 + /api 反代含 SSE 配置）；前端服务器端构建（node 20 已装）；验收 = 阿司匹林/扑热息痛真实 LLM 完整规划。

**Tech Stack:** Ubuntu 22.04 / Miniconda / PG 14 / redis 6 / nginx（已装）/ node 20（已装）。

**Spec:** §6 部署方案 + §9 验收标准 + §11 风险表（Linux 首验、PubChem 网络、成本）。

## 服务器事实（2026-08-17 探测）

- Ubuntu 22.04.5，4核/7.1G/30G空闲；**已有服务不可打扰**：nginx 服务 bio.evotrek.cn(80/443)、bioagent.service、/root/{BioAgent,DpAgent,RachelAgent,workspace}
- 已装：nginx、node v20.20.2、python3.12（系统）；未装：conda/docker/redis/pg
- /root 权限 700 → nginx 静态根用 /var/www/rachelv2（部署脚本拷贝）
- 8080 端口空闲；Aliyun 安全组 8080 是否放行待验（若未放行需用户控制台操作）

## 裁定（M5）

1. **apt 原生 redis+pg 替代 spec §6 的 docker-compose**：docker 缺失、国内拉镜像不可靠、apt systemd 原生更稳；spec 意图（redis+pg 可用）满足
2. **端口 8080**：不动现有 80/443 站点；后续可平移子域名
3. **前端服务器端构建**：node 20 已装，更新链路 = git archive 上传 → 服务器 build
4. **短时 artifact token 不在本里程碑**：当前 HTTP-over-IP 部署下 Bearer 同样明文，收益边际；TLS/域名上线时一并做（记账）
5. **worker concurrency=1**：共机资源礼让；跑通后可调

## 任务

### Task M5-T1（代码，subagent 执行）：PG 就绪 + 部署工件

**Files:**
- Modify: `backend/app/db/models.py`（DateTime → DateTime(timezone=True)）、`backend/pyproject.toml`（+psycopg2-binary）
- Create: `backend/alembic/versions/0002_*.py`（autogenerate：timezone 变更）
- Create: `deploy/nginx-rachelv2.conf`、`deploy/systemd/rachel-api.service`、`deploy/systemd/rachel-worker.service`、`deploy/init_server.sh`、`deploy/update.sh`
- Modify: `backend/README.md`（部署 runbook 段落）
- Test: `backend/tests/test_m5_migration.py`（timezone 列属性断言 + upgrade head 可执行）

**工件规格：**
- nginx-rachelv2.conf：`listen 8080;` server；`root /var/www/rachelv2;`（try_files SPA fallback `/index.html`）；`location /api/ { proxy_pass http://127.0.0.1:8000; proxy_http_version 1.1; proxy_set_header Host $host; proxy_buffering off; proxy_read_timeout 300s; proxy_send_timeout 300s; }`（SSE：proxy_buffering off + read timeout>心跳 16s）；`client_max_body_size 10m`
- rachel-api.service：`ExecStart=/root/miniconda3/envs/rachel-v2/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir /root/Rachelv2Agent/backend`，`WorkingDirectory=/root/Rachelv2Agent`，`EnvironmentFile=/root/Rachelv2Agent/.env`，User=root，Restart=on-failure，After=network.target redis-server.service postgresql.service
- rachel-worker.service：同上但 `celery -A app.worker.celery_app worker --concurrency=1 --loglevel=info`（Linux 无需 -P solo）
- init_server.sh（幂等 runbook，具体步骤见 T2 执行记录）：apt 装 redis-server postgresql nginx(已装跳过) → PG 建库建用户(rachel/rachel_prod_pw 随机生成写 .env) → miniconda 装(TUNA) → conda env create → pip install -e backend[dev] → alembic upgrade head → 前端 npm ci+build → 拷 dist→/var/www/rachelv2 → .env 生成（JWT_SECRET 随机）→ systemd 单元安装启用 → nginx 站点启用 reload
- update.sh：git archive 流上传新代码 → pip install → alembic upgrade → npm build → 拷 dist → systemctl restart 两服务

### Task M5-T2（运维，控制器直接执行）：服务器准备与部署

步骤（每步验证后再下一步）：apt 更新+装 redis-server postgresql（bind 127.0.0.1 核查）→ PG 建库/用户 → Miniconda(TUNA mirror) → conda env create -f environment.yml（Linux 首验 spec 风险#2）→ VERIFY_RELEASE.py → pip install -e backend + psycopg2-binary → .env（生产值：PG URL/随机 JWT_SECRET/DEEPSEEK key/**PUBCHEM_OFFLINE 先 true**，验收时再试在线）→ alembic upgrade head → 代码上传（git archive | ssh tar）→ 前端 npm ci + build → dist→/var/www/rachelv2 → systemd 两单元起 → nginx 站点 :8080 → 本地 curl 验证（安全组放行则通；不通则报用户开端口）

### Task M5-T3（验收，控制器直接执行）：真实 LLM 端到端

/health → 注册 admin → admin API 写入 DeepSeek provider（现 key；提醒轮换）→ 提交扑热息痛（真实 LLM）→ SSE/trace 观察（预计 10-30 分钟，DeepSeek 费用 ~¥1-5）→ succeeded 后验证：路线树数据（visualization.json 节点数）、决策审计 steps、终点审计（先离线；再试 PUBCHEM_OFFLINE=false 在线一次）→ 报告 HTML 可取 → （可选）本地 Playwright 冒烟

### Task M5-T4（收尾）：runbook 提交 + 记忆更新 + 安全待办移交（key 轮换、TLS/域名、短时 token）

## 验收标准（spec §9）

注册用户提交真实 SMILES → 30 分钟内 succeeded → 路线树画布数据完整 → 决策审计可追溯 → 终点审计可见 → 报告/文件可下载 → **全程在部署服务器上完成**。
