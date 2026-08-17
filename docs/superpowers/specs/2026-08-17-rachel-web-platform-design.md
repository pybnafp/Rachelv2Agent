# Rachel-v2 Web 平台设计文档（前端 + 后端 + 算法端）

- 日期：2026-08-17
- 状态：已与需求方逐节确认
- 范围：基于 Rachelv2Agent 项目构建多人 Web 平台，用户提交目标分子 SMILES，系统自动完成逆合成路线规划并可视化结果

---

## 1. 背景与目标

Rachel-v2 是一个 LLM 驱动的逆合成路线规划状态机（详见 `docs/Rachel-v2_system_overview.md`）。原本以 Codex/Claude Code Skill 形式运行：LLM 通过 `RetroCmd`（JSON-in/JSON-out，26 个公共命令）多轮交互，从 `init` 走到 `export`，一个分子的完整规划约 90~120 条命令（见 `examples/result_demo`，实测 118 条）。

本项目目标：把这条交互链路产品化为一个类 AlphaFold Server 体验的 Web 平台——

> 用户输入一个 SMILES → 提交任务 → 等待（分钟级）→ 浏览交互式逆合成路线树与决策审计。

### 1.1 已确认的需求决策

| 维度 | 决定 |
|---|---|
| 算法深度 | 完整路线规划（LLM 驱动 RetroCmd 状态机全程，非单发决策上下文） |
| LLM | 多模型可切换（OpenAI 兼容协议）；默认 DeepSeek 官方接口（`https://api.deepseek.com`），key 存 `.env` |
| 部署形态 | 多人 Linux 服务器（121.196.149.121，SSH 密钥登录，项目位于 `/root/Rachelv2Agent`） |
| 用户体系 | 注册/登录（JWT）、任务隔离、并发调度 |
| 前端 | React 18 + TypeScript，AlphaFold Server 风格 |
| 可视化优先级 | ① 路线树画布 ② 决策审计 + 终点审计 ③ 实时进度面板 |
| 参考先例 | AlphaFold Server（UX 模式）、ASKCOS（技术架构：FastAPI + Celery + Vue，本设计将前端换为 React） |

### 1.2 非目标（本期不做）

- 单发决策上下文（`build_decision_context`）快速预览模式
- 公网开放注册、计费、限流
- 算法端微服务化（Rachel-v2 与后端同环境进程内调用）
- 移动端适配

---

## 2. 总体架构

选定方案：**FastAPI + Celery + Redis + PostgreSQL**（ASKCOS 同款生产架构）。

### 2.1 进程视图

| 进程/服务 | 职责 | 运行环境 |
|---|---|---|
| Nginx | 前端静态文件、`/api` 反代 | 系统级 |
| api（uvicorn:FastAPI） | 认证、任务 CRUD、SMILES 校验、产物文件服务、进度轮询/SSE | conda `rachel-v2` |
| worker（Celery × 2，可扩） | AgentDriver 完整路线规划 + export 落盘 | conda `rachel-v2` |
| Redis 7 | Celery broker、进度快照、trace 环形列表 | docker-compose |
| PostgreSQL 16 | 用户、LLM 供应商配置、任务、步骤审计 | docker-compose |

关键决策：**单一 conda 环境装齐全部依赖**。以 `Rachel-v2/environment.yml` 为底，pip 追加 `fastapi uvicorn[standard] celery redis sqlalchemy alembic httpx openai pydantic-settings python-jose passlib[bcrypt] python-multipart`。API 进程与 worker 共用环境、按进程角色区分，避免双环境同步问题（RDKit 两边都要用）。

### 2.2 仓库布局（monorepo）

