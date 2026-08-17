# Rachel-v2 系统完整分析

> 本文档基于 Rachel-v2 源码、系统文档（README.md / workflow.md / SKILL.md）以及 `result_demo/` 目录下 119 个 JSON 执行记录，对系统进行逐层解读。
> 目标读者：对逆合成规划感兴趣的初学者与进阶研究者。

---

## 一、Rachel 是什么

**Rachel 是一个"以化学信息为基础、由 LLM 主导的多步逆合成规划系统"。**

给定一个目标分子（比如某种药物候选），Rachel 帮你**反向推导**出"用什么简单原料、经过哪些反应步骤可以合成这个目标"。

但 Rachel 不是普通的"AI 生成合成路线"工具。它更准确的理解是：

> **逆合成路线状态机 + LLM 化学判断 + 自动验证与审计系统**

传统逆合成系统往往是"一次性生成器"——丢进去一个分子，吐出一条路线文本。Rachel 的思路完全不同——它把逆合成路线拆成一系列受控步骤：

1. 当前目标分子是什么？
2. 它有哪些可断键位点或反应机会？
3. 每个位点有哪些候选反应动作？
4. LLM 选择哪个动作，为什么？
5. 系统能否用 sandbox 验证这个动作？
6. 验证通过后，才把这一步写进路线树。
7. 然后把得到的前体分子作为新的当前节点继续拆解。
8. 最后路线完成后，再统一审计 terminal 起始原料是否有 PubChem CID 或 vendor 证据。

---

## 二、核心设计哲学

Rachel 的核心哲学可以概括为三点：

> **Rachel 提供信息，LLM 做决策。大胆假设，严格验证。**

这形成了一条严格的**职责边界**：

| 角色 | 负责什么 | 不负责什么 |
|------|---------|-----------|
| **化学工具层** (`chem_tools`) | 提供分子事实、候选反应、验证证据 | 不选择反应 |
| **编排层** (`main`) | 维护会话状态、路线树、决策历史 | 不判断化学合理性 |
| **验证门控** (Validation Gates) | 分类矛盾/风险/证据缺失 | 不替 LLM 选择路线 |
| **LLM / 化学家** | 设计路线、选择反应、裁决争议 | — |

关键设计原则：

1. **Chemistry first** — 化学真实与路线质量永远优先于模板分数、CS 分数和便利性
2. **Bold design, strict proof** — 大胆假设化学策略，但每一步都必须经过严格验证
3. **Actions are peer hypotheses** — 系统列出的 action 和 LLM 自定义 action 是并列假设，走同样的沙盒验证路径
4. **Gates inform, not decide** — 验证门控只分类证据状态（blocked / proof_required / inconclusive / warning / clear），不替你选路线
5. **One real event per commit** — 每次提交只允许一个真实的化学事件，多步想法通过 continuation 机制展开
6. **Audit every decision** — 每个被拒绝的方案、每张经验卡、每个 override 都保留在审计轨迹中
7. **Depth must add value** — 宁可接受诚实的高级 terminal，也不要虚假的深度拆分

---

## 三、系统架构（三层结构）

```
┌─────────────────────────────────────────────────┐
│           研究者 / LLM 化学判断层                  │
│   (路线假设、反应设计、证据协调、最终决策)           │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│              编排层 (Orchestration)                │
│   会话状态 │ BFS 队列 │ 路线树 │ 提交历史          │
│   retro_cmd │ retro_session │ retro_orchestrator  │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│              化学工具层 (Chem Tools)               │
│  断键分析 │ FGI │ 模板扫描 │ 分子信息 │ 验证器     │
│  bond_break │ fg_detect │ template_scan │ cs_score│
│  forward_validate │ atom_mapping │ site_audit     │
└─────────────────────────────────────────────────┘
```

### 代码结构速览

