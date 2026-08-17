# Rachel 技术参考

## 0. 项目概览（由原 readme 合并）

本节整合了原根层 `readme.md` 中偏技术说明的内容，作为进入命令细节和数据结构之前的总览入口。

### 0.1 项目定位

Rachel 是一个以结构化化学信息为基础、由 LLM/化学家主导决策的计算机辅助多步逆合成系统。它通过 JSON 命令接口提供分子事实、候选反应空间、验证观察、证明义务和持久化审计状态；路线策略、反应设计、前体补全及最终化学判断仍由 LLM/化学家负责。系统的目标不是替代化学判断，而是让大胆的路线假设在写入路线树前必须经过可检查的严格验证。

### 0.2 目录结构

```text
Rachel/
├── main/                        # 编排引擎（LLM 交互层）
│   ├── retro_cmd.py             # LLM 命令接口
│   ├── retro_session.py         # JSON 会话持久化 + 沙盒管理
│   ├── retro_orchestrator.py    # BFS 编排器 + 沙盒 + 终止判定
│   ├── retro_tree.py            # 合成树数据模型
│   ├── retro_state.py           # 审计状态
│   ├── retro_report.py          # 正向报告与可视化数据
│   ├── retro_output.py          # 结果导出
│   ├── retro_visualizer.py      # HTML/MD 报告与图像可视化
│   ├── strategy_disclosure.py   # CandidateUnit、site-first disclosure helper
│   └── prompt_mount.py          # 动态 prompt_brief 与经验卡挂载
│
├── chem_tools/                  # 化学工具层
│   ├── _rdkit_utils.py          # RDKit 公共工具
│   ├── mol_info.py              # 分子分析
│   ├── fg_detect.py             # 官能团识别
│   ├── template_scan.py         # 模板扫描
│   ├── bond_break.py            # 断键执行
│   ├── forward_validate.py      # 正向验证
│   ├── cs_score.py              # 复杂度评分
│   ├── fg_warnings.py           # 官能团冲突警告
│   ├── smart_cap.py             # 智能断键推理
│   └── templates/               # 反应模板库
│
├── tools/                       # 独立工具脚本
├── experience_cards.json        # 机器可读短经验卡
├── experience_cards.md          # 人工维护经验卡
├── experience.md                # 长经验沉淀，不默认注入 LLM
├── SKILL.md                     # LLM 操作手册
├── refs.md                      # 本技术参考
└── workflow.md                  # 工作流说明
```

Rachel-v2 根目录另有：

```text
validation/        # 当前核心验证测试，位于 runtime 包外
archive/           # 迁出的旧 docs/tests/data/论文材料/实验产物
walkthrough_runs/  # 真实路线诊断、payload probe、导出缓存
analysis/          # 临时分析与开发辅助材料
```

### 0.3 快速开始

```python
from Rachel.main import RetroCmd

cmd = RetroCmd("my_session.json")

# 1. 创建会话
cmd.execute(
    "init",
    {
        "target": "CC(=O)Nc1ccc(O)cc1",
        "name": "Paracetamol",
        "terminal_cs_threshold": 1.5,
    },
)

# 2. 取当前待决策分子
ctx = cmd.execute("next", {})
sites = cmd.execute("reaction_sites", {})

# 3. 第一层选真实 reaction site，第二层展开同 site 动作
site_id = sites["site_reaction_map"][0]["site_id"]
detail = cmd.execute("explore_site", {"site_id": site_id})

# 4. LLM/化学家比较机理、位点、前体现实性与风险后，沙盒验证所选动作
action_id = detail["actions"][0]["action_id"]
attempt = cmd.execute("try_action", {"action_id": action_id})
cmd.execute("sandbox_list", {})
validation = attempt["validation"]

# 5. 提交决策
committed = cmd.execute(
    "commit",
    {
        "idx": attempt["attempt_idx"],
        "expected_action_id": action_id,
        "reasoning": "写清 site、前体、原子账、validation gate 和被拒动作。",
        "confidence": "medium",
        "rejected": [],
    },
)
assert committed.get("step_id")
```

### 0.4 核心设计

- 角色边界：Rachel 提供信息、挑战和审计，LLM/化学家负责路线与反应决策
- 化学质量优先：机理、原子来源、位点、拓扑、选择性、兼容性和路线价值高于模板/名称/评分
- 大胆假设、严格验证：系统未列出的更优化学可以通过 `route_sketch -> propose_action -> try_action` 成为一等候选
- gate 只分类证据状态：真实矛盾、补证义务、警告和工具限制分开表达，不替 LLM 选择反应
- 双类型节点图：`MoleculeNode + ReactionNode`，以 canonical SMILES 去重
- BFS 编排：广度优先展开，自动处理 terminal 分子
- 沙盒机制：`try_action` 不写入主树，`commit` 后才持久化
- 三层 LLM 上下文：`context(compact)` 分子认知、`reaction_sites()` 第一层 site 菜单、`explore_site(site_id)` 第二层动作展开
- 默认上下文只暴露 `prompt_brief`，不反复注入完整 `prompt_mount`、`SKILL.md` 或 `experience.md`
- JSON 持久化：单文件保存完整状态，支持中断恢复
- LLM 自提前体：`propose_action` 只登记动作，仍必须用 `try_action(custom_id)` 验证
- 智能断键推理：`smart_cap` / `custom_cap` 只作专家辅助，不能直接 commit
- 公开验证协议：`blocked`、`proof_required`、`inconclusive`、`warning`、`clear`，并将化学矛盾、补证义务和工具覆盖不足分开
- 可视化报告：可导出 HTML/Markdown 结果与分子、反应图像

### 0.5 依赖

- Python 3.10+
- RDKit
- `numpy`
- `Pillow`

### 0.6 测试

```powershell
conda activate rachel-v2
python -m pytest Rachel\main\test_strategy_disclosure.py -q
python -m pytest validation\tests\test_compact_bond_identifiers.py validation\tests\test_site_anchor_audit.py validation\tests\core\unit -q
```

### 0.7 相关文档

- `SKILL.md`：默认可执行契约；普通运行优先读取
- command output + `prompt_brief`：当前节点的动态事实和义务
- `workflow.md`：状态机、设计哲学、上下文披露和维护协议
- `experience_cards.md`：短经验卡人工维护视图；卡片只提醒，不裁决化学
- `experience_cards.json`：运行时动态经验卡来源
- `experience.md`：长经验先验，不默认注入运行时上下文
- `refs.md`：命令字段、数据结构与导出协议的技术参考
- `chem_tools/README.md`：化学工具层说明

## 1. RetroCmd 命令详情

### init

创建新会话，初始化合成树和编排器。

