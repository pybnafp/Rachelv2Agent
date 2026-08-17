# Rachel-v2 Web 平台 M3（决策审计 + 终点审计面板）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 详情页新增两个审计 Tab——决策审计（job_steps 时间线，可展开命令参数/结果摘要/commit 理由与被拒候选）与终点审计（terminals 表 + PubChem CID/vendor 闭合徽章，网络不可用可降级）。

**Architecture:** 后端在 worker export 成功后运行 Rachel-v2 的 PubChem 终点审计（`tools/pubchem_terminal_audit.py`，离线模式仅本地分类+allowlist），结果写 `export/terminal_audit.json` 并经 `/result` 返回；前端两个新面板组件消费 `/trace` 与 `/result`。审计失败不阻塞任务（spec §7 降级）。

**Tech Stack:** 沿用 M1/M2（FastAPI/Celery；React 19 + TS6 + Tailwind；无新依赖）。

**Spec:** `docs/superpowers/specs/2026-08-17-rachel-web-platform-design.md` §5.3 Tab 2/3、§12 终点审计、§7 PubChem 降级；§10 M3 行"job_steps/terminals 数据贯通"。

## Global Constraints

- 后端测试：`D:/Anaconda/envs/rachel-v2/python.exe -m pytest backend/tests -v`（当前 59 绿）；前端：`npm --prefix frontend test`（当前 55 绿）+ `npm --prefix frontend run build`。
- **测试绝不访问网络**：PubChem 审计在测试中一律 offline 模式（conftest 设 env `PUBCHEM_OFFLINE=true`）。
- `Rachel-v2/` 只读——审计工具只 import：`from Rachel.tools.pubchem_terminal_audit import PubChemClient, audit_record, load_terminal_records`。
- TS6 erasableSyntaxOnly（禁 enum/参数属性）；`import type`；测试 mock MoleculeView 与 `../rdkit`；Tabs 受控 `{tabs,active,onChange}`。
- 错误契约 `{"error":...}`；每任务一 commit（conventional）；TDD。

## 已核实的数据形状（M3 事实基准）

```
GET /api/jobs/{id}/trace?after=n → {steps: JobStepOut[]}
JobStepOut = {seq, command, args(dict), result_summary, status("ok"|"error"), tokens, duration_ms, created_at}
  # commit 步骤的 args 含 {idx, reasoning, confidence, rejected[], ...}（M1 driver 原样记录）
  # accept 步骤的 args 含 {reason}

terminals.json = [{smiles, node_id, cs_score, classification}]        # 实测 6 条
audit_record() 单条返回 = {
  node_id, smiles, cs_score, rachel_classification,
  local{...本地分类}, allowlist{hit, evidence{...}},
  pubchem{best_cid, best_cid_url, cids[], vendor_evidence{...}, queried},
  pubchem_metrics{pubchem_cid_closed: bool, vendor_closed: bool, ...},
  buyability_decision{...}
}
PubChemClient(cache_dir=Path|None, timeout=20.0, pause_seconds=0.2, offline=False)
load_terminal_records(path) → (records, resolved_path)   # 目录或文件均可
/result 现有键：job / visualization? / terminals? / metrics?
```

**本计划新增/变更契约：**

```
Settings 新增: pubchem_offline: bool = False (env PUBCHEM_OFFLINE)
worker: export 成功(succeeded|partial)后调 run_terminal_audit(export_dir)
  → export/terminal_audit.json = {schema, input, offline, summary{...}, results[audit_record...],
                                   available: true}
  失败 → export/terminal_audit.json = {available: false, error: str}（不抛出）
/result 增键: terminal_audit: dict | None
前端 ResultOut 增: terminal_audit?: {
  available: boolean; error?: string; offline?: boolean;
  summary?: Record<string, any>;
  results?: Array<{node_id, smiles, cs_score, rachel_classification,
    pubchem?: {best_cid?: number|null, best_cid_url?: string, queried?: boolean},
    pubchem_metrics?: {pubchem_cid_closed?: boolean, vendor_closed?: boolean},
    allowlist?: {hit?: boolean}, buyability_decision?: Record<string, any>}>
}
```

## File Structure