```
Rachel-v2/Rachel/
├── main/                    # 编排层
│   ├── retro_cmd.py         # 命令接口（JSON-in/JSON-out，唯一入口）
│   ├── retro_session.py     # 会话状态管理（门控、accept、commit 逻辑）
│   ├── retro_orchestrator.py # BFS 编排引擎（队列、树操作、finalize）
│   ├── retro_tree.py        # 路线树数据结构（MoleculeNode / ReactionNode）
│   ├── retro_state.py       # 审计状态持久化
│   ├── retro_report.py      # 正向合成报告生成
│   ├── retro_visualizer.py  # 可视化（分子图、反应图、树图）
│   ├── retro_output.py      # 导出全套产物
│   ├── prompt_mount.py      # 动态 prompt 挂载（经验卡、质量护栏）
│   ├── strategy_disclosure.py # 策略信息展示（site/reaction 菜单构建）
│   └── public_protocol.py   # 公共协议投影（legacy → v2 验证合约）
│
├── chem_tools/              # 化学工具层
│   ├── bond_break.py        # 断键分析与前体生成
│   ├── fg_detect.py         # 官能团检测
│   ├── template_scan.py     # 反应模板扫描
│   ├── mol_info.py          # 分子信息（描述符、环、手性等）
│   ├── cs_score.py          # 复杂度评分（CS score）
│   ├── smart_cap.py         # 智能封端（LLM 完成的结构提示）
│   ├── forward_validate.py  # 前向验证（模板重建 + 可行性评分）
│   ├── site_audit.py        # 位点保真度审计
│   ├── atom_mapping_audit.py # 原子映射审计（MCS 启发式）
│   ├── ring_topology_audit.py # 环拓扑审计
│   ├── validation_contract.py # 验证门控公共 v2 协议（核心！）
│   ├── validation_policy.py # 验证策略
│   ├── fg_warnings.py       # 官能团兼容性警告
│   └── templates/           # 反应模板库（10+ JSON 文件）
│       ├── reactions.json
│       ├── functional_groups.json
│       ├── protecting_groups.json
│       └── ...
│
├── tools/                   # 辅助工具（独立脚本）
│   ├── pubchem_terminal_audit.py     # PubChem 终点可购买性审计
│   ├── audit_terminal_buyability_batch.py # 批量审计
│   ├── visualize_reaction.py
│   └── llm_retro_platform.py
│
├── SKILL.md                 # LLM 面向的执行契约（硬规则）
├── workflow.md              # 工作流设计文档（维护参考）
├── experience_cards.json    # 经验卡（运行时动态挂载）
└── README.md                # 项目说明
```

---

## 四、Demo 执行结果概览

Demo 目标分子（`n5_9998`）：

- **SMILES**: `Cc1ncc(C)n2nc(CCc3ccc(O)c(NC(C)CCO)n3)nc12`
- **分子式**: C₁₈H₂₄N₆O₂
- **分子量**: 356.43
- **复杂度分数 (CS)**: 4.42（中等）
- **结构特征**: 3 个芳环、1 个手性中心、7 个可旋转键、伯醇 + 酚 + 仲芳胺

### 最终合成树

```
🎯 目标分子 (CS=4.4)
    ↓ 还原胺化 (Step 11)
  ├── 核心中间体 (CS=4.0)
  │     ↓ 烯烃加氢 (Step 10)
  │   └── 烯烃中间体 (CS=4.0)
  │       ↓ 硝基还原 (Step 9)
  │     └── 硝基中间体 (CS=4.2)
  │         ↓ 脱甲基化 (Step 8)
  │       └── 甲氧基中间体 (CS=4.2)
  │           ↓ HWE 烯化 (Step 7) ← 核心骨架组装事件
  │         ├── 醛基吡啶 (CS=2.7)
  │         │     ↓ 甲基氧化 (Step 4)
  │         │   └── 甲基吡啶 (CS=2.5)
  │         │         ↓ SNAr 甲氧化 (Step 2)
  │         │       ├── ✅ 氟硝基甲基吡啶 (CS=2.6)
  │         │       └── ✅ 甲醇 (CS=1.5)
  │         └── 膦酸酯 (CS=3.7)
  │               ↓ Arbuzov 反应 (Step 6)
  │             ├── 氯甲基并环 (CS=3.2)
  │             │     ↓ 醇→氯 (Step 5)
  │             │   ├── 羟甲基并环 (CS=3.2)
  │             │   │     ↓ 醛还原 (Step 3)
  │             │   │   └── 醛基并环 (CS=3.2)
  │             │   │         ↓ 甲基氧化 (Step 1)
  │             │   │       └── ✅ 三甲基并环核心 (CS=3.0)
  │             │   └── ✅ 二氯亚砜 (CS=2.0)
  │             └── ✅ 亚磷酸三乙酯 (CS=1.8)
  └── ✅ 4-羟基丁-2-酮 (CS=1.6)
```