```python
cmd.execute("init", {
    "target": "CC(=O)Nc1ccc(O)cc1",  # 必填，目标分子 SMILES
    "name": "Paracetamol",            # 可选，名称
    "terminal_cs_threshold": 2.25,    # CS ≤ 此值通常判定为 terminal；已指定手性中心仍需 LLM review
    "max_steps": 50,                  # 最大反应步数
    "max_depth": 15,                  # 最大树深度
})
```

返回: `{ok, session_id, session_file, target, name}`

Init parameter starting points:

| 目标复杂度 | `terminal_cs_threshold` | `max_steps` |
|-----------|--------------------------|-------------|
| 简单 (CS < 2) | 1.5 | 10 |
| 中等 (CS 2-4) | 2.3 | 30 |
| 复杂 (CS > 4) | 2.25 | 50 |

这些只是起点；最终应以化学机理、路线质量、目标复杂度和用户要求为准。

含已指定手性中心的低-CS 分子不会因阈值自动 quick-pass。历史 run 或已 `finalize` 路线中关闭的 terminal 可用 `review_terminal` 重新送入标准 LLM 决策队列；成功后路线回到 `in_progress`，复用原 molecule node、force-standard 路径和既有反应历史，并在扩展路线闭合后要求再次显式 `finalize`。已展开的 product 不能 reopen。

```python
cmd.execute("review_terminal", {
    "smiles": terminal_smiles,
    "reason": "chemist requests deeper decomposition",
    "additional_steps": 10,
})
```

`additional_steps` 可省略或设为 `0`；提供时必须是非负整数。当 `steps_executed >= max_steps` 时，必须显式提供正数扩容，否则返回 `step budget exhausted` 且不修改会话。

### next

取下一个待决策分子。默认自动跳过 quick_pass terminal（CS 低、重原子少、无可断键），
只在遇到 standard 分子时停下。若存在 pending strategy continuation，则对应 precursor
会被强制作为 standard 节点返回，即使它原本满足 quick_pass。

```python
ctx = cmd.execute("next", {})
# 返回 compact 上下文，或 {"action": "queue_empty"} 表示编排完成
```

返回的 compact 上下文结构是分子级认知包，不内嵌完整第一层动作菜单：

```json
{
  "status": { "target", "status", "steps_executed", "pending_count", ... },
  "current": {
    "action": "awaiting_decision",
    "decision_tier": "standard",
    "smiles": "CC(=O)Nc1ccc(O)cc1",
    "node_id": "mol_0",
    "depth": 0,
    "cs_score": 1.3,
    "classification": "trivial",
    "is_terminal": true,
    "is_target": true
  },
  "molecule_brief": { "heavy_atoms": 11, "rings": 1, "hetero_atoms": 3 },
  "functional_group_brief": [
    { "name": "amide_generic", "count": 1 }
  ],
  "complexity_brief": { "cs_score": 1.3, "classification": "trivial" },
  "warnings": [],
  "reaction_opportunity_brief": {
    "site_count": 2,
    "total_reaction_count": 4,
    "action_count": 6,
    "competing_site_count": 1,
    "high_competition_sites": ["bond:0"],
    "reaction_names": ["Amide Bond Formation", "Buchwald-Hartwig"],
    "first_layer_command": "reaction_sites()"
  },
  "commands": {
    "first_layer": "reaction_sites()",
    "action_sandbox": "try_action(action_id)",
    "custom_action": "propose_action(...)"
  },
  "prompt_brief": {
    "stage": "context_compact",
    "events": ["stage.context_compact"],
    "next_actions": ["reaction_sites()"],
    "quality_guardrails": [
      "Chemical plausibility and route quality outrank template score, CS score, and local convenience.",
      "Each committed step must be one real chemical event with a plausible mechanism and correct site.",
      "Preserve scaffold topology; explicitly justify any ring construction, opening, or scaffold change.",
      "Account for key C/N/S/halogen/protecting-group atoms and missing small molecules before commit.",
      "Install reactive temporary handles late; protection/deprotection must be explicit tree steps.",
      "Prefer honest advanced terminal acceptance over speculative low-confidence deep disconnections.",
      "If system actions miss a sound route, propose a complete one-step custom reaction/precursor set, then validate and audit it before commit."
    ]
  }
}
```

若当前节点来自多步策略续作，`current.prompt_brief` 会额外包含
`strategy_continuation_brief`，只需读取其中的 focus molecule 和下一步摘要。

### context

获取当前分子的上下文。

```python
cmd.execute("context", {"detail": "compact"})
```

按需获取当前活跃分子的完整静态结构事实：

```python
cmd.execute("context", {"detail": "structure"})
```

返回仍使用常规 `status/current` 外层结构。完整记录位于
`current.molecule_structure`，字段包括：

- `smiles`：canonical SMILES
- `formula`
- `mw`：Rachel 现有的平均分子量，不是 exact mass
- `descriptors`：`logP`、`HBD`、`HBA`、`TPSA`、`rotatable_bonds`、
  `Fsp3`、`ring_count`、`aromatic_ring_count`、`heterocycle_count`
- `atoms`：`idx`、`element`、`charge`、`hybridization`、`in_ring`、
  `aromatic`、`num_hs`、`neighbors`
- `bonds`：`idx`、`atoms`、`bond_type`、`in_ring`、`aromatic`、
  `conjugated`
- `rings`：成员 `atoms`、`size`、`aromatic`、`heterocyclic`
- `stereo`：手性中心及双键立体信息
- `symmetry`
- `scaffold`

该记录按需计算，不写入 session、route tree 或 compact payload。

说明：
- 默认 `next()` 与 `context(detail="compact")` 返回同一套 compact cognition。
- compact 不包含 `bond_summary`、`fgi_summary`、`reaction_families`、`strategy_groups` 或完整 `reaction_menu`。
- 需要完整第一层动作时调用 `reaction_sites()`。
- 需要旧字段或内部索引时显式调用 `context(detail="diagnostic")`；diagnostic 不作为默认 LLM 上下文。
- `context(detail="full")` 表示完整 action-space context；`diagnostic` 表示
  legacy/internal diagnostics，二者都不是 structure detail 的别名。

### reaction_sites

返回完整第一层 site-first 菜单。第一层按真实反应位点分组，而不是按手写 strategy group 或 reaction family 分组。

```python
cmd.execute("reaction_sites")
```

核心字段：