```
Rachelv2Agent/
├── Rachel-v2/            # 算法端，只读使用，不修改其内部代码
├── backend/
│   ├── app/
│   │   ├── main.py           # FastAPI 入口、路由挂载、产物静态服务
│   │   ├── core/             # 配置(.env 驱动)、JWT 安全、依赖注入
│   │   ├── api/              # auth.py / jobs.py / admin.py
│   │   ├── db/               # SQLAlchemy 模型、alembic 迁移
│   │   ├── schemas/          # Pydantic 请求/响应模型
│   │   ├── agent/            # ★ AgentDriver
│   │   │   ├── driver.py     #   function-calling 主循环
│   │   │   ├── prompts.py    #   system prompt 组装（SKILL.md 分层）
│   │   │   ├── tools.py      #   RetroCmd 26 命令 → OpenAI tool schema
│   │   │   └── trace.py      #   步骤记录 → Redis/DB
│   │   └── worker/           # Celery app + run_retro_job 任务
│   ├── alembic/  tests/  pyproject.toml
├── frontend/                 # React 18 + TS + Vite + Tailwind + shadcn/ui
│   └── src/{pages,components,api,stores}
├── deploy/                   # nginx.conf、systemd 单元、docker-compose.yml、
│                             # conda 重建脚本、init_server.sh / update.sh
├── data/jobs/{job_id}/       # 任务工作区：session、导出产物、messages.jsonl
├── docs/                     # 现有文档 + specs
└── .env                      # 密钥（gitignored）
```

### 2.3 核心数据流

```
用户提交 SMILES → POST /api/jobs → RDKit 校验、规范化 → 入队（queued）
→ worker 领取（running）：
    RetroCmd(session) init
    AgentDriver 循环：LLM(function-calling) ⇄ RetroCmd.execute()
      · 每步 → trace → Redis/DB
      · 上下文滑动窗口压缩
    → finalize → export_results(output_dir=data/jobs/{id}/)
→ 解析 visualization.json / tree.json / terminals.json → 汇总指标入库（succeeded）
→ 前端轮询/SSE → React Flow 路线树渲染
```

---

## 3. AgentDriver 设计（算法端驱动器，系统最高风险部件）

职责：把交互式 Skill 运行方式移植为后端无人值守循环。一个 job 一个实例，无共享状态。

### 3.1 工具注册（tools.py）

- `RetroCmd` 的 26 个公共命令（init/next/context/guide/route_plan/route_sketch/reaction_sites/explore_site/try_action/propose_action/sandbox_list/sandbox_clear/select/commit/accept/review_terminal/skip/tree/status/continuation_status/continuation_abort/finalize/report/export/smart_cap/custom_cap）逐一注册为 OpenAI function-calling tool；参数 JSON Schema 从 `retro_cmd.py` 实际签名 + workflow 文档提炼。
- 额外 2 个元工具：
  - `read_doc(name, section?)`：按需读取 workflow.md / experience_cards.md 指定章节；
  - `finish(summary)`：正常收尾信号。
- **工具结果强制截断**：> 8KB 保留头部 + 摘要行 + 明确告知 LLM "已截断，可用更细粒度命令重新获取"。这是防上下文爆炸的第一道闸（实测 `finalize` 单步返回可达 275KB）。

### 3.2 System prompt 分层（prompts.py）

```
[常驻] SKILL.md 全文（约 32KB）+ 精简 workflow 速查（推荐命令序列图）
[按需] workflow.md（约 58KB）/ experience_cards.md → read_doc 工具
[任务] 目标分子 SMILES、job 参数、输出要求（最终必须走到 export）
```

DeepSeek 自动上下文缓存使常驻部分按前缀命中计费，成本可控。

### 3.3 主循环（driver.py）

```python
while step < MAX_STEPS(默认300) and 未 finish and 未超 wall_clock(默认60min):
    resp = llm.chat(messages, tools)           # openai SDK + base_url 指向当前 active provider
    for tool_call in resp.tool_calls:
        result = RetroCmd.execute(cmd, args)   # 状态机推进（session.json 持久化）
        trace.record(step, cmd, args, result)  # → Redis 快照 + DB job_steps
        messages.append(tool_result(truncate(result)))
    compact_if_needed(messages)                # 滑动窗口压缩
on_finish:      RetroCmd("finalize") → RetroCmd("export") → 落盘
on_limit:       尝试 finalize + export 抢救部分结果 → job = partial
```