### 6 种起始原料

| 原料 | CS 分数 | 类型 |
|------|---------|------|
| CC(=O)CCO（4-羟基丁-2-酮） | 1.6 | 简单 |
| CCOP(OCC)OCC（亚磷酸三乙酯） | 1.8 | 简单 |
| Cc1ccc(F)c([N+](=O)[O-])n1（氟硝基甲基吡啶） | 2.6 | 中等 |
| CO（甲醇） | 1.5 | 简单 |
| O=S(Cl)Cl（二氯亚砜） | 2.0 | 简单 |
| Cc1nc2c(C)ncc(C)n2n1（三甲基并环核心） | 3.0 | 中等 |

### 11 步反应概览

| 步骤 | 反应类型 | 验证门控 | 被拒绝的替代方案 |
|------|---------|---------|----------------|
| 1 | 甲基→醛基氧化 | warning | Vilsmeier（骨架不平衡）、缩醛（不是更简单前体） |
| 2 | SNAr 甲氧化 | missing_evidence | 硝化（硬阻断+区域选择性差）、Ullmann/Chan-Lam（不如 SNAr 直接） |
| 3 | 醛→醇还原 | clear | 3 个环断裂 action（前体不连贯） |
| 4 | 甲基→醛基氧化 | warning | Vilsmeier（电子贫化不利）、Swern（前体无效） |
| 5 | 醇→氯 (SOCl₂) **LLM 自定义** | missing_evidence | 自由基氯化（选择性差） |
| 6 | Arbuzov 膦酸酯化 **LLM 自定义** | missing_evidence | 系统 action 会破坏保留的核心 |
| 7 | HWE 烯化 **LLM 自定义** | missing_evidence | Wittig（无真实叶立德）、Julia（SMILES 无效）、Peterson（可及性差） |
| 8 | BBr₃ 脱甲基化 | warning | 先做烯烃再脱保护（酚在碱性条件下会被去质子化） |
| 9 | 硝基→胺还原 | missing_evidence | Wittig/Julia（前体不完整） |
| 10 | 烯烃加氢 | clear | Negishi/Kumada（需要未保护的氨基酚有机金属） |
| 11 | 还原胺化 | missing_evidence | SN2（仲溴代物消除风险）、Mitsunobu（兼容性差） |

---

## 五、完整单步流程的源码级解析

### 5.1 init — 创建会话

**源码路径**: `retro_cmd.py:231` → `RetroSession.create()`

创建 `session.json`，写入 target SMILES、max_depth、max_steps、terminal_cs_threshold。此时路线树只有一个目标节点，队列为空。

**demo 实际** (`00_init.json`):
```json
{"ok": true, "session_id": "deea6efc", "target": "Cc1ncc(C)n2nc(...)", "name": "n5_9998"}
```

### 5.2 next — 从 BFS 队列取分子 + 返回 compact 认知

**源码路径**: `retro_cmd.py:258` → `retro_session.prepare_next()`

实际行为：
1. 从 BFS 双端队列 `deque` 中弹出下一个 `(smiles, depth)` 对
2. 如果该分子 CS 低于阈值且无手性中心 → 自动标记 `auto_terminal`，跳过
3. 否则返回标准 `context(compact)` → 包含分子简报、官能团、反应机会概览

**demo 实际** (`01_next.json`): 返回 CS=4.42、31 个反应位点、52 种反应、4 张经验卡自动挂载。

### 5.3 route_plan / guide（可选）— 全局策略 + 专家指导

**源码路径**: `retro_session.py:316` (`route_plan`) / `retro_session.py:303` (`guide`)

`route_plan` 不改变路线树，只记录全局路线论题。后续每步 commit 都会检查当前 action 是否与 plan 对齐。

**demo 实际** (`02_route_plan.json`):
```json
{"route_mode": "hybrid", "revision": 0,
 "route_thesis": "Use a hybrid route: preserve the mature fused triazolopyrimidine-like core..."}
```

