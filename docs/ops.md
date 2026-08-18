# Rachel-v2 平台运维手册（ops.md）

> 记录本项目开发-部署-生产过程中出现的所有错误及修复。新故障排查时先查本手册。
> 维护约定：每次根因定位并修复后，在此追加一节（现象/根因/修复/预防）。

---

## 1. 生产：难分子任务失败——LLM 输出截断（2026-08-18）

- **现象**：`COc1ncc(Cl)cc1Nc1nc(Cl)c(C)cc1[N+](=O)[O-]` 任务 failed，12 步 / 357k tokens；任务 `error` 字段为空，失败原因只藏在 `stats.reason`。
- **根因**：`reason: no tool calls in two consecutive turns`。deepseek-v4-pro 在复杂分子上每轮先生成 3.4k+ tokens 推理文本再发工具调用；输出上限 `max_output=4096` 导致 `finish_reason=length` 截断——推理没写完、工具调用未生成，连续两轮触发熔断。证据：轨迹 tokens 曲线贴上限爬升（3918→3401→3480）；修复后重跑出现 3 个 >4096 轮次存活。
- **修复**：① provider `max_output` 4096→**8192**（admin API：`PUT /api/admin/llm-providers`）② driver 记录 text-only 轮（content + finish_reason → `messages.jsonl`，kind=text_only）③ length 截断时 nudge 提示模型"精简并立即调工具" ④ failed 任务的 `error` 字段透出 `reason`（此前为空）。
- **验证**：同分子 36 步 succeeded，路线 10 节点，终点审计 CID/vendor 2/2 闭合。
- **预防**：换模型时评估其"推理 verbosity × 输出上限"；新模型先看单轮 tokens 分布（trace 的 tokens 列）。排查同类问题看 `data/jobs/{id}/messages.jsonl` 的 text_only 记录。
- **成本参考**：复杂分子单任务 ~1.2M input tokens（扑热息痛的 5 倍）。

## 2. 部署：worker 三连故障（2026-08-17，M5）

### 2.1 `No module named 'Rachel'`
- **根因**：生产 worker 的 `sys.path` 无 Rachel-v2 目录（开发环境由 conftest/冒烟脚本注入，掩盖缺失）。
- **修复**：systemd 单元 `Environment=PYTHONPATH=/root/Rachelv2Agent/Rachel-v2`（在 `[Service]` 段内；曾误置于 `[Install]` 后被 systemd 忽略——检查段位！）。

### 2.2 `UnboundExecutionError: Could not locate a bind`
- **根因**：`run_retro_job` 中 `db = SessionLocal()` 先于 `_ensure_engine()`——工厂后配置不回填已实例化的 Session；测试环境 conftest 预绑定 SessionLocal，从未暴露。
- **修复**：`_ensure_engine()` 移到 `SessionLocal()` 之前；回归测试模拟全新进程（engine=None + 未绑定工厂）。
- **教训**：测试夹具对全局状态的"善意"预置会掩盖初始化顺序缺陷。

### 2.3 任务不注册（M1 修复波，部署前发现）
- **根因**：celery_app 无 `include=["app.worker.tasks"]`，worker 进程不注册任务（eager 测试掩盖）。
- **修复**：`celery_app.conf.update(include=[...])`；配套守卫测试。

## 3. 部署：git archive EOL 污染（2026-08-17）

- **现象**：服务器文件 CRLF 污染；`VERIFY_RELEASE.py` size mismatch。
- **根因**：Windows `core.autocrlf` 在 `git archive` 时做 LF→CRLF 转换，破坏 release 字节保真。另发现**本地 Rachel-v2 副本与官方 SHA256SUMS.json 本就存在内容差异**（非部署造成），VERIFY 对本副本永不可过。
- **修复**：`.gitattributes`（`* text=auto eol=lf` + 显式扩展名 text + 二进制标记）+ 全仓 renormalize；**部署改用工作树 tar 直传**（字节保真）。Linux 验证改用 `scripts/smoke_retro.py`（与 Windows 结果一致：16 步/6 节点）。
- **注意**：`.gitattributes` 曾出现 `*.svg binary` 与 `*.svg text` 冲突（后行覆盖前行）——加规则后 `grep` 查重。