```json
{
  "site_reaction_map": [
    {
      "site_id": "bond:10",
      "site_type": "bond",
      "site_hint": "Ar-N single bond, fused heteroaryl C-N site",
      "action_count": 5,
      "reaction_count": 5,
      "competition_hint": "5 reactions compete at this site",
      "reactions": [
        {
          "reaction_id": "reaction:snar_n_nucleophile",
          "reaction_name": "SNAr N-Nucleophile",
          "action_count": 1,
          "source_summary": ["bond"],
          "risk_hint": "check leaving group, electronics, and site fidelity"
        }
      ],
      "next_step": "explore_site('bond:10')"
    }
  ],
  "prompt_brief": { "stage": "reaction_sites", "next_actions": ["explore_site(site_id)"] }
}
```

### explore_site

展开一个真实 site 下的所有动作实例，用于第二层同位点比较。

```python
cmd.execute("explore_site", {"site_id": "bond:10"})
```

返回核心字段：

```json
{
  "site_id": "bond:10",
  "site_type": "bond",
  "site_hint": "Ar-N single bond",
  "action_count": 5,
  "reaction_count": 5,
  "competition_hint": "same-site competing reactions present",
  "reactions": [
    { "reaction_id": "reaction:snar_n_nucleophile", "reaction_name": "SNAr N-Nucleophile", "action_count": 1 }
  ],
  "actions": [
    {
      "action_id": "bond:10:alt:0",
      "reaction": { "id": "reaction:snar_n_nucleophile", "name": "SNAr N-Nucleophile" },
      "source": "bond",
      "template_id": "N01_snar_n_nucleophile",
      "precursors_preview": ["...", "..."],
      "bond_idx": 10,
      "alt_idx": 0,
      "risk_tags": ["site_fidelity", "heteroaryl"]
    }
  ],
  "next_step": "try_action(action_id)",
  "prompt_brief": { "stage": "explore_site", "next_actions": ["try_action(action_id)"] }
}
```

### try_action

标准 sandbox 入口。它根据 `action_id` 自动分派到 bond、FGI 或 custom precursor 执行路径。Smart-capping action 是结构提示；直接调用会返回 `llm_completion_required`，不会创建 sandbox attempt，需先用 `propose_action` 补全为真实一步反应。

```python
cmd.execute("try_action", {"action_id": "bond:10:alt:0"})
```

返回核心字段：

```json
{
  "success": true,
  "action_id": "bond:10:alt:0",
  "source": "bond",
  "reaction_type": "SNAr N-Nucleophile",
  "precursors": ["...", "..."],
  "forward_validation": {
    "pass": true,
    "feasibility_score": 0.72,
    "gate": {
      "gate_state": "pass",
      "commit_policy": "allow"
    }
  },
  "attempt_idx": 0,
  "prompt_brief": { "stage": "try_action", "next_actions": ["sandbox_list"] }
}
```

### guide

记录合成专家对当前 active node 的自然语言方向。它只影响后续
`prompt_brief` 和 commit 审计，不直接写入 route tree。

```python
cmd.execute("guide", {
    "text": "Prioritize the N-aryl SNAr site and avoid early fused-core disassembly.",
    "intent": "reaction_hint",
    "reaction_hint": "SNAr N-aryl disconnection"
})
```

返回核心字段：

```json
{
  "ok": true,
  "guidance_id": "cg_...",
  "chemist_guidance": [
    {"id": "cg_...", "intent": "reaction_hint", "summary": "Prioritize the N-aryl SNAr site..."}
  ],
  "prompt_brief": {
    "stage": "reaction_sites",
    "events": ["stage.reaction_sites", "chemist.directive", "chemist.reaction_hint"]
  },
  "next_step": "reaction_sites()"
}
```

Raw `text` 只保存在 session/audit provenance 中；默认 LLM payload 不应读取完整 raw 指导。

### route_plan

设置或修订跨节点常驻的全局合成路线 thesis。它不写 route tree，不验证
action，也不替代 `route_sketch`；默认 LLM payload 只读取短
`prompt_brief.route_plan_brief`。

复杂目标有两条合法入口：通常先从 target、`molecule_brief` 和
`functional_group_brief` 登记短 revision-0 provisional seed，再用
`reaction_sites` / `explore_site` 证据完整重述为 evidence-enriched
revision 1；若分子级事实不足以形成有用 seed，则先检查位点，第一次
`route_plan` 直接登记 evidence-first complete revision 0。后续只有记录过的
实质路线主张发生变化时才修订；催化剂、溶剂、试剂或模板实现细节变化通常
不单独触发修订。每次修订都必须完整重述当前 plan，因为命令是替换而非字段合并。

plan-first 路径的短 seed 可以是：

```python
cmd.execute("route_plan", {
    "route_thesis": "Preserve the mature heteroaryl core and test a late N-aryl disconnection first.",
    "route_mode": "late_fgi",
    "mode_evidence": ["target-level facts show an established heteroaryl core"],
    "strategic_risks": ["late substitution may fail if the core is too deactivated"],
    "revision_triggers": ["site evidence contradicts the proposed N-aryl disconnection"],
    "revision_reason": "initial"
})
```

相关位点证据到位后，完整重述 evidence-enriched revision 1：

```python
cmd.execute("route_plan", {
    "route_thesis": "Preserve the mature heteroaryl core and test late N-aryl disconnection first.",
    "route_mode": "late_fgi",
    "mode_evidence": ["mature heteroaryl core is available and should be preserved"],
    "strategic_risks": ["late substitution may fail if the heteroaryl core is too deactivated"],
    "revision_triggers": ["advanced terminal still hides core construction"],
    "key_disconnections": ["late N-aryl C-N disconnection"],
    "preferred_precursor_logic": ["heteroaryl fluoride plus chiral amine fragment"],
    "protect_or_preserve": ["preserve fused heteroaryl core"],
    "terminal_rescue_policy": "Before accepting advanced terminal, attempt a short mechanistic rollback.",
    "revision_reason": "evidence-enriched refinement after site analysis"
})
```

若先看 site evidence 且此前没有 seed，直接使用同样完整的字段，但将
`revision_reason` 写为 `initial`；这会登记 complete revision 0，而不是人为制造
revision 1。

返回核心字段：

```json
{
  "ok": true,
  "route_plan": {
    "id": "plan:abc123",
    "revision": 1,
    "route_thesis": "Preserve the mature heteroaryl core...",
    "route_mode": "late_fgi",
    "mode_evidence": ["mature heteroaryl core is available and should be preserved"],
    "strategic_risks": ["late substitution may fail if the heteroaryl core is too deactivated"],
    "revision_triggers": ["advanced terminal still hides core construction"],
    "key_disconnections": ["late N-aryl C-N disconnection"],
    "preferred_precursor_logic": ["heteroaryl fluoride plus chiral amine fragment"],
    "protect_or_preserve": ["preserve fused heteroaryl core"],
    "terminal_rescue_policy": "Before accepting advanced terminal...",
    "last_revision_reason": "evidence-enriched refinement after site analysis"
  },
  "route_plan_history_count": 2,
  "prompt_brief": {
    "stage": "route_plan",
    "events": ["stage.route_plan", "strategy.route_plan_active", "strategy.route_mode_triage"],
    "route_plan_brief": {
      "id": "plan:abc123",
      "revision": 1,
      "route_mode": "late_fgi"
    }
  },
  "next_step": "reaction_sites()"
}
```