### 5.4 reaction_sites — 第一层 site/reaction 菜单

**源码路径**: `retro_cmd.py:349` → `strategy_disclosure.build_site_reaction_map()`

把 `disconnectable_bonds` + `fgi_options` 按真实反应位点分组，每个 site 暴露 `site_id`、`site_type`、`site_hint`、`competition_hint`。

**demo 实际** (`03_reaction_sites.json`): 返回 31 个 site，高竞争位点如 bond:17 有 5 种候选反应。

### 5.5 explore_site — 第二层同位点候选展开

**源码路径**: `retro_cmd.py:353` → `strategy_disclosure.expand_site_candidates()`

展开一个位点的所有 action，每个 action 有 `action_id`、`precursors_preview`、`risk_tags`、`heuristic_score`、`confidence`。

### 5.6 try_action — 沙盒验证（核心阶段）

**源码路径**: `retro_cmd.py:387` → `retro_session.try_action()` → `forward_validate` + `site_audit` + `validation_micro`

这是验证发生的地方。实际行为：

1. 根据 `action_id` 找到对应的前体方案
2. 调用 `forward_validate.py` 中的 `validate_forward()` — 用正向模板尝试从前体重建目标
3. 调用 `site_audit.py` 中的 `audit_site_retention()` — 检查位点保真度
4. 生成 `validation_micro` — 原子映射、图变化、环变化、FG 变化
5. 组装 `forward_validation.gate` — 包含 `gate_state`、`hard_blocks`、`soft_warnings`、`override_allowed`、`missing_evidence`
6. 追加到 `_sandbox_attempts` 列表（不写路线树！）

try_action 的结果通过 `_public_validation_result()` (`retro_cmd.py:100`) 中的 `build_validation_contract()` (`validation_contract.py:282`) 投影为公共 v2 协议。状态映射如下：

```python
# validation_contract.py 中的核心映射
_STATE_MAP = {
    "hard_block": "blocked",           # 化学矛盾 → 不能提交
    "override_required": "proof_required",  # 需要补证 → 可 override
    "missing_evidence": "inconclusive",     # 证据缺失 → 独立判断
    "warning": "warning",               # 有风险 → 必须在 reasoning 中说明
    "pass": "clear",                   # 无异议 → 正常化学审查
}
```

**demo 实际** (`05_try_bond17_reductive_amination.json`):
```json
{"forward_validation": {"gate": {"gate_state": "missing_evidence",
  "hard_blocks": [], "soft_warnings": [...], "missing_evidence": [...]}}}
```

### 5.7 sandbox_clear — 清空沙盒（可选）

**源码路径**: `retro_cmd.py:560`

归档当前沙盒所有 attempt 到 `_archived_sandbox`，然后清空。典型场景：对比被"污染"（多次试错后难以对比）时，清空后重新只跑最终选定的 action，得到干净的沙盒。

**demo 实际**: 多次出现 `sandbox_clear` 文件（如 `26_sandbox_clear_before_nitro.json`、`46_sandbox_clear_before_hwe_commit.json`），说明 LLM 在 commit 前经常清空沙盒以获得干净的单项验证。

### 5.8 sandbox_list — 沙盒对比视图

**源码路径**: `retro_cmd.py:484`

遍历 `_sandbox_attempts`，将每个 attempt 通过 `_public_validation_result()` 投影为 v2 验证合约，并按 `by_site` / `by_reaction` 分组索引。

**demo 实际** (`09_sandbox_bond17_compare.json`): 并列展示 3 个候选（还原胺化、SN2、Mitsunobu）的验证结果。

### 5.8 commit — 验证门控 + 审计后写入路线树

**源码路径**: `retro_cmd.py:575` → `retro_session.commit()` (`retro_session.py:2348`)

commit 是最复杂的阶段。它内部运行**两道门控**：

#### 门控 1：`_evaluate_site_retention_gate()` (`retro_session.py:1343`)

仅对 LLM 自定义 action（`source="llm_proposed"`）触发：
- 如果 `site_audit` 要求 strict 审计且位点有变化 → 需要 override 或提供证明
- 如果 reasoning 声称位点保持但无审计数据 → 直接阻断