### 3.4 上下文窗口管理（关键设计）

- 常驻：system prompt + 目标分子消息。
- 滑动窗口：最近 K=10 个工具结果保全文，更早的替换为一行摘要（例：`step 12: explore_site(site_3) → 8 actions, ok`）。
- 量化依据：实测单步返回 9~33KB（reaction_sites 33KB、finalize 275KB），压缩后稳态上下文 ≈ 32KB(SKILL) + 10×15KB ≈ 60K tokens 内，远低于 128K 上下文上限。
- 完整未截断消息日志存 `data/jobs/{id}/messages.jsonl`（审计/复现，不进 LLM）。

### 3.5 多模型配置

- DB 表 `llm_providers`：`name / base_url / api_key / model / temperature / max_output / is_active`；安装时写入默认行（DeepSeek 官方，key 注入自 `.env`）。
- admin API 增删改查、切换 active；统一走 `openai` SDK 的 `base_url`，无供应商特判代码。

### 3.6 失败语义

| 情形 | 处理 |
|---|---|
| RetroCmd 返回错误 JSON | 原样回喂 LLM 自纠（状态机设计本意）；连续同类错误 ≥10 次 → 熔断，job=failed |
| LLM API 异常 | SDK 内建重试 + 指数退避；连续 5 次失败 → job=failed |
| 步数/超时/预算上限 | finalize + export 抢救 → job=partial，记录原因 |
| SMILES 无效 | API 层入队前拦截（400），不进 worker |

---

## 4. 后端设计

### 4.1 REST API（`/api` 前缀，JWT Bearer）

```
POST /api/auth/register | /api/auth/login    # 首个注册用户自动 admin
GET  /api/auth/me

POST /api/jobs                       # {smiles, name?, 覆盖参数?}；RDKit 解析+规范化，无效 400
GET  /api/jobs?mine=1&page=          # 任务列表（自己的；admin 可看全部）
GET  /api/jobs/{id}                  # 状态 + 统计（步数/token/耗时/错误）
GET  /api/jobs/{id}/trace?after=n    # 步骤轨迹增量拉取
GET  /api/jobs/{id}/events           # SSE 实时进度（三期，先靠轮询）
GET  /api/jobs/{id}/result           # 聚合 visualization/tree/terminals/审计指标
GET  /api/jobs/{id}/files/{path}     # 产物文件（HTML 报告/图像/session.json）
POST /api/jobs/{id}/cancel           # 撤销 Celery 任务
DELETE /api/jobs/{id}                # 删除自己的任务（连同产物目录）

GET|PUT /api/admin/llm-providers     # 供应商管理（仅 admin）
GET  /api/admin/stats                # 队列深度/运行中任务（仅 admin）
```

### 4.2 数据模型（PostgreSQL）

| 表 | 关键字段 |
|---|---|
| `users` | id, username, password_hash(bcrypt), role(user/admin), created_at |
| `llm_providers` | id, name, base_url, api_key, model, temperature, max_output, is_active |
| `jobs` | id(uuid), user_id→users, smiles, name, status(queued/running/succeeded/partial/failed/cancelled), provider_id→llm_providers, error, stats(jsonb: steps/tokens_in/tokens_out/duration), celery_task_id, created_at/started_at/finished_at |
| `job_steps` | id, job_id→jobs, seq, command, args(jsonb), result_summary, status, tokens, duration_ms, created_at |

Redis 用途：Celery broker；`job:{id}:progress` 哈希（阶段、当前步、最近命令）；trace 环形列表（SSE 源）。

### 4.3 任务生命周期与护栏

- 状态机：`queued → running → succeeded | partial | failed | cancelled`，全部转换写 DB；worker 崩溃由 Celery `acks_late` + 任务超时兜底标记 failed。
- 护栏：单用户同时运行任务 ≤3（默认）；SMILES 重原子 ≤80（默认，可配）；任务产物保留 30 天（清理脚本，可配）。
- 产物文件服务：`data/jobs/{id}/` 只读暴露，路径穿越防护；`SYNTHESIS_REPORT.html` 可被前端 iframe 嵌入。