持久化位置：

- `session["route_plan"]["current"]`：完整当前 plan。
- `session["route_plan"]["history"]`：完整修订历史，仅用于 audit/debug/report。
- `prompt_brief.route_plan_brief`：默认 LLM 上下文中的短投影。
- commit audit 可包含 `route_plan_id`、`route_plan_revision`、
  `route_plan_alignment`、`route_plan_note`。

字段说明：

- `route_mode`：短路线范式标签，例如 `late_fgi`、`scaffold_assembly`、
  `electronic_state_strategy` 或 `hybrid`。
- `mode_evidence`：为什么当前范式可信的短证据列表。
- `strategic_risks`：可能推翻当前全局 thesis 的路线风险。
- `revision_triggers`：后续看到这些证据时应主动修订 `route_plan`。

这些字段会被压缩进入 `prompt_brief.route_plan_brief`。在 `route_plan`
命令中实际提供 `route_mode` 时产生 `strategy.route_mode_triage`；首次 plan
前若当前分子事实明确需要路线范式比较，也可产生该事件。
`revision_triggers` 是未来修订条件，不代表当前已触发。实际修订 plan 后只产生
`strategy.route_plan_revised`。

### route_sketch

记录 LLM 在路线 thesis 变化、多事件想法、局部 strategy-to-action 转换或
advanced-terminal review 下的短路线策略草图。一个完整的一步 peer action 可以直接
`propose_action -> try_action`；`route_sketch` 不是 LLM 自提化学的许可门槛。它只影响
后续 `prompt_brief`、audit 和可选 strategy continuation，不直接写入 route tree。

```python
cmd.execute("route_sketch", {
    "problem": "Listed actions are weak for the desired convergent route.",
    "macro_strategy": "Build the core first and install the side chain late.",
    "key_disconnections": ["late ether formation", "avoid fused-core cleavage"],
    "rejected_action_space_reason": "Current actions shift the site or require unrealistic handles.",
    "next_executable_step": "propose_action",
    "terminal_review": false
})
```

返回核心字段：

```json
{
  "ok": true,
  "route_sketch_id": "sketch:mol_0:0",
  "route_strategy_brief": {
    "id": "sketch:mol_0:0",
    "macro_strategy": "Build the core first and install the side chain late.",
    "next_executable_step": "propose_action"
  },
  "prompt_brief": {
    "stage": "route_sketch",
    "events": ["stage.route_sketch", "strategy.route_sketch_active"]
  },
  "next_step": "propose_action(...)"
}
```

完整 sketch 只保存在 session/audit provenance 中。当前分子处理期间，
`context_compact` 和 `reaction_sites` 继续携带短 `route_strategy_brief`；其中仅保留
id、macro strategy、next step、terminal flag 和最多两条压缩 continuation step。
若下一步不在系统 action 中，继续
`propose_action(..., route_sketch_id=...) -> try_action(custom_id)`。

若短策略需要多个真实化学事件，可在 sketch 中记录压缩的 `continuation_steps`
计划。该计划不是反应节点；只用于在第一步 custom action 成功 commit 后创建
pending strategy continuation。每次仍只能提交一个真实化学事件。

`terminal_review=True` 会触发
`strategy.advanced_terminal_rescue_requested`，用于 advanced terminal 前的
LLM 自提策略转行动草图。terminal-review sketch 之后，普通 `accept` 会被
hard gate 阻断，直到至少有一个 route-sketch-derived custom sandbox attempt，
或显式提供 no-actionable rescue override。
Terminal-review sketch 的 `next_executable_step` 仍必须是允许的执行入口，
通常是 `propose_action`；不要把 `accept` 写成 route sketch 的下一步。

### propose_action

登记完整的 LLM 设计一步前体动作。系统 action 与该动作是 peer hypotheses；当
LLM action 更 route-coherent 时，先在 `rationale_summary` 建立 positive chemical
case，再把比较作为次要选择 provenance。只有真正拒绝某个已列 action 时才填写
`why_existing_actions_rejected`。登记后仍必须用 `try_action(custom_id)` 验证。

```python
cmd.execute("propose_action", {
    "precursors": ["CC(=O)Cl", "Nc1ccc(O)cc1"],
    "reagents": ["CCN(CC)CC"],
    "reaction_name": "Schotten-Baumann acylation",
    "action_label": "peer acetylation precursor set",
    "why_existing_actions_rejected": "",
    "rationale_summary": "Acetyl chloride supplies the acetyl carbonyl, p-aminophenol supplies the amide nitrogen and aryl-phenol skeleton, and base captures HCl; this is one chemoselective amide-forming event at the aniline nitrogen.",
    "risk_tags": ["custom_precursor", "atom_accounting", "chemoselectivity"]
})
```

如果确实拒绝了某个系统 action，再把该字段写成具体事实，例如：

```python
"why_existing_actions_rejected": "site:bond:4 shifts the acylation to the phenolic oxygen instead of the intended aniline nitrogen"
```

不要为了获得自提权限而虚构系统方案失败；完整 positive chemical case 才是当前
候选值得验证的主要依据。

返回 `action_id` 后继续：

```python
cmd.execute("try_action", {"action_id": "custom:custom_acetylation_precursor_set:0"})
```

当该 action 是 multi-step strategy continuation 的第一真实事件时，可附带
`route_sketch_id`、当前 `continuation_step_idx` 和 `continuation_precursor`。它们只用于
编排后续 focus，不改变当前反应的验证语义。

`precursors` 是保留计量重复的列表，不是集合。若两个相同试剂分子分别供应两个
产物位点，应重复写两次相同 SMILES，不能只在 reasoning 中写“2 equivalents”。
`precursors` 表示需要进入树的骨架或 synthon；`reagents` 表示当前步参与原子守恒、
电子态审计和报告导出、但不进入 reaction tree/terminal list 的催化剂、金属、供体或
小组分。两类列表都保留计量重复；scaffold/topology/site/FG 审计只使用
`precursors`。
有机金属 `precursor_normalization` 中的 `current_reagent` 仍属于当前反应；
`upstream_source_precursors` 仅表示可选的独立上游来源提示，不得替换当前反应物，
也不是唯一来源机制。preflight 同时支持 `[C]-[Zn]-[Cl]` 与
`[Cl]-[Zn]-[C]` 编码，并避免把 ZnCl2 等普通金属卤化物误判为有机金属。
commit 后建立续作焦点，不改变 sandbox/commit 必须验证一个真实事件的规则。