#### 门控 2：`_evaluate_validation_gate()` (`retro_session.py:1279`)

读取沙盒 attempt 的 `forward_validation.gate`：

```
if gate 缺失 → "validation gate missing; commit blocked"
if gate_state == "hard_block" → "validation gate hard-blocked commit"
if gate_state == "override_required":
    if override.allowed == true AND override.reason 非空 → 放行
    else → "validation gate requires explicit override"
else (warning / missing_evidence / pass) → 放行
```

门控通过后，commit 还要做：
1. 构建 `LLMDecision` 对象（reasoning、confidence、rejected_alternatives）
2. 构建完整的 `decision_audit`（route_plan 对齐、经验卡、prompt 状态、route_sketch 来源、custom provenance）
3. 调用 `orch.commit_decision()` (`retro_orchestrator.py:1151`) 写入路线树
4. 检查是否有 rescue continuation 需要注册
5. 归档沙盒、清空沙盒、保存 session

commit 成功后返回 `step_id`（如 `rxn_1`），这就是写入路线树的证据。

### 5.9 accept terminal — 带 terminal rescue gate 的终点标记

**源码路径**: `retro_cmd.py:592` → `retro_session.accept_terminal()` (`retro_session.py:2544`)

accept 不是直接标记，它先过 `_terminal_rescue_gate()` (`retro_session.py:630`)：

```
1. 检查是否有 terminal_review sketch：
   → 没有 sketch → 直接放行
   → 有 sketch 但未尝试任何 rescue action → error，要求至少试一个
   → 有 sketch 且是多步 rescue + 已 commit 一步 → 允许继续 continuation
   → 有 sketch 且有 force_accept + reason → 放行
```

**demo 实际** — 三甲基并环核心 (`113_accept_trimethyl_fused_core.json`):
```json
{"ok": true, "action": "accepted_terminal",
 "terminal_rescue": {"terminal_review": true, "rescue_attempt_count": 0,
   "force_accept_without_rescue": true,
   "rescue_not_actionable_reason": "No credible parseable one-step rescue..."}}
```

系统不让你随便 accept 一个高级 terminal，必须先做 `route_sketch(terminal_review=True)` 尝试救援。如果救不了，必须显式说明为什么。

### 5.10 review_terminal — 重新打开已关闭的 terminal

**源码路径**: `retro_cmd.py:600` → `retro_session.review_terminal()` (`retro_session.py:2574`)

这是一个"已关闭路线的补救机制"。如果 finalize 后化学家认为某个 terminal 应该继续拆解，可以用 `review_terminal` 重新打开原树节点：

1. 验证该分子确实在路线树中且状态为 terminal
2. 验证它不是已被展开过的产物节点（已展开的不能再打开）
3. 如果步骤预算已用完，需要提供 `additional_steps > 0`
4. 将该分子重新标记为 intermediate，放回 BFS 队列头部
5. 后续走标准的 `next → site → action → validation → commit` 循环
6. 扩展完成后需要再次 `finalize`

### 5.11 finalize — 关闭编排

**源码路径**: `retro_cmd.py:644` → `retro_session.finalize()` (`retro_session.py:2708`) → `orch.finalize()` (`retro_orchestrator.py:1954`)

实际行为：
1. **先检查是否有未完成的 rescue continuation** → 如果有，返回 error，不让 finalize
2. 清空队列中剩余分子，全部标记为 terminal
3. 如果路线树完整 → `tree.complete(summary)`；否则 → `tree.fail(summary)`

**demo 实际** (`115_status_before_finalize.json`):
```json
{"steps_executed": 11, "pending_count": 0, "tree_complete": true,
 "active_rescue_continuations": []}
```

只有这三个条件同时满足，finalize 才会成功。

### 5.12 report + export — 产物生成

**源码路径**: `retro_cmd.py:648-664` → `retro_report.generate_forward_report()` + `retro_output.export_results()`

report 遍历路线树，把每步 reaction node 的 `LLMDecision`（reasoning、rejected、validation gate、experience cards）展开为正向合成文本。

export 生成全套产物：