---

## 5. 前端设计

### 5.1 页面（react-router）

```
/login /register     登录注册
/                    提交页
/jobs                任务列表
/jobs/:id            任务详情（核心页）
/admin/llm           LLM 供应商管理（admin）
```

### 5.2 提交页（AlphaFold Server 风格双栏）

- 左栏（主）：任务名 + SMILES 输入框（唯一必填）——RDKit-JS 即时渲染结构预览 + 有效性校验；内置示例分子一键填入（阿司匹林、扑热息痛等）。
- 右栏（高级，默认折叠）：LLM 供应商选择、最大步数/超时预算。
- 提交 → 跳转任务详情页。

### 5.3 任务详情页

按 status 切换形态：

- **running**：进度面板——阶段指示器（初始化→路线规划→收尾→导出）、步骤命令流（轮询 `/trace?after=n`，3s）、当前步数/耗时/token 统计。
- **succeeded/partial**：Tab 布局
  1. **路线树**（核心组件 `RouteTreeCanvas`，@xyflow/react）：`visualization.json` 节点按 role 着色（target=蓝/intermediate=灰/terminal=绿），按 depth 自动分层布局；节点卡片内嵌 SMILES 结构图（RDKit-JS）+ CS 分数徽章；点节点→右侧抽屉（大图结构+分子信息）；点边→反应名、模板、validation gate；缩放/平移/小地图/节点搜索。
  2. **决策审计**：`job_steps` 时间线，每步可展开命令参数、结果摘要、commit 理由与被拒候选。
  3. **终点审计**：起始原料表格——结构图、SMILES、PubChem CID 链接、`pubchem_cid_closed`/`vendor_closed` 徽章。
  4. **报告**：iframe 嵌入 SYNTHESIS_REPORT.html；**原始文件**：下载 tree.json / session.json 等。

### 5.4 技术栈细节

- React 18 + Vite + TypeScript + TailwindCSS + shadcn/ui，蓝青主色浅色主题（Material 风格贴近 AlphaFold Server）。
- `@xyflow/react`（React Flow 12）；RDKit-JS WASM 本地打包（不依赖 CDN，国内服务器可用）。
- TanStack Query 轮询（running 态 3s 自适应，终态停）；Zustand 管 UI 状态。
- 全部请求经 Nginx 同域反代 `/api`，无 CORS。

---

## 6. 部署方案

目标服务器：121.196.149.121（SSH 密钥 `bio_connection.pem`），项目根 `/root/Rachelv2Agent`。

一次性初始化（`deploy/init_server.sh`）：

1. 上传项目（rsync，排除 node_modules/__pycache__/venv/.env）。
2. docker-compose 启动 redis:7 + postgres:16（数据卷持久化）。
3. conda env create -f Rachel-v2/environment.yml；pip install -e backend/；alembic upgrade head。
4. 前端构建产物 frontend/dist（本地构建上传或服务器构建）。
5. 写入 .env：DEEPSEEK_API_KEY / DATABASE_URL / REDIS_URL / JWT_SECRET / ADMIN_USER。

常驻进程（systemd 单元，`deploy/systemd/`）：

- `rachel-api.service`：uvicorn 0.0.0.0:8000
- `rachel-worker.service`：celery -A app.worker worker --concurrency=2
- Nginx：80/443 → 静态 + `/api` → uvicorn（后续挂域名 + TLS）

运维：`deploy/update.sh` 更新代码并滚动重启；日志 journald；产物清理 cron。

安全注意：

- `.env` 与 SSH 私钥绝不入库；`.gitignore` 覆盖。
- 会话中暴露过的 DeepSeek API key 上线前必须轮换。
- 生产 JWT_SECRET 随机生成 ≥32 字节。

---

## 7. 错误处理

