# Rachel-v2 Web 平台 M4（实时进度 + admin 管理）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** running 态任务详情页升级为实时进度面板（SSE 事件流 + 断线降级轮询：阶段指示器、命令流、实时统计），新增 admin LLM 供应商管理页，并清偿 M2/M3 顺延小项。

**Architecture:** 后端新增 SSE 端点 `/api/jobs/{id}/events`（Bearer 或 ?token= 双通道，同步生成器由 StreamingResponse 线程池驱动，2s 节流查 job_steps 增量 + 状态变化，终态即关）；实时统计在**服务端从 job_steps 聚合**（running 期间 job.stats 为空——worker 只在收尾写入）。前端 ProgressPanel 用 EventSource 消费，onerror 自动降级为 /trace 轮询（spec §7）。admin 页消费既有 GET/PUT /api/admin/llm-providers。

**Tech Stack:** 沿用（FastAPI/React 19/TS6/TanStack Query）；无新依赖。

**Spec:** `docs/superpowers/specs/2026-08-17-rachel-web-platform-design.md` §4.1（/events SSE、Redis 进度——裁定见下）、§5.3 running 形态、§7（SSE 断线降级轮询）、§10 M4 行。

**控制器裁定（写计划时已定）：**
1. spec §4.2 的 Redis `job:{id}:progress` 哈希 **不做**——进度数据源就是 job_steps 表（DB 已是事实源），SSE 端点服务端查表即可；引入 Redis 双写徒增一致性面。spec 的"Redis 进度缓存"意图由 DB+2s 节流满足。
2. SSE 鉴权用 ?token=（EventSource 不能带 header），与 M2 files 端点同模式；本次把双通道解析抽成 `app/api/deps.py::resolve_token_user` 共享助手（消化 M2 顺延项"鉴权内联未抽"）。
3. 阶段（stage）**前端从命令流推导**，后端不存 stage 字段：init→初始化；next/reaction_sites/explore_site/try_action/commit/accept/propose_action/sandbox_*/select→路线规划；route_plan/route_sketch/guide→策略调整；finalize→收尾；export→导出；finish→完成。

## Global Constraints

- 后端 `D:/Anaconda/envs/rachel-v2/python.exe -m pytest backend/tests -v`（基线 66 绿）；前端 `npm --prefix frontend test`（70 绿）+ build。
- Rachel-v2/ 只读；TS6 erasableSyntaxOnly；`import type`；每任务一 commit（conventional）；TDD。
- SSE 测试用 TestClient 的 `stream` 上下文（httpx 流式），断言首帧与终态关闭；**不做真实长连接压测**（M5 服务器验收）。
- EventSource 在 jsdom 不存在——测试用 FakeEventSource（vi.stubGlobal）。

## 契约（M4 新增/变更）

```
# 后端
GET /api/jobs/{id}/events?token=<jwt>      # Bearer 亦行；SSE text/event-stream
  事件流（data 均为 JSON 串）:
    event: snapshot  data: {"status": str, "stats_live": {"steps": int, "tokens": int, "duration_ms": int}, "steps": [TraceStep...现有步骤]}
    event: steps     data: {"steps": [TraceStep...新增(seq>上次)]}
    event: status    data: {"status": str, "stats": dict}        # 状态变化时
    event: done      data: {"status": str}                        # 终态后发送并关闭
  注释心跳 ": ping"（≥15s 空闲时）；总时长上限 7200s；客户端断开检测 request.is_disconnected()
# deps.py
def resolve_token_user(cred: HTTPAuthorizationCredentials | None, token: str | None, db: Session) -> User  # 401 on failure；files 与 events 共用
# 前端
useJobEvents({id, onSteps, onStatus, onDone}) → {mode: "sse"|"polling"|"closed"}   # EventSource + 降级
lib/traceStats.ts: aggregateSteps(steps) → {total, errors, tokens, durationMs}     # AuditTimeline 与 ProgressPanel 共用
```

## File Structure

```
backend/app/api/deps.py                  # M4-T1: resolve_token_user
backend/app/api/jobs.py                  # M4-T1: events 端点；files 改用共享助手
backend/tests/test_m4_events.py          # M4-T1
frontend/src/
├── lib/traceStats.ts                    # M4-T2: 聚合工具（AuditTimeline 重构复用）
├── lib/stages.ts                        # M4-T2: 命令→阶段推导（纯函数）
├── api/hooks.ts                         # M4-T2: useJobEvents
├── components/ProgressPanel.tsx         # M4-T2: 阶段指示器+命令流+实时统计
├── components/AuditTimeline.tsx         # M4-T2: 改用 traceStats（DRY）
├── pages/JobDetailPage.tsx              # M4-T2: running 分支换 ProgressPanel
├── pages/AdminProvidersPage.tsx         # M4-T3
├── components/Layout.tsx / App.tsx      # M4-T3: admin 导航与路由 /admin/llm
└── tests/{progress-panel,admin-providers}.test.tsx + fakes_eventsource.ts
```