```
输出目录/
├── SYNTHESIS_REPORT.html    # 自包含可视化 HTML（分子图 + 反应图 + 树图）
├── SYNTHESIS_REPORT.md      # Markdown 报告
├── report.txt               # 正向合成纯文本
├── tree.json                # 完整路线树 JSON（可恢复会话）
├── tree.txt                 # 文本渲染的树
├── terminals.json           # 起始原料清单（CS + classification）
├── visualization.json       # nodes/edges 图数据（供前端渲染）
├── session.json             # 完整会话快照
└── images/                  # 分子图 + 反应图 + 合成树总览
```

### 5.13 Post-route terminal audit — 路线外独立审计

**源码路径**: `tools/pubchem_terminal_audit.py` + `tools/audit_terminal_buyability_batch.py`

这个阶段不在核心运行循环中，而是 export 之后的独立后处理脚本：

1. **本地化学过滤**：排除盐类、反离子、金属有机试剂（Li、Mg、Zn、Cu、Sn...）、无机试剂
2. **白名单匹配**：检查 `terminal_allowlist.json`
3. **PubChem 查询**：对每个 terminal 的 canonical SMILES 查询 PubChem CID
4. **Vendor 供应证据检查**：记录 buyability 状态
5. **批量审计报告**：生成 per-run 和汇总的 CSV/Markdown 审计报告

在 demo 的 6 个 terminal 中，`Cc1nc2c(C)ncc(C)n2n1`（CS=3.0 的三甲基并环杂芳核）正是 Rachel 在 terminal review 中以 `force_accept_without_rescue=true` 接受的那个——post-route audit 就是为了回答"这个 terminal 到底能不能买到"。

---

## 六、完整状态机全景图