若该 action 涉及成环、并环、骨架编辑或原子来源争议，还应补充：

```python
cmd.execute("propose_action", {
    "precursors": ["..."],
    "reaction_name": "custom annulation or rearrangement",
    "action_label": "custom topology step",
    "why_existing_actions_rejected": "System actions do not explain the intended topology change.",
    "rationale_summary": "One real event with explicit atom-source evidence.",
    "intended_deltas": ["ring_closure", "fg_installation"],
    "expected_ring_change": "fused_ring",
    "changed_bonds": [{"product_atoms": [0, 1], "precursor_atoms": [0, 1], "event": "formed"}],
    "preserved_anchors": ["retained heteroatom position", "stable side-chain handle"],
    "mechanistic_evidence": ["short mechanistic reason this is a single event"],
    "family_evidence": {
        "same_precursor_tether": "if intramolecular",
        "new_ring_bond_atom_source": "source of the new bond atoms"
    }
})
```

### Hidden legacy / diagnostic commands

以下命令仍可由旧脚本或专家诊断调用，但不在默认 help / LLM prompt 中作为主路径出现：

```text
explore
explore_reaction
explore_fgi
try_bond
try_fgi
try_precursors
```

普通路线规划应使用 `reaction_sites -> explore_site -> try_action`。

### smart_cap

智能断键推理 — 基于键两端化学环境自动推断 capping 方案。

```python
# 按 bond_idx 查询（需要当前 context）
cmd.execute("smart_cap", {"bond_idx": 0})

# 直接指定 SMILES + 原子对
cmd.execute("smart_cap", {"smiles": "CC(=O)Nc1ccccc1", "bond": [1, 3]})

# 限制返回数量
cmd.execute("smart_cap", {"bond_idx": 0, "max": 3})
```

返回:

```json
{
  "ok": true,
  "proposals": [
    {
      "reaction_type": "Amide bond formation",
      "fragments": ["CC(=O)O", "Nc1ccccc1"],
      "confidence": 0.90,
      "description": "RC(=O)-NR₂ → RC(=O)OH + HNR₂"
    }
  ]
}
```

### custom_cap

LLM 自定义 capping — 指定断键两端各加什么基团。

```python
cmd.execute("custom_cap", {
    "bond_idx": 0,
    "cap_i": "Br",
    "cap_j": "B(O)O"
})
```

### sandbox_list

查看沙盒中所有方案的紧凑比较视图。

```python
cmd.execute("sandbox_list")
```

返回设计：

- `attempts` 是 LLM 默认阅读的比较表。
- `by_site` / `by_reaction` 只保存 attempt 索引，不重复整行。
- 每个 attempt 只公开 canonical `validation` (`rachel.validation.v2`)。
- `validation.decision_gate` 是唯一公开 gate 状态；`contradictions`、`proof_obligations`、`evidence_gaps`、`tool_limits`、`warnings` 和 `system_errors` 分开传递。
- topology/site 信息位于 `validation.observations`；MCS 映射明确标为 `method=mcs_heuristic`。`site_rows` 不再是公开协议字段。
- 完整 sandbox attempt 仍保存在 session JSON 中，供 commit、report/export 和 diagnostic 使用。
- 历史 session 中的 `forward_validation`、`validation_micro`、`evidence_packet`、`override_allowed` 仍可读取，但不会作为新公共命令输出。

### sandbox_clear

清空沙盒中所有方案。

```python
cmd.execute("sandbox_clear")
```

### select + commit

选中方案并提交到树。

```python
cmd.execute("select", {"idx": 1})
cmd.execute("commit", {
    "idx": 1,                          # 沙盒方案索引
    "expected_action_id": "site:bond:2:alt:1", # 防止 idx 与 reasoning 指向不同 action
    "reasoning": "酰氯法条件温和...",    # 决策理由
    "confidence": "high",               # high / medium / low
    "rejected": [                       # 被拒绝的方案
        {"method": "Ac2O route", "reason": "副产物处理"}
    ]
})
```

commit 返回:

```json
{
  "step_id": "rxn_1",
  "reaction_smiles": "CC(=O)Cl.Nc1ccc(O)cc1>>CC(=O)Nc1ccc(O)cc1",
  "new_pending": [],
  "new_terminal": ["CC(=O)Cl", "Nc1ccc(O)cc1"],
  "tree_complete": true,
  "validation": {
    "schema_version": "rachel.validation.v2",
    "execution": {"status": "completed", "scope": "commit"},
    "decision_gate": {"state": "clear"},
    "contradictions": [],
    "proof_obligations": []
  }
}
```

commit 前置门控：

- `validation.decision_gate.state == "blocked"` 时不能提交。
- 正常 LLM 流程应同时提交 `idx` 和该行显示的 `expected_action_id`；两者不一致时在写树前报错，防止沙盒重排或旧 idx 导致 reasoning/前体错配。
- `state == "proof_required"` 时必须补证据、修改前体，或提供有化学依据的 `validation_override`。
- `state == "inconclusive"` 时分别读取 `evidence_gaps` 与 `tool_limits`，不能把模板缺失当作化学否定或正证据。
- 严格 same-core site audit 不完整或出现多位点变化时进入 `proof_required`，不再因缺少 `site_rows` 自动硬拒绝；独立位置证据可通过同一 `validation_override` 说明。
- commit 成功后，reaction node 和公共 commit 返回复用所选 sandbox attempt 的
  validation；不会用缺失 action context 的二次 validator 覆盖已审查 gate。

### accept / skip

```python
cmd.execute("accept", {"reason": "简单商业试剂"})  # 标记为 terminal
cmd.execute("skip", {"reason": "无可行方案"})       # 跳过
```

### tree / status / finalize / report / export

```python
cmd.execute("tree")      # → {tree (文本), terminal_count, pending_count, terminals}
cmd.execute("status")    # → {target, status, steps_executed, pending_count, pending_continuation_count, ...}
cmd.execute("continuation_status")  # → active strategy continuation summary
cmd.execute("continuation_abort", {"continuation_id": "...", "reason": "chemical reason"})
cmd.execute("finalize", {"summary": "..."})  # 完成编排
cmd.execute("report")    # → {report (文本), starting_materials}
cmd.execute("export", {"name": "Losartan", "output_dir": "..."})  # 导出结果
```

`finalize` 在存在 pending strategy continuation 时不会 drain queue，而是返回：

```json
{
  "error": "strategy_continuation_pending",
  "active_strategy_continuations": [
    { "id": "continuation:...", "focus_smiles": "...", "next_step": {...} }
  ]
}
```