---

### Task M4-T1: 后端 SSE 事件流端点 + 鉴权助手抽取

**Files:**
- Modify: `backend/app/api/deps.py`、`backend/app/api/jobs.py`
- Test: `backend/tests/test_m4_events.py`

**Interfaces:**
- Consumes: `_get_own_job`、bearer（deps）、JobStep 查询
- Produces: 契约区 `resolve_token_user` 与 events 端点

- [ ] **Step 1: 失败测试**

```python
import json

def _sse_lines(resp):
    return [l for l in resp.iter_lines() if l]

def test_events_snapshot_and_done(client, db, auth_headers_user):
    jid = client.post("/api/jobs", headers=auth_headers_user, json={"smiles": "CCO"}).json()["id"]
    with client.stream("GET", f"/api/jobs/{jid}/events", headers=auth_headers_user) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        lines = _sse_lines(resp)
    joined = "\n".join(lines)
    assert "event: snapshot" in joined and '"status"' in joined
    assert "event: done" in joined                      # eager 下任务已终态 → 快照后即 done 关闭

def test_events_token_query_auth(client, db, auth_headers_user):
    jid = client.post("/api/jobs", headers=auth_headers_user, json={"smiles": "CCO"}).json()["id"]
    tok = auth_headers_user["Authorization"].split(" ", 1)[1]
    with client.stream("GET", f"/api/jobs/{jid}/events?token={tok}") as resp:
        assert resp.status_code == 200
    with client.stream("GET", f"/api/jobs/{jid}/events?token=bad") as resp:
        assert resp.status_code == 401

def test_events_other_user_404(client, db, auth_headers_admin, auth_headers_user):
    jid = client.post("/api/jobs", headers=auth_headers_user, json={"smiles": "CCO"}).json()["id"]
    with client.stream("GET", f"/api/jobs/{jid}/events", headers=auth_headers_admin) as resp:
        assert resp.status_code == 200                   # admin 可见
    client.post("/api/auth/register", json={"username": "m4eve", "password": "pw7"})
    t = client.post("/api/auth/login", json={"username": "m4eve", "password": "pw7"}).json()["access_token"]
    with client.stream("GET", f"/api/jobs/{jid}/events",
                       headers={"Authorization": f"Bearer {t}"}) as resp:
        assert resp.status_code == 404

def test_resolve_token_user_shared(client, db, auth_headers_user):
    # files 端点改用共享助手后行为不变（既有 token 测试仍绿即为验证）；此处直接单测助手
    from app.api.deps import resolve_token_user
    from fastapi.security import HTTPAuthorizationCredentials
    tok = auth_headers_user["Authorization"].split(" ", 1)[1]
    u = resolve_token_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials=tok), None, db)
    assert u.username == "usr"
    assert resolve_token_user(None, "bad", db) is None or True   # 实现选择：返回 None 或抛 401——以 events/files 用法为准
```

- [ ] **Step 2: deps.py 助手（files 与 events 共用；返回 None 表示未通过，调用方抛 401——统一语义写 docstring）**

```python
def resolve_token_user(cred, token, db) -> User | None:
    """Bearer credential 或 ?token= query 任一 → User；都无效返回 None（调用方 401）。"""
    from app.core.security import decode_token
    raw = None
    if cred is not None and cred.credentials:
        raw = cred.credentials
    elif token:
        raw = token
    if not raw:
        return None
    payload = decode_token(raw)
    if not payload or "sub" not in payload:
        return None
    try:
        uid = int(payload["sub"])
    except (TypeError, ValueError):
        return None
    return db.get(User, uid)
```
files 端点改为调用它（消除内联复制；既有 Bearer/?token= 测试不回归即验证）。

- [ ] **Step 3: events 端点（jobs.py）**