```
┌─────────────────────────────────────────────────────────────┐
│                    Rachel-v2 完整单步流程                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────┐                                                  │
│  │ init │ 创建 session.json，写入目标 + 阈值               │
│  └──┬───┘                                                  │
│     ▼                                                       │
│  ┌──────┐  BFS 取分子                                      │
│  │ next │  → quick_pass 自动 terminal 跳过                 │
│  └──┬───┘  → standard 返回 compact 认知                    │
│     ▼                                                       │
│  ┌──────────────┐  可选：记录全局路线论题                     │
│  │ route_plan   │  (不改变路线树，仅策略上下文)               │
│  │ guide        │  可选：记录合成专家自然语言指导               │
│  └──┬─────────┘                                            │
│     ▼                                                       │
│  ┌───────────────┐  第一层：按真实位点分组                    │
│  │ reaction_sites│  返回 site_reaction_map                   │
│  └──┬──────────┘  (bond:17 → 5 reactions, ...)             │
│     ▼                                                       │
│  ┌──────────────┐  第二层：展开一个位点的所有候选              │
│  │ explore_site │  返回 actions[] + precursors_preview       │
│  └──┬──────────┘  + risk_tags + confidence                 │
│     ▼                                                       │
│  ┌──────────────┐  沙盒验证（不写树！）                      │
│  │  try_action  │  → forward_validate (正向模板重建)          │
│  └──┬─────────┘  → site_audit (位点保真度)                  │
│     │             → validation_micro (原子映射/图变/环变)     │
│     │             → 组装 forward_validation.gate             │
│     ▼                                                       │
│  ┌───────────────┐  紧凑对比视图                            │
│  │  sandbox_list │  → 每个 attempt 的 v2 validation 合约     │
│  └──┬──────────┘  → by_site / by_reaction 分组索引         │
│     ▼                                                       │
│  ┌────────────────┐  (可选) 沙盒被污染时清空重跑            │
│  │sandbox_clear │  归档旧 attempt，清空沙盒               │
│  └──┬─────────┘                                        │
│     ▼                                                       │
│  ┌──────────────────────────────────────────────┐           │
│  │           commit — 两道门控后才写树           │           │
│  │                                              │           │
│  │  门控 1: _evaluate_site_retention_gate       │           │
│  │    (仅 LLM custom action)                    │           │
│  │    strict audit + changed site → 需 override │           │
│  │                                              │           │
│  │  门控 2: _evaluate_validation_gate            │           │
│  │    gate 缺失          → blocked              │           │
│  │    hard_block         → blocked              │           │
│  │    override_required  → proof_required        │           │
│  │    missing_evidence   → inconclusive          │           │
│  │    warning            → warning               │           │
│  │    pass               → clear                 │           │
│  │                                              │           │
│  │  → 构建 LLMDecision + decision_audit         │           │
│  │  → orch.commit_decision() 写入路线树         │           │
│  │  → 注册 rescue continuation（如有）           │           │
│  │  → 归档沙盒 + 保存 session                   │           │
│  └──┬─────────────────────────────────────────┘           │
│     │                                                       │
│     ├──→ 回到 next（继续拆解前体）                          │
│     │                                                       │
│     └──→ accept terminal（如果当前分子是终点）               │
│            │                                                │
│            ▼                                                │
│     ┌──────────────────────┐                                │
│     │ _terminal_rescue_gate│  终点救援门控                   │
│     │                      │                                │
│     │ 无 sketch → 放行        │                                │
│     │ 有 sketch → 必须先试   │                                │
│     │ 多步 rescue → 先 commit │                                │
│     │ force_accept → 说明理由│                                │
│     └──┬───────────────────┘                                │
│        │                                                  │
│        ├──→ 回到 next（继续其他前体）                       │
│        │                                                  │
│        ▼  所有 leaf 都 terminal                            │
│  ┌──────────┐  检查 rescue continuation                   │
│  │ finalize │  → 有未完成 → error                          │
│  └──┬───────┘  → 队列清空 → tree.complete()              │
│     ▼                                                       │
│  ┌────────┐  生成正向合成报告（含每步审计证据）            │
│  │ report │  → 每步的 reasoning / rejected / gate / cards  │
│  └──┬─────┘                                             │
│     ▼                                                       │
│  ┌───────┐  导出全套产物                                   │
│  │ export│  → HTML/MD/TXT/JSON/images                      │
│  └──┬────┘                                                 │
│     ▼                                                       │
│  ┌──────────────────────────────────────────┐               │
│  │  Post-route terminal audit (独立脚本)    │               │
│  │                                          │               │
│  │  1. 本地化学过滤（排除盐/金属/无机）    │               │
│  │  2. PubChem CID 查询                     │               │
│  │  3. Vendor 供应证据检查                  │               │
│  │  4. 白名单匹配                           │               │
│  │  5. 生成 buyability 审计报告              │               │
│  └──────────────────────────────────────────┘               │
│                                                             │
│  ┌──────────────────────────────────────────┐               │
│  │  review_terminal（可选，补救机制）       │               │
│  │  重新打开已关闭的 terminal leaf，     │               │
│  │  走标准 next→site→action→commit 循环 │               │
│  │  扩展完成后需再次 finalize            │               │
│  └──────────────────────────────────────────┘               │
└─────────────────────────────────────────────────────────────┘
│     │                      │                                │
│     │ 有 sketch 未尝试 →    │                                │
│     │   error, 要求试一个   │                                │
│     │ 多步 rescue 需续作 → │                                │
│     │   必须先 commit      │                                │
│     │ force_accept + reason│                                │
│     │ → 放行               │                                │
│     └──┬───────────────────┘                                │
│        │                                                  │
│        ├──→ 回到 next（继续其他前体）                       │
│        │                                                  │
│        ▼  所有 leaf 都 terminal                            │
│  ┌──────────┐  检查 rescue continuation                   │
│  │ finalize │  → 有未完成 → error                          │
│  └──┬───────┘  → 队列清空 → tree.complete()              │
│     ▼                                                       │
│  ┌────────┐  生成正向合成报告（含每步审计证据）            │
│  │ report │  → 每步的 reasoning / rejected / gate / cards  │
│  └──┬─────┘                                             │
│     ▼                                                       │
│  ┌───────┐  导出全套产物                                   │
│  │ export│  → HTML/MD/TXT/JSON/images                      │
│  └──┬────┘                                                 │
│     ▼                                                       │
│  ┌──────────────────────────────────────────┐               │
│  │  Post-route terminal audit (独立脚本)    │               │
│  │                                          │               │
│  │  1. 本地化学过滤（排除盐/金属/无机）    │               │
│  │  2. PubChem CID 查询                     │               │
│  │  3. Vendor 供应证据检查                  │               │
│  │  4. 白名单匹配                           │               │
│  │  5. 生成 buyability 审计报告              │               │
│  └──────────────────────────────────────────┘               │
└─────────────────────────────────────────────────────────────┘
```