```
backend/
├── app/core/config.py                   # M3-T1: +pubchem_offline
├── app/services/terminal_audit.py       # M3-T1 新建: run_terminal_audit
├── app/worker/tasks.py                  # M3-T1: export 后调用审计
├── app/services/artifacts.py            # M3-T1: parse_export 增 terminal_audit
├── app/schemas/jobs.py                  # M3-T1: ResultOut.terminal_audit
├── tests/test_m3_terminal_audit.py      # M3-T1
frontend/src/
├── types.ts                             # M3-T2: +TerminalAudit 类型
├── api/hooks.ts                         # M3-T2: +useTrace
├── components/AuditTimeline.tsx         # M3-T2: 决策审计时间线
├── components/TerminalAuditPanel.tsx    # M3-T2: 终点审计表
├── pages/JobDetailPage.tsx              # M3-T2: 两新 Tab
└── tests/{audit-timeline,terminal-audit-panel}.test.tsx + fixtures/trace_steps.json
```

---

### Task M3-T1: 后端终点审计集成（worker + /result）

**Files:**
- Create: `backend/app/services/terminal_audit.py`
- Modify: `backend/app/core/config.py`、`backend/app/worker/tasks.py`、`backend/app/services/artifacts.py`、`backend/app/schemas/jobs.py`、`backend/tests/conftest.py`（_testing fixture 加 PUBCHEM_OFFLINE env）
- Test: `backend/tests/test_m3_terminal_audit.py`

**Interfaces:**
- Consumes: Rachel 审计工具（只读 import）、parse_export、worker export 流程（stats.export_dir）
- Produces: `run_terminal_audit(export_dir: Path, offline: bool | None = None) -> dict`（写 export/terminal_audit.json 并返回其内容；offline=None 时取 settings.pubchem_offline；terminals.json 缺失 → {"available": False, "error": "no terminals.json"}；任何异常捕获为 available=False，绝不抛出）；parse_export 返回增 `terminal_audit` 键（文件存在时）；ResultOut 增 `terminal_audit: dict | None = None`；worker 在 set_status(succeeded/partial) 前调用审计并把 `stats["terminal_audit_summary"] = payload.get("summary")` 写入（available 与否都写，便于观测）

- [ ] **Step 1: 失败测试**

```python
import json
from pathlib import Path
FIXT = Path("examples/result_demo/export")

def _run(offline=True):
    from app.services.terminal_audit import run_terminal_audit
    return run_terminal_audit(FIXT, offline=offline)

def test_audit_offline_produces_local_results(tmp_path, monkeypatch):
    # 复制 fixture 到 tmp（审计会写 terminal_audit.json，不能污染 examples/）
    import shutil
    dst = tmp_path / "export"; shutil.copytree(FIXT, dst)
    from app.services.terminal_audit import run_terminal_audit
    payload = run_terminal_audit(dst, offline=True)
    assert payload["available"] is True and payload["offline"] is True
    assert len(payload["results"]) == 6                       # demo terminals 数
    r0 = payload["results"][0]
    assert "pubchem_metrics" in r0 and "buyability_decision" in r0
    assert (dst / "terminal_audit.json").exists()
    # 幂等：重跑覆盖
    payload2 = run_terminal_audit(dst, offline=True)
    assert payload2["available"] is True

def test_audit_missing_terminals_degrades(tmp_path):
    from app.services.terminal_audit import run_terminal_audit
    payload = run_terminal_audit(tmp_path, offline=True)
    assert payload["available"] is False and "terminals" in payload["error"]

def test_audit_exception_never_raises(tmp_path, monkeypatch):
    import app.services.terminal_audit as ta
    monkeypatch.setattr(ta, "load_terminal_records", lambda p: (_ for _ in ()).throw(RuntimeError("boom")))
    payload = ta.run_terminal_audit(tmp_path, offline=True)
    assert payload["available"] is False and "boom" in payload["error"]

def test_worker_runs_audit_after_export(client, db, auth_headers_user, monkeypatch, tmp_path):
    # mock driver 正常收尾 + 预置 export 产物 → succeeded 后 /result 带 terminal_audit
    from app.db.models import LlmProvider
    from sqlalchemy import select
    p = db.scalar(select(LlmProvider)); p.model = "mock"; db.commit()
    import app.core.config as cfg
    monkeypatch.setattr(cfg.Settings, "data_dir", tmp_path, raising=False)
    jid = client.post("/api/jobs", headers=auth_headers_user,
                      json={"smiles": "CC(=O)Nc1ccc(O)cc1", "name": "m3"}).json()["id"]
    exp = tmp_path / jid / "export"; exp.mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.copy(FIXT / "terminals.json", exp / "terminals.json")
    body = client.get(f"/api/jobs/{jid}/result", headers=auth_headers_user).json()
    assert body.get("terminal_audit", {}).get("available") is True
    stats = client.get(f"/api/jobs/{jid}", headers=auth_headers_user).json()["stats"]
    assert "terminal_audit_summary" in stats
```