```python
import time as _time
from fastapi.responses import StreamingResponse

TERMINAL = {JobStatus.SUCCEEDED, JobStatus.PARTIAL, JobStatus.FAILED, JobStatus.CANCELLED}
SSE_POLL_SEC = 2.0
SSE_MAX_SEC = 7200

def _live_stats(db: Session, job_id: str, last_seq: int) -> dict:
    rows = db.scalars(select(JobStep).where(JobStep.job_id == job_id)).all()
    return {"steps": len(rows), "tokens": sum(r.tokens or 0 for r in rows),
            "duration_ms": sum(r.duration_ms or 0 for r in rows), "last_seq": last_seq}

@router.get("/{job_id}/events")
def events(job_id: str, token: str | None = None, request: Request = None,
           cred: HTTPAuthorizationCredentials | None = Depends(bearer),
           db: Session = Depends(get_db)):
    from app.api.deps import resolve_token_user
    user = resolve_token_user(cred, token, db)
    if user is None:
        raise HTTPException(401, "missing or invalid token")
    job = _get_own_job(db, job_id, user)
    def gen():
        last_seq = 0
        last_status = None
        t0 = _time.monotonic()
        while _time.monotonic() - t0 < SSE_MAX_SEC:
            if request is not None and request.is_disconnected():
                return
            steps = db.scalars(select(JobStep).where(
                JobStep.job_id == job.id, JobStep.seq > last_seq).order_by(JobStep.seq)).all()
            if steps:
                payload = [JobStepOut.model_validate(s).model_dump(mode="json") for s in steps]
                last_seq = steps[-1].seq
                ev = "snapshot" if last_status is None else "steps"
                extra = f', "stats_live": {json.dumps(_live_stats(db, job.id, last_seq))}' if ev == "snapshot" else ""
                yield f"event: {ev}\ndata: {json.dumps({'steps': payload})[:-1]}{extra}}}\n\n"
                if last_status is None:
                    last_status = "init"
            db.expire_all()
            current = db.get(Job, job.id)
            if current and current.status != last_status:
                last_status = current.status
                yield f"event: status\ndata: {json.dumps({'status': current.status, 'stats': current.stats or {}})}\n\n"
                if current.status in {JobStatus.SUCCEEDED, JobStatus.PARTIAL,
                                      JobStatus.FAILED, JobStatus.CANCELLED}:
                    yield f"event: done\ndata: {json.dumps({'status': current.status})}\n\n"
                    return
            _time.sleep(SSE_POLL_SEC)
        yield "event: done\ndata: {\"status\": \"timeout\"}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
```

（实现时注意：snapshot 帧的 JSON 拼装改为先组 dict 再 dumps——上面 extra 拼法仅示意，勿复制字符串拼接 bug；`request: Request = None` 应为 FastAPI 注入 `request: Request`；首帧前若已终态，也要先发 snapshot 再发 status+done——以测试 1 断言为准。）

- [ ] **Step 4: 跑测试**（新 4 + 全套 66 不回归；既有 files token 测试验证助手重构）
- [ ] **Step 5: Commit** `feat: sse job event stream with shared token auth resolution`

---

### Task M4-T2: 前端 ProgressPanel（SSE + 降级轮询）+ 统计/阶段工具

**Files:**
- Create: `frontend/src/lib/traceStats.ts`、`frontend/src/lib/stages.ts`、`frontend/src/components/ProgressPanel.tsx`、`frontend/src/api/hooks.ts` 增 useJobEvents、`frontend/src/tests/fakes_eventsource.ts`
- Modify: `frontend/src/components/AuditTimeline.tsx`（改用 traceStats）、`frontend/src/pages/JobDetailPage.tsx`（running 分支换 ProgressPanel）
- Test: `frontend/src/tests/progress-panel.test.tsx`、`frontend/src/tests/trace-stats.test.ts`

**Interfaces:**
- Consumes: TraceStep、useAuthStore token、/trace
- Produces: `aggregateSteps(steps) → {total, errors, tokens, durationMs}`；`stageOf(commands: string[]) → StageKey`（stage 键 "init"|"planning"|"strategy"|"finalizing"|"exporting"|"done"，STAGES 常量含 label 与顺序）；`useJobEvents({id, onSteps, onStatus, onDone}) → {mode}`；`<ProgressPanel jobId/>`

**规格：**
- ProgressPanel：顶部阶段指示器（STAGES 顺序横条，当前阶段高亮 sky，已完成 emerald 勾，未到灰）；中部命令流（最近 30 条滚动区：seq+command+status 点+耗时，新步骤进入时自动滚底 data-testid="cmd-stream"）；底部实时统计三卡（步数/token/耗时 来自 aggregateSteps）；连接状态徽章（mode: sse→"实时" sky / polling→"轮询降级" amber / closed 灰）
- useJobEvents：new EventSource(`/api/jobs/${id}/events?token=${token}`)；onmessage 按 event 分发（addEventListener("snapshot"/"steps"/"status"/"done")）；done → close、mode=closed、调用 onDone；onerror 且未 done → close + 降级 setInterval 3s 拉 `/trace?after=lastSeq` 增量 + 定期 GET job 状态，直至终态（mode=polling）；组件卸载清理（close/clearInterval）
- JobDetailPage：running|queued 分支渲染 ProgressPanel（替换原静态提示，保留 running-hint testid 于面板内某元素）；onDone → invalidate ["job",id] 与 ["result",id]（触发结果加载与 Tabs 切换）
- AuditTimeline 统计卡改用 aggregateSteps（行为不变，既有测试不回归）
- stages.ts：命令→阶段映射按裁定 3；空命令列表 → "init"