此时应继续 `next` 处理续作，或用 `continuation_abort` 带理由关闭。
若 focus 原本是 auto-terminal，abort 后会恢复 terminal；若要换用新的深拆策略，
先用 `review_terminal(smiles, reason, additional_steps=0)` 将原树节点重新排队；若总步数预算已耗尽，同时提供正数 `additional_steps`。

export 返回:

```json
{
  "output_dir": "output/20260220_235417_Losartan",
  "files": ["SYNTHESIS_REPORT.html", "SYNTHESIS_REPORT.md", "report.txt", ...],
  "n_files": 8,
  "n_images": 12,
  "html_report": "output/.../SYNTHESIS_REPORT.html",
  "visualization_ok": true,
  "summary": "Losartan: 5 步, 6 种起始原料, 可视化=✓"
}
```

Typical export order:

1. `finalize`
2. `report`
3. `export`

---

## 2. 数据结构

### MoleculeNode

```python
@dataclass
class MoleculeNode:
    smiles: str              # canonical SMILES
    node_id: str             # "mol_0", "mol_1", ...
    role: str                # "target" / "intermediate" / "terminal" / "pending"
    depth: int               # 树中深度
    complexity: Dict         # {cs_score, classification, is_terminal}
    decision_context: Dict   # build_decision_context() 的完整输出
    llm_analysis: Dict       # LLM 的分析记录
```

### ReactionNode

```python
@dataclass
class ReactionNode:
    step_id: str             # "rxn_1", "rxn_2", ...
    depth: int
    reaction_smiles: str     # "A.B>>C"
    product_node: str        # mol_id
    reactant_nodes: List[str]  # [mol_id, ...]
    reaction_type: str
    template_evidence: TemplateEvidence
    llm_decision: LLMDecision
    forward_validation: Dict
```

### TemplateEvidence

```python
@dataclass
class TemplateEvidence:
    template_id: str = ""
    template_name: str = ""
    category: str = ""
    confidence: float = 0.0
    source: str = ""         # "template" / "llm_proposed" / "fgi"
```

### LLMDecision

```python
@dataclass
class LLMDecision:
    selection_reasoning: str       # 选择理由
    confidence: str                # "high" / "medium" / "low"
    rejected_alternatives: List[Dict]  # [{method, reason}]
    protection_needed: bool
    risk_assessment: str
```

### SynthesisAuditState

```python
@dataclass
class SynthesisAuditState:
    strategic_plan: Dict           # LLM 的全局战略
    protections: List[ProtectionEntry]  # 保护基生命周期
    decision_history: List[DecisionRecord]  # 每步决策记录
    failed_attempts: List[FailedAttempt]    # 失败记录
    linear_step_count: int
    max_linear_target: int         # 根据 CS score 动态设置
    target_cs_score: float
```

### DecisionRecord

```python
@dataclass
class DecisionRecord:
    step_id: str
    molecule: str
    action: str            # decide / propose / accept-terminal / skip
    reaction_name: str
    reasoning_summary: str
    outcome: str           # committed / gate_failed / skipped / terminal
    confidence: str        # high / medium / low
```

### ProtectionEntry

```python
@dataclass
class ProtectionEntry:
    functional_group: str  # phenol, ketone, aldehyde ...
    position: str          # C3-OH, ring A ketone ...
    protection: str        # TBS ether, acetal, 延迟引入 ...
    install_step: str      # rxn_2 或 planned
    remove_step: str       # rxn_5 或 pending
    status: str            # planned / installed / removed
```

---

## 3. 化学工具层 (chem_tools)

化学工具层由编排器内部调用，LLM 通常不需要直接使用。下表只列主干模块和代表函数，不作为完整 API 清单。

| 模块 | 函数 | 作用 |
|------|------|------|
| M0 _rdkit_utils | `parse_mol`, `canonical`, `validate_smiles`, `smarts_match`, `tanimoto`, `mol_formula_counter`, `load_template` | RDKit 公共工具（内部） |
| M1 mol_info | `analyze_molecule`, `match_known_scaffolds` | 分子基础信息 |
| M2 fg_detect | `detect_functional_groups`, `detect_reactive_sites`, `detect_protecting_groups`, `get_fg_reaction_mapping` | 官能团识别 |
| M3 template_scan | `scan_applicable_reactions`, `find_disconnectable_bonds` | 模板扫描 |
| M4 bond_break | `execute_disconnection`, `execute_fgi`, `execute_operations`, `preview_disconnections`, `try_retro_template`, `resolve_template_ids` | 断键执行（6 个） |
| M5 forward_validate | `validate_forward`, `check_atom_balance` | 正向验证 |
| M6 cs_score | `compute_cs_score`, `classify_complexity`, `score_progress`, `batch_score_progress` | 复杂度评分 |
| M7 fg_warnings | `check_fg_conflicts`, `check_reaction_compatibility`, `suggest_protection_needs`, `check_deprotection_safety` | 官能团冲突 |
| M8 smart_cap | `suggest_capping`, `custom_cap` | 智能断键推理 |

模板与局部环境维护约束：

- 反应 SMARTS 中的普通闭壳层 C-H 回退不能用裸 `[CH]` 作为通用占位符；在 RDKit 产物侧它可能表示开壳层碳。应保留映射碳让价态自动补氢，或用与实际氢数一致的受限 SMARTS，并用自由基电子数测试正反向产物。
- 普通酯的 `C(=O)-O` 模板和 smart-capping 规则必须排除 carbamate `N-C(=O)-O`。局部角色分别使用 `ester_o/carbonyl_c` 与 `carbamate_o/carbamate_carbonyl_c`，避免把 Boc/Cbz/Fmoc 的 O-C(=O) 键暴露为 Fischer、Steglich、Yamaguchi 或 ester-hydrolysis 候选。
- 羧酸或羧酸盐的终端酰基氧使用 `carboxylic_acid_o`，不得标为 `ester_o` 或生成“酸 + 水”的 ester-hydrolysis capping 候选。
- 反应条件族解析必须优先使用具体术语。`amide_coupling` / `peptide_coupling` 属于酰基取代条件，不得因包含泛化词 `coupling` 而继承 `pd_catalysis`；裸 `coupling` 仅在无更具体命中时作为兜底。
- 若图与 FG 审计表明唯一变化是保护基安装、底物图被完整保留，而模板前体遗漏保护基供体，则 atom-balance 的骨架增长降为 `protecting_group_source_required` 证明义务。LLM 必须补入真实闭壳层供体并重新验证；非保护基来源的 C/N/S 骨架增长仍是 hard block。

### CS Score 分级