## 4. 架构级修复（各里程碑终审发现）

| # | 问题 | 根因 | 修复 | 教训 |
|---|---|---|---|---|
| 4.1 | cancel 后任务状态被 worker 覆盖"复活" | cancel 与最终 set_status 竞态 | worker 写终态前 `db.expire_all()` 重读，CANCELLED 不覆盖 | 长任务必有状态竞态 |
| 4.2 | LLM API 一次抖动即任务失败 | 无重试计数 | 连续失败计数 ≥5 才 failed，成功清零 | SDK 内建重试不够，业务层再兜底 |
| 4.3 | SSE 流钉死连接池连接（最长 2h） | Depends session 被生成器捕获 | 每轮询短生命周期 Session + `run_in_threadpool` | 长连接端点不得持有注入的 DB session |
| 4.4 | 审计拖慢状态翻转（用户多看几分钟 running） | 审计在 set_status 前运行 | 审计移到状态翻转后；finished_at 只设一次 | 可降级的旁路任务放在主状态机之后 |
| 4.5 | `_ensure_engine` 覆盖测试重绑的 SessionLocal | init_engine 无条件 configure | 保留已有 bind 的守卫 | 全局单例 + 测试重绑 = 顺序敏感 |
| 4.6 | 导出产物落在 Rachel-v2/output 而非任务工作区 | driver 未传 output_dir | `_finalize_export` 显式 `output_dir=workspace/export` | 路径契约要显式 |

## 5. 前端修复

- **重新提交预填失效**：SubmitPage 不读 `?smiles=` 参数（跨任务缝隙：导航方与表单方各自测试各自一半）→ mount 读取 + replace 清参。
- **报告 iframe 无沙箱**：同源 iframe 可读 localStorage 的 JWT → `sandbox="allow-scripts"`（无 allow-same-origin）。
- **/files 与 /result 路径域**：export_dir 未做 data_dir 祖先校验（防御纵深）→ resolve + parents 检查，越界降级。

## 6. 环境事实（排障先读）

- 服务器 121.196.149.121（Ubuntu 22.04，与 bio.evotrek.cn 共存，我方 nginx :8080）；项目 `/root/Rachelv2Agent`；conda `/root/miniconda3/envs/rachel-v2`；静态 `/var/www/rachelv2`。
- 服务：`systemctl status rachel-api rachel-worker`；日志 `journalctl -u rachel-worker -f`。
- admin token 失效（12h）重新登录：`POST /api/auth/login`。
- LLM 证据：`data/jobs/{id}/messages.jsonl`（tool_calls 轮 + text_only 轮含 finish_reason）；步骤轨迹：`GET /api/jobs/{id}/trace`。
- 发布流程：工作树 tar 直传 → `deploy/update.sh`；**勿用 git archive**（见 §3）。
- 国内镜像：conda 用 TUNA（`.condarc` 只留 pkgs/main + cloud/conda-forge，pkgs/r 已 404）；npm 用 npmmirror；pip 用 TUNA。

## 7. 生产：succeeded/failed 任务无法删除（2026-08-18）

- **现象**：网页删除成功/失败任务无反应，任务仍在列表；cancelled 任务可删。
- **根因**：`DELETE /api/jobs/{id}` 对含 job_steps 的任务在 PG 上 500（`ForeignKeyViolation`）——模型只有裸 FK 列无 relationship，SQLAlchemy flush 时父表先于子表删除；**SQLite 默认不执行外键约束**，测试全绿成盲区。前端删除按钮无 onError，500 被静默吞掉。
- **修复**：① 删除端点先 `db.execute(delete(JobStep)...)` 批量删子记录再删任务 ② `make_engine` 对 SQLite 连接启用 `PRAGMA foreign_keys=ON`（测试从此具备 FK 检查能力——顺带揪出 2 个依赖无 FK 宽松行为的测试并修正）③ 前端删除失败显示红色错误（delete-error）。
- **验证**：此前删不掉的 succeeded/failed 任务 200 删除成功、列表消失。
- **教训**：SQLite 测试 ≠ PG 生产语义；凡涉及级联删除/约束，测试引擎必须开 FK。