注：worker 内调用统一 `offline=get_settings().pubchem_offline`；conftest `_testing` autouse 增 `monkeypatch.setenv("PUBCHEM_OFFLINE", "true")` 保证第四例不触网。第四例中 mock LLM provider 的 finish-only 脚本会让 driver 立即 finalize+export（M2 后 export 落 workspace/export），随后审计在仅含 terminals.json 的目录上离线运行——正是要验证的降级路径。

- [ ] **Step 2: terminal_audit.py 实现**

```python
"""Route-completion PubChem terminal audit; failures degrade, never raise."""
from __future__ import annotations
import json, traceback
from pathlib import Path
from typing import Any

AUDIT_FILE = "terminal_audit.json"

def run_terminal_audit(export_dir: Path, offline: bool | None = None) -> dict:
    try:
        from Rachel.tools.pubchem_terminal_audit import (
            PubChemClient, audit_record, load_terminal_records,
        )
        if offline is None:
            from app.core.config import get_settings
            offline = get_settings().pubchem_offline
        records, _src = load_terminal_records(export_dir)
        client = PubChemClient(cache_dir=export_dir / ".pubchem_cache", offline=offline)
        results = [audit_record(r, client, include_vendors=not offline, query_reagents=False)
                   for r in records]
        from Rachel.tools.pubchem_terminal_audit import summarize
        payload: dict[str, Any] = {
            "schema": "rachel-v2-terminal-buyability-audit-002",
            "offline": bool(offline), "available": True,
            "summary": summarize(results), "results": results,
        }
    except Exception as exc:
        payload = {"available": False, "error": f"{type(exc).__name__}: {exc}",
                   "detail": traceback.format_exc()[-2000:]}
    try:
        export_dir.mkdir(parents=True, exist_ok=True)
        (export_dir / AUDIT_FILE).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    return payload
```

（若 `summarize` 名称与工具实际不符——以 grep 为准替换；工具模块顶部有 `def summarize`，main() 使用之。）

- [ ] **Step 3: 挂接 worker 与 parse_export / ResultOut**

- worker run_retro_job：成功分支（succeeded|partial、export_dir 存在）在写 stats 前：
```python
from app.services.terminal_audit import run_terminal_audit
audit_payload = run_terminal_audit(Path(export_dir))
stats["terminal_audit_summary"] = audit_payload.get("summary") or {"available": audit_payload.get("available")}
```
- artifacts.parse_export：`ta = _load(export_dir / "terminal_audit.json")`；存在则 `out["terminal_audit"] = ta`（incomplete 判定不因缺审计文件而变——审计本就可缺省）。
- schemas ResultOut：`terminal_audit: dict | None = None`（exclude_none 已开）。
- config Settings：`pubchem_offline: bool = False`；conftest `_testing`：`monkeypatch.setenv("PUBCHEM_OFFLINE", "true")`。

- [ ] **Step 4: 跑测试**（新文件 + 全套 59+4）
- [ ] **Step 5: Commit** `feat: post-route pubchem terminal audit with offline degradation`

---

### Task M3-T2: 前端两个审计面板 + Tab 接入

**Files:**
- Modify: `frontend/src/types.ts`（TerminalAudit 类型树，见契约）、`frontend/src/api/hooks.ts`（+useTrace）、`frontend/src/pages/JobDetailPage.tsx`（Tabs 增 audit/terminals 两项）
- Create: `frontend/src/components/AuditTimeline.tsx`、`frontend/src/components/TerminalAuditPanel.tsx`
- Create: `frontend/src/tests/fixtures/trace_steps.json`（从真实 JobStep 形状构造 12 步：含 init/next/reaction_sites/explore_site/try_action×2(一 error)/commit(含 reasoning+rejected+confidence)/accept(含 reason)/finalize/export/finish）
- Test: `frontend/src/tests/audit-timeline.test.tsx`、`frontend/src/tests/terminal-audit-panel.test.tsx`

**Interfaces:**
- Consumes: useTrace(id, enabled) = useQuery ["trace", id] → apiGet<{steps: JobStepStep[]}>(`/api/jobs/${id}/trace`)（JobStepStep 类型加 types.ts：seq/command/args/result_summary/status/tokens/duration_ms/created_at）；result.terminals、result.terminal_audit
- Produces: `<AuditTimeline jobId={id}/>`、`<TerminalAuditPanel terminals audit/>`