| 范围 | 分类 | 含义 |
|------|------|------|
| ≤ 2.25 | trivial | 简单试剂，可作为合成终点（is_terminal=true） |
| 2.25 - 6.0 | moderate | 中等复杂度，需要继续拆解 |
| > 6.0 | complex | 复杂分子，需要精心设计路线 |

### Smart Capping (M8)

`suggest_capping(smiles, bond)` 根据键两端原子的化学环境自动推断断键后的 capping 方案。

这些方案只表达可能的断键方向、端基和片段结构，不证明正向反应、试剂完整性或选择性。`confidence` 是局部规则匹配强度，不是反应可行性概率。
公共 action 使用固定反应名 `LLM-completed structural disconnection`；原规则标签仅放在
`execution.heuristic_reaction_hint`，避免把 Heck/Miyaura 等启发式词条包装成反应结论。

覆盖 13 类反应规则：

| 规则 | 键类型 | Cap (i端 / j端) | 置信度 |
|------|--------|-----------------|--------|
| Suzuki coupling | Ar-Ar | Br / B(OH)₂ | 0.92 |
| Negishi coupling | Ar-Ar | Br / ZnCl | 0.70 |
| Stille coupling | Ar-Ar | Br / SnMe₃ | 0.60 |
| Amide bond formation | C(=O)-N | OH / H | 0.90 |
| Amide (acid chloride) | C(=O)-N | Cl / H | 0.80 |
| Ester hydrolysis | C(=O)-O | OH / H | 0.88 |
| N-alkylation (SN2) | N-C(sp3) | H / Br | 0.82 |
| Reductive amination | N-C(sp3) | H / =O | 0.70 |
| Williamson ether | O-C(sp3) | H / Br | 0.78 |
| Buchwald-Hartwig | Ar-N | Br / H | 0.80 |
| SNAr/Ullmann | Ar-O | F / H | 0.65 |
| Heck | C(sp2)-C(sp3) | H / Br | 0.55 |
| Grignard | C-C (通用) | Br / MgBr | 0.45 |

集成位置：
- `build_decision_context` 中每个 bond 自动附带 `smart_capping` 字段
- `explore_site(site_id)` 会把 smart capping 规范化为 `smart:*` 动作
- `context(detail="diagnostic")` 可查看 legacy bond/Fgi 细节
- `smart_cap` 命令可独立调用，用于专家辅助 ideation
- `custom_cap` 命令可让 LLM 自定义 capping 基团
- 有价值的 capping 输出应通过 `propose_action(...)` 登记，再走 `try_action(custom_id)`

理论最大值约 8.75。800 样本 USPTO50K 验证：trivial 5.0%, moderate 91.6%, complex 3.4%；中位数 4.21。

基准分子参考：atorvastatin ≈ 4.6, cholesterol ≈ 6.2, morphine ≈ 6.8, taxol ≈ 8.2。

权重：size=0.55, ring=0.65, stereo=0.55, hetero=0.40, symmetry=-0.20, fg_density=0.35。size 维度基于重原子数（非 MW），fg_density 同时计数保护基和复杂度官能团（酰胺/磺酰胺/氨基甲酸酯/脲/酯等）。

### 正向验证 (forward_validation)

`validate_forward` 仍计算加权可行性分数，但 v2 的 commit 判断优先阅读 `assessment.gate`。分数用于排序和风险感知，gate 用于告诉 LLM：这是硬错误、可管理风险、证据不足，还是允许提交。

底层验证维度：

| 步骤 | 权重 | Hard Gate |
|------|------|-----------|
| 原子守恒 (check_atom_balance) | 0.25 | severe_imbalance / skeleton_imbalance |
| 模板正向执行 | 0.25 | — |
| MCS 骨架对齐 | 0.20 | 不再单独无条件 hard block |
| 键变化拓扑 | 0.15 | has_hard_fail |
| 官能团兼容性 | 0.15 | forbidden FG |

旧内部 `feasibility_score` 是 validator support 的加权摘要，不是校准后的
化学成功概率，也不是公共 commit 判据。新公共 JSON 不输出该字段；历史
session 仍可保留它用于诊断。

#### validation gate

公共 `validation.decision_gate` 将验证证据分为 commit-facing 类别：

| state | 含义 |
| --- | --- |
| `blocked` | 不能提交；通过 `block_type` 区分化学矛盾与 validator/system error。 |
| `proof_required` | 需要补 atom source、tether、anchor、位点或机制证据；不是自动化学否定。 |
| `inconclusive` | 证据不足；必须分别读取 `evidence_gaps` 和 `tool_limits`。 |
| `warning` | 可提交，但 reasoning 必须处理风险。 |
| `clear` | 未发现 gate 级异议，仍需正常化学审查。 |

典型 gate 字段：

```json
{
  "schema_version": "rachel.validation.v2",
  "execution": {"status": "completed", "scope": "sandbox_validation"},
  "decision_gate": {"state": "inconclusive"},
  "contradictions": [],
  "proof_obligations": [],
  "evidence_gaps": [],
  "tool_limits": [
    {"code": "forward_template_target_not_regenerated", "source": "template_execution"}
  ],
  "observations": {
    "template": {"status": "target_not_regenerated", "product_similarity": 0.68},
    "atom_mapping": {"method": "mcs_heuristic", "status": "map_available"}
  }
}
```

`mechanism_interpretation` 仅在注册机制确实解释部分 observed deltas 时出现。
`unregistered_family` 不投影到公共 v2；反应名未注册不是独立 warning。

当前保守原则：
- `severe_imbalance`、`skeleton_imbalance` 和真实守恒矛盾进入 `contradictions`。
- 旧 `scaffold_not_aligned` 在公共协议中规范化为 `major_scaffold_not_inherited`，表示事实挑战，不自动判错 scaffold assembly。
- 旧 `unsupported_new_*` / `fusion_bond_infeasible` 规范化为 `*_requires_evidence`，避免把启发式或映射不足写成化学否定。
- 检测到卡宾、自由基或自由基离子前体时，`precursor_state` 记录开壳层原子和自由基电子数，`proof_obligations` 返回 `open_shell_precursor_requires_evidence`。LLM 应修正意外模板占位符为闭壳层前体，或补充原位生成、寿命、原子来源、机制角色和选择性证据；开壳层事实本身不进入 `contradictions`。
- 单原子 Li/Mg/Zn/Cu 组分单独投影为 `observations.precursor_state.status = elemental_metal_reagent`；其 RDKit 自由基电子是元素金属编码事实，不触发 open-shell proof obligation。该观察通过现有 `evidence_packet` 保留到压缩后的公共 validation。
- 模板未执行或未生成目标进入 `tool_limits`，不与化学 `evidence_gaps` 混合。
- 内部 legacy gate (`hard_block/override_required/missing_evidence/pass`) 继续用于历史 session 和 commit 实现，但新 LLM 流程只消费 canonical v2 投影。