| 层 | 错误 | 策略 |
|---|---|---|
| 前端 | 网络/轮询失败 | TanStack Query 自动重试退避；SSE 断线降级轮询 |
| API | 无效 SMILES/配额超限/越权 | 400/403 明确错误码；路径穿越防护 |
| Worker | LLM API 异常 | SDK 重试 + 指数退避；连续 5 次失败 → failed |
| Worker | 步数/超时/预算上限 | finalize+export 抢救 → partial |
| Worker | 进程崩溃 | Celery acks_late + 超时 → failed；session.json 落盘可人工恢复 |
| 算法端 | RetroCmd 错误 | 回喂 LLM 自纠；连续同类 ≥10 次 → 熔断 |
| PubChem 审计 | 网络不通（国内访问不稳） | 可降级：审计失败不阻塞 job，面板显示"审计不可用"，产物保留 |

---

## 8. 测试策略（按风险排序）

1. **AgentDriver 单测**（最高风险）：mock LLM 返回预设 tool_call 序列（取自 `examples/result_demo` 真实命令序列），断言状态机走通 init→…→export；截断函数、上下文压缩单测。
2. **后端 API 集成测试**：pytest + testcontainers（postgres/redis）——注册登录/提交/列表/越权/取消。
3. **Celery 端到端**：mock LLM 跑通完整生命周期（queued→succeeded）。
4. **前端**：Vitest 组件测试（RouteTreeCanvas 用真实 visualization.json fixture）；Playwright 冒烟（提交→轮询→结果页）。
5. **真 LLM 冒烟**（手动，非 CI）：阿司匹林完整规划一次，验收全链路。

---

## 9. 验收标准

注册用户提交一个真实 SMILES → 30 分钟内得到 succeeded → 路线树画布可交互浏览（缩放/点选/看结构）→ 决策审计可追溯每一步命令 → 终点审计面板可见 CID/vendor 指标 → 报告 HTML 可查看、原始文件可下载。

---

## 10. 分期交付

| 里程碑 | 内容 | 验证 |
|---|---|---|
| M1 骨架跑通 | 仓库结构、auth、提交 API、AgentDriver（mock LLM）端到端 | mock 走通 demo 命令序列并产出 export 文件 |
| M2 结果可视化 | React 前端、任务列表/详情、RouteTreeCanvas、报告嵌入 | 用 examples 真实产物渲染 |
| M3 审计面板 | 决策审计时间线、终点审计表格 | job_steps/terminals 数据贯通 |
| M4 进度与管理 | 实时进度面板（轮询优化/SSE）、admin LLM 管理 | running 态实时可见 |
| M5 上线验收 | 服务器部署、真 LLM 冒烟、护栏与清理 | 验收标准全通过 |

---

## 11. 风险与开放问题

| 风险 | 缓解 |
|---|---|
| AgentDriver 循环质量依赖 DeepSeek 的化学推理与 function-calling 稳定性 | 多模型可切换，验收前用 GLM/Claude 对比冒烟；MAX_STEPS/预算护栏兜底 |
| Rachel-v2 未在 Linux 验证过（官方仅声明 Windows） | M1 首项即在 Linux 重建环境跑 `VERIFY_RELEASE.py`；RDKit/纯 Python 跨平台风险低 |
| 国内服务器访问 PubChem 不稳 | 终点审计设计为可降级，不阻塞主流程 |
| LLM 长循环 token 成本 | 上下文压缩 + 缓存命中 + 预算上限 + stats 可视化 |
| 128K 上下文溢出 | 滑动窗口 + 8KB 截断双闸（见 §3.4） |

开放问题（实现阶段决定，不阻塞 spec）：

1. `export` 前是否强制 LLM 显式 `finalize`（demo 中 finalize 在 export 前）——按 demo 序列实现，driver 收到 finish 后统一补发 finalize+export。
2. continuation_status/continuation_abort 等低频命令是否纳入 tool schema 首版——纳入（schema 廉价），但 prompt 速查表不突出。
3. 前端 RDKit-JS 的 WASM 资源以 npm 包还是 vendored 文件引入——实现时按可用性选择，倾向 npm。