---

## 七、从 Demo 中可以看到的核心特点

### 7.1 有状态规划 vs 一次性生成

Demo 经过了 119 个 JSON 交互才完成 11 步路线。每次交互都有明确的决策边界。被拒绝的方案（如 SN2、Mitsunobu、Vilsmeier）都被完整记录在审计轨迹中。

### 7.2 沙盒验证 before commit

每个反应在写入路线树之前都必须在沙盒中验证。例如 Step 11（还原胺化）在沙盒中同时测试了 3 个候选：

```
[0] 还原胺化 — gate=inconclusive, forward=True  ✅ 选中
[1] SN2      — gate=inconclusive, forward=True  ❌ 仲溴代物风险
[2] Mitsunobu — gate=warning, forward=True      ❌ 兼容性差
```

### 7.3 LLM 自定义 action 作为"并列假设"

Steps 5、6、7 都是系统没有模板的反应，由 LLM 通过 `propose_action` 自主设计，然后走同样的沙盒验证路径。Rachel 不把 LLM 的方案当二等公民。

### 7.4 验证门控分类（不是简单分数）

五个门控状态各有语义：

- **blocked**: 化学矛盾或系统错误，绝对不能提交
- **proof_required**: 需要补充证据（不是自动拒绝），LLM 可以补证后 override
- **inconclusive**: 区分"化学证据不足"和"工具覆盖不足"，LLM 自行判断
- **warning**: 可以提交，但 reasoning 中必须说明如何处理风险
- **clear**: 无异议，但正常的化学审查仍然需要

### 7.5 经验卡动态挂载

系统根据当前阶段和分子特征动态加载经验卡：
- 看到"电子贫化吡啶" → 挂载"电子态策略"卡
- 做第一计划前 → 挂载"路线模式分类"卡
- 审查高级 terminal → 挂载"短路线救援"卡

### 7.6 Terminal accept 也要过门控

`_terminal_rescue_gate` 确保不能偷懒接受高级 terminal。demo 中三甲基并环核心（CS=3.0）虽然被接受，但必须先做 `route_sketch(terminal_review=True)` 尝试救援，然后以 `force_accept_without_rescue=true` + 明确理由才放行。

### 7.7 Finalize 也有安全阀

有未完成的 rescue continuation 时 finalize 被阻断。确保多步 rescue 意图要么走完，要么显式放弃。

### 7.8 Post-route audit 是最终质量兜底

路线生成完毕后，独立脚本对每个 terminal 进行 PubChem CID 查询和 vendor 供应检查，回答"这些起始原料真的能买到吗"。

---

## 八、Rachel 与传统逆合成本质区别

| 维度 | 传统系统 | Rachel |
|------|---------|--------|
| **规划模式** | 一次性生成 | 有状态循环 (state→action→validation→commit) |
| **验证时机** | 事后检查或无检查 | 提交前沙盒验证，两道门控 |
| **拒绝处理** | 丢弃 | 保留为审计痕迹，可追溯；sandbox_clear 只归档不清除 |
| **LLM 角色** | 黑盒生成器 | 化学决策层（第一公民） |
| **自定义反应** | 不支持 | propose_action + 同等沙盒验证 |
| **路线策略** | 隐含在 prompt 中 | 显式 route_plan + 可修订，每步 commit 检查对齐 |
| **保护基** | 常忽略 | 必须是显式树节点，不能只写在 reasoning 里 |
| **Terminal 审查** | CS 低于阈值即接受 | 必须做 mini-route 救援评估 + force_accept 需显式理由 |
| **Finalize** | 无 | 检查 rescue continuation 完整性，未完成则阻断 |
| **补救机制** | 无 | review_terminal 可重新打开已关闭 terminal |
| **产出可购买性** | 不验证 | Post-route PubChem/vendor 独立审计 |
| **输出** | 文本路线 | 结构化树 + 审计报告 + 可视化 + 可恢复会话 |