**AuditTimeline 规格：**
- 头部统计卡：总步数 / error 步数 / tokens 合计 / 累计耗时(ms→s)；refetch 按钮（useQuery refetch）
- 时间线列表：每行 = seq 序号徽章 + command（Badge，commit/accept 高亮 sky 色）+ 状态（ok=绿点/error=红点）+ tokens + duration + 时间(HH:mm:ss)；点击行展开（受控 expanded: Set<number>，可多开）：
  - args：`<pre>` JSON.stringify(args, null, 2)，mono text-xs，max-h-64 overflow-auto
  - result_summary：灰底引用块
  - command==="commit" 时在展开区顶部渲染：reasoning 引用块（黄色边框）+ confidence 徽章 + rejected 列表（每项一行，来自 args.rejected 数组，JSON 展示）
  - command==="accept" 时：args.reason 引用块
- 数据获取：useTrace(id, enabled=tab激活或job终态)；空 steps 显示"暂无步骤记录"

**TerminalAuditPanel 规格：**
- `audit?.available === false` 或 undefined：顶部琥珀警示条"终点审计不可用"（+ error 一行小字，data-testid="audit-unavailable"），下方仍渲染 terminals 基础表（无闭合徽章列）
- audit.available === true：顶部汇总条（audit.summary 的可用计数字段尽量展示：cid_closed x/y、vendor_closed a/b——summary 实际键以 fixture 为准，缺字段时从 results 计数兜底）+ offline 时注明"离线审计（本地分类）"
- 表列：结构（MoleculeView 120x80）/ SMILES（mono 截断+title）/ CS 分数（2位）/ CID（pubchem.best_cid 有 → `<a href={best_cid_url} target="_blank" rel="noreferrer">CID {best_cid}</a>`，无 → "—"）/ 闭合徽章两枚：`CID✓/✗`（pubchem_metrics.pubchem_cid_closed）与 `Vendor✓/✗`（vendor_closed）——绿/灰 Badge
- allowlist.hit 的行加"allowlist"小徽章

**测试要点：**
- audit-timeline：12 步 fixture → 12 行；error 步红点；点击 commit 行 → 展开 reasoning 文本与 rejected 项；统计卡数字正确
- terminal-audit-panel：可用 fixture（3 结果，2 cid_closed）→ 汇总 + 徽章 + CID 链接 href；不可用 fixture → audit-unavailable 且基础表仍渲染
- JobDetailPage 集成：succeeded job + result(含 terminals+audit) → Tab 列表五项（路线树/报告/审计/终点审计/文件），切到审计 Tab 出现时间线

- [ ] **Step 1: 失败测试（两组件 + 集成）**
- [ ] **Step 2: 实现（types→hooks→组件→JobDetailPage 接线）**
- [ ] **Step 3: 全前端测试 + build**
- [ ] **Step 4: Commit** `feat: decision audit timeline and terminal closure panel`

---

### Task M3-T3: 收尾（Tab 顺序与文案 + 全量回归 + 文档）

**Files:**
- Modify: `frontend/src/pages/JobDetailPage.tsx`（Tab 顺序定为 路线树/报告/决策审计/终点审计/文件）、`backend/README.md`（PUBCHEM_OFFLINE 环境变量说明：无外网服务器设 true 走离线审计）

**步骤：** 调整 Tab 顺序与标签文案统一（决策审计/终点审计）→ 后端全套 + 前端全套 + build 全绿 → 手动检查 dev 起服后 succeeded 任务两新 Tab 可渲染（可引用 M2 的 integration 脚本思路，不强制新脚本）→ Commit `chore: m3 tab ordering, docs and regression`

---

## Self-Review 记录

- **Spec 覆盖**：§5.3 决策审计（时间线+展开+commit理由/被拒候选）→ M3-T2 AuditTimeline；终点审计（结构/SMILES/CID链接/双徽章）→ TerminalAuditPanel；§7/§12 降级（审计不可用横幅+基础表兜底；offline 本地分类）→ T1+T2；§10 M3 验证"job_steps/terminals 数据贯通"→ trace 端点既有 + /result terminals/terminal_audit。M4（实时进度/SSE/admin页）与 M5 不在本计划。
- **占位符**：无 TBD；summary 字段名以 fixture 为准的兜底已明确写出（缺字段从 results 计数）。
- **类型一致性**：TerminalAudit 类型树与 audit_record 返回逐字段对齐；JobStepStep 与后端 JobStepOut 一致；useTrace 键 ["trace", id] 全计划唯一。
- **风险**：① `summarize` 符号名需 grep 核实（已注明以实际为准）；② 测试网络隔离由 PUBCHEM_OFFLINE env 保证；③ 审计耗时（6 terminal × pause 0.2s + 超时）在 job 收尾路径上可接受（离线≈0，在线最坏 ~1-2 分钟，worker 不阻塞他人）。