#### 原子守恒 — 两层小分子损失设计

`check_atom_balance` 采用两层（Tier）设计处理反应中的小分子损失：

- Tier 1（类别特定）：根据 `reaction_category` 查表，只允许该类反应已知的损失分子。覆盖 19 类反应（ester_hydrolysis, friedel_crafts, elimination, curtius 等）。
- Tier 2（通用回退）：无论是否有 category，都尝试 6 种非骨架小分子损失（H₂O, HCl, HBr, HI, HF, H₂）。约束：通用回退不会自动解释骨架原子（C/N/S）差异。

两层依次应用于 deficit（前体多出）和 excess（产物多出）两侧。

#### 单向不平衡检测

关键设计：`skeleton_imbalance` 和 `severe_imbalance` 均为单向检测，只在产物侧有多余原子时触发：

- `skeleton_imbalance`：产物比前体多出 C/N/S 原子（原子凭空出现）。前体侧多出 C/N/S 是正常的（Wittig 的 Ph₃P=O、Stille 的 Bu₃SnCl 等试剂离去基团）。
- `severe_imbalance`：产物侧非 H 原子多出 > 4。前体侧多出通过连续评分软惩罚。

#### 连续 balance_score

`balance_score` 取代了旧的二值 balanced/not 判定，计算公式：

```
balance_score = 1.0 - (unexplained_atoms / total_heavy_atoms)
```

其中 `unexplained_atoms` = 两层损失扣除后仍无法解释的原子总数。典型值：
- 完全守恒反应：1.0
- Wittig（Ph₃P=O 离去）：~0.77
- Suzuki（硼酸离去）：~0.81
- Stille（锡试剂离去）：~0.5
- 严重不平衡：→ 0.0（被 hard gate 拦截）

`balance_score` 直接作为原子守恒维度（权重 0.25）参与 `feasibility_score` 加权平均。若触发 severe_imbalance 或 skeleton_imbalance，该维度强制为 0.0。

#### check_atom_balance 返回字段

```json
{
  "balanced": true,
  "balance_score": 0.77,
  "precursor_atoms": {"C": 20, "H": 18, "O": 2, "P": 1},
  "product_atoms": {"C": 10, "H": 10, "O": 1},
  "excess": {},
  "deficit": {"C": 10, "H": 8, "O": 1, "P": 1},
  "adjusted_excess": {},
  "adjusted_deficit": {"C": 10, "O": 1, "P": 1},
  "severe_imbalance": false,
  "skeleton_imbalance": false,
  "note": "balanced after accounting for small-molecule loss"
}
```

#### hard_fail_reasons 可能的值

| 值 | 含义 |
|----|------|
| `severe_imbalance` | 产物侧非 H 原子多出 > 4 |
| `skeleton_imbalance` | 产物比前体多出骨架原子（C/N/S） |
| `scaffold_not_aligned` | MCS 骨架对齐不足；通常需要 override/site audit，不自动代表化学错误 |
| `bond_topology_violation` | 键变化拓扑不可行 |
| `reaction_specific_violation` | 反应类别专属规则不满足 |
| `forbidden_fg` | 含有反应禁忌官能团 |

---

## 4. JSON 会话文件结构

```json
{
  "session_id": "abc123",
  "target": { "smiles": "...", "name": "...", "cs_score": 1.3 },
  "config": { "max_depth": 15, "max_steps": 50, "terminal_cs_threshold": 2.25 },
  "status": { "status": "in_progress", "steps_executed": 1, "pending_count": 0 },
  "current": {
    "smiles": "...",
    "node_id": "mol_0",
    "decision_context": { "...": "full fact payload" },
    "sandbox": {
      "attempts": [
        {
          "idx": 0,
          "action_id": "bond:10:alt:0",
          "source": "bond",
          "precursors": [...],
          "success": true,
          "forward_validation": { "assessment": { "gate": {...} } }
        }
      ],
      "selected": null,
      "n_attempts": 1,
      "summary": { "gate_states": { "pass": 1 } }
    },
    "custom_candidates": []
  },
  "archived_sandbox": [
    { "event": "commit", "attempts": [...], "selected_idx": 0 }
  ],
  "queue": [ ["SMILES", depth], ... ],
  "rescue_continuations": [
    {
      "id": "rescue:...",
      "route_sketch_id": "sketch:...",
      "focus_smiles": "...",
      "status": "pending",
      "remaining_steps": [...]
    }
  ],
  "seen_smiles": ["..."],
  "tree": { "molecule_nodes": {...}, "reaction_nodes": [...] },
  "audit_state": {
    "prompt_state": { "stage": "commit", "events": ["stage.commit"] },
    "strategic_plan": {...},
    "protections": [...],
    "decision_history": [...],
    "failed_attempts": [...],
    "linear_step_count": 0,
    "max_linear_target": 8,
    "target_cs_score": 0.0
  }
}
```

其中 `rescue_continuations` 是 `session.json` 的内部历史兼容字段，用于恢复旧
session；公共命令、`prompt_brief` 和导出的 `tree.json` 使用
`continuation_*` / `strategy_continuation_*`。新的 LLM 调用不要使用
`rescue_steps`、`rescue_status` 或 `rescue_abort`。

---

## 5. 终止判定逻辑

三层判定（任一满足即为 terminal）:

1. 重原子 ≤ 6 — 极简分子，直接 terminal
2. CS score ≤ threshold — 低于配置阈值
3. 无可断键 + 无 FGI — 模板无法处理

目标分子（is_target=true）即使满足 terminal 条件也不会自动跳过，
会进入 standard 流程让 LLM 决策。

---

## 6. 输出文件结构

`export` 命令将结果导出到 `output/YYYYMMDD_HHMMSS_分子名/`:

```
output/20260220_235417_Losartan/
├── SYNTHESIS_REPORT.html   # 自包含 HTML 可视化报告（核心输出）
├── SYNTHESIS_REPORT.md     # Markdown 报告（带图像引用）
├── report.txt              # 正向合成报告（纯文本）
├── tree.json               # 完整合成树 JSON
├── tree.txt                # 合成树文本渲染
├── terminals.json          # 起始原料清单
├── visualization.json      # nodes/edges 图数据（供前端）
├── session.json            # 完整会话快照（可恢复）
└── images/                 # 分子/反应/合成树 PNG 图像
    ├── mol_0.png
    ├── rxn_1_reaction.png
    └── synthesis_tree.png
```

HTML 报告特点：所有分子结构图和反应图内嵌为 base64，无需外部依赖，单文件可分享。