**测试：**
- trace-stats：混合 ok/error 步 → 计数正确；空数组 → 全 0
- progress-panel：FakeEventSource（可编程 dispatch snapshot/steps/done）→ 渲染命令行数、阶段高亮"路线规划"、统计数字；dispatch done → onDone 调用 + close；FakeEventSource 立即 error → 降级轮询（fetch 被 3s 定时器调用——用 vi.useFakeTimers 推进断言 fetch 到 /trace?after=）；卸载 → close 被调
- JobDetailPage 集成：running job + FakeEventSource → running-hint 与 cmd-stream 并存

- [ ] **Step 1: 失败测试** → **Step 2: 实现** → **Step 3: 全前端测试 + build** → **Step 4: Commit** `feat: live progress panel with sse and polling fallback`

---

### Task M4-T3: admin 供应商管理页 + M3 顺延清理

**Files:**
- Create: `frontend/src/pages/AdminProvidersPage.tsx`
- Modify: `frontend/src/components/Layout.tsx`（admin 导航"供应商"）、`frontend/src/App.tsx`（/admin/llm 路由 + admin 守卫）、`frontend/src/components/TerminalAuditPanel.tsx`（M3 顺延：available===true 一致性 + summary 回退死计数清理）、`frontend/src/api/hooks.ts`（useTrace enabled 门控：`!!id && enabled`（调用方传 tab 激活或终态）——AuditTimeline 与 ProgressPanel 传各自条件）、`frontend/src/components/AuditTimeline.tsx`（hhmmss 改 UTC 显示并加 "UTC" 后缀）
- Test: `frontend/src/tests/admin-providers.test.tsx`

**AdminProvidersPage 规格：**
- useQuery ["providers"] → GET /api/admin/llm-providers；卡片列表：name、model、base_url（截断）、temperature/max_output、api_key 状态（"已设置" emerald / "未设置" zinc——**永不回显明文**）、is_active 徽章（"当前使用" sky）
- 操作：每卡片"编辑"（进入表单：name/base_url/api_key(留空=不变)/model/temperature/max_output）与"设为当前"（PUT is_active:true，互斥由后端保证，成功后 invalidate）
- 顶部"新增供应商"按钮（空表单）；非 admin 访问 → 无权限卡（Layout 导航本就只对 admin 显示；直接 URL 访问时页面用 /api/auth/me role 判断）
- 表单校验：name/base_url/model 必填；提交 PUT → 错误横幅（error 文案）/成功 → 刷新列表

**测试**：mock fetch——列表渲染 3 供应商（1 active）；点"设为当前" → PUT 体 is_active true；编辑表单必填校验（空 model 提交禁用）；api_key 永不出现在 DOM（assert 无明文 key 字符串）。

- [ ] **Step 1: 失败测试** → **Step 2: 实现 + 顺延清理** → **Step 3: 全前端测试 + build（70+新增）** → **Step 4: Commit** `feat: admin llm provider management page with deferred cleanups`

---

## Self-Review 记录

- **Spec 覆盖**：§4.1 /events SSE（三期）→ T1+T2；§7 SSE 断线降级轮询 → useJobEvents onerror 路径；§5.3 running 形态（阶段/命令流/统计）→ ProgressPanel；admin LLM 管理 → T3；M4 行"轮询优化" → 降级轮询 + 既有 JobsPage 条件轮询。Redis progress 哈希裁定不做（DB 为事实源，已记 Ruling）。M3/M2 顺延项全部入 T3。
- **占位符**：T1 Step3 代码含自注（JSON 拼装示意勿照抄、Request 注入），实现者以测试断言为准——这是明确的实现指引而非 TBD。
- **类型一致性**：TraceStep 复用；SSE 帧 steps 字段与 TraceStep 同构；aggregateSteps 双消费方；resolve_token_user 语义（None→调用方 401）全计划统一。
- **风险**：① TestClient 流式 SSE 的同步生成器兼容性（httpx stream + StreamingResponse 同步 gen 为 FastAPI 支持路径，测试 1 即验证）；② FakeEventSource 的 dispatch 时机（fakes_eventscope 提供可控 enqueue）；③ AuditTimeline 重构 DRY 的行为回归由既有 12 步 fixture 测试兜底。