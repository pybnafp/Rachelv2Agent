"""
合成报告生成器
==============
从 RetrosynthesisTree 生成三种输出:
  1. generate_forward_report() — 正向合成报告（拓扑排序反转）
  2. get_terminal_list() — 起始原料清单
  3. to_visualization_data() — nodes/edges 图数据（供前端可视化）
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List

from Rachel.chem_tools.validation_contract import build_validation_contract

from .retro_tree import (
    RetrosynthesisTree,
    ReactionNode,
    MoleculeNode,
    MoleculeRole,
)


# ─────────────────────────────────────────────────────────────────────────
# 正向合成报告
# ─────────────────────────────────────────────────────────────────────────

def _format_rejected_alt(item: Any) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        method = (
            item.get("method")
            or item.get("action_id")
            or item.get("candidate_id")
            or item.get("strategy_id")
            or item.get("reaction_type")
            or item.get("name")
            or "alternative"
        )
        reason = item.get("reason") or item.get("rationale") or item.get("note") or ""
        return f"{method}: {reason}" if reason else str(method)
    return str(item)


def _code_list(items: Any) -> List[str]:
    if not items:
        return []
    if isinstance(items, str):
        return [items]
    codes: List[str] = []
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                code = item.get("code") or item.get("reason") or item.get("name") or ""
                if code:
                    codes.append(str(code))
            elif item:
                codes.append(str(item))
    return codes


def _gate_summary(gate: Dict[str, Any]) -> str:
    if not gate:
        return ""
    contract = build_validation_contract({"gate": gate})
    parts = []
    for field in (
        "contradictions",
        "proof_obligations",
        "evidence_gaps",
        "tool_limits",
        "warnings",
        "system_errors",
    ):
        codes = _code_list(contract.get(field, []))
        if codes:
            parts.append(f"{field}={', '.join(codes)}")
    return " (" + "; ".join(parts) + ")" if parts else ""


def _gate_state(item: Dict[str, Any]) -> str:
    gate = item.get("validation_gate") or {}
    legacy_state = (
        item.get("validation_gate_state")
        or gate.get("gate_state")
        or gate.get("state")
        or ""
    )
    if not legacy_state:
        return ""
    return build_validation_contract({"gate": {"gate_state": legacy_state}})[
        "decision_gate"
    ]["state"]


def _candidate_audit_line(item: Dict[str, Any], *, candidate_format: str = "{}") -> str:
    idx = item.get("attempt_idx")
    prefix = f"[{idx}] " if idx is not None else ""
    cid = item.get("action_id", "") or item.get("candidate_id", "") or item.get("source", "")
    cid_text = candidate_format.format(cid) if cid else ""
    ok = "executed" if item.get("success") else "execution_failed"
    gate_state = _gate_state(item)
    gate_text = "" if not gate_state else f", gate={gate_state}"
    line = f"{prefix}{cid_text} {ok}{gate_text}".rstrip()
    gate = item.get("validation_gate") or {}
    contract = build_validation_contract({"gate": gate})
    for field in (
        "contradictions",
        "proof_obligations",
        "evidence_gaps",
        "tool_limits",
        "warnings",
        "system_errors",
    ):
        codes = _code_list(contract.get(field, []))
        if codes:
            line += f", {field}={', '.join(codes)}"
    reaction_type = item.get("reaction_type") or ""
    if reaction_type:
        line += f", reaction={reaction_type}"
    return line


def _selected_attempt(audit: Dict[str, Any]) -> Dict[str, Any]:
    selected = audit.get("selected_attempt") or {}
    if selected:
        return selected
    selected_id = audit.get("selected_action_id", "") or audit.get("selected_candidate_id", "")
    for item in (audit.get("action_comparison", []) or audit.get("candidate_comparison", []) or []):
        if (item.get("action_id") or item.get("candidate_id")) == selected_id:
            return item
    return {}


def _append_decision_audit_core(
    lines: List[str],
    audit: Dict[str, Any],
    *,
    prefix: str = "    ",
    bullet: str = "- ",
    max_attempts: int = 6,
    candidate_format: str = "{}",
) -> None:
    selected_action = audit.get("selected_action_id", "") or audit.get("selected_candidate_id", "")
    if selected_action:
        lines.append(f"{prefix}{bullet}selected action: {selected_action}")

    decision_source = audit.get("decision_source", "")
    if decision_source:
        lines.append(f"{prefix}{bullet}decision source: {decision_source}")

    reagents = list(audit.get("reagents", []) or [])
    if reagents:
        lines.append(f"{prefix}{bullet}current-step reagents: {', '.join(reagents)}")

    route_plan = audit.get("route_plan_brief") or {}
    if route_plan:
        plan_id = route_plan.get("id", "") or audit.get("route_plan_id", "")
        revision = route_plan.get("revision", audit.get("route_plan_revision", ""))
        thesis = route_plan.get("route_thesis", "")
        label = f"{plan_id} r{revision}" if plan_id != "" and revision != "" else plan_id
        route_line = f"{label}: {thesis}" if label else thesis
        alignment = audit.get("route_plan_alignment", "")
        if alignment:
            route_line += f" [{alignment}]"
        lines.append(f"{prefix}{bullet}route plan: {route_line}")
        if audit.get("route_plan_note"):
            lines.append(f"{prefix}  {bullet}plan note: {audit['route_plan_note']}")

    guidance = audit.get("chemist_guidance_summary", []) or []
    if guidance:
        lines.append(f"{prefix}{bullet}chemist guidance:")
        for item in guidance[:2]:
            guidance_id = item.get("id", "")
            intent = item.get("intent", "")
            summary = item.get("summary", "")
            label = f"{guidance_id} ({intent})" if intent else guidance_id
            lines.append(f"{prefix}  {bullet}{label}: {summary}")

    route_strategy = audit.get("route_strategy_brief") or {}
    if route_strategy:
        sketch_id = route_strategy.get("id", "") or audit.get("route_sketch_id", "")
        macro = route_strategy.get("macro_strategy", "")
        next_step = route_strategy.get("next_executable_step", "")
        route_line = f"{sketch_id}: {macro}" if sketch_id else macro
        if next_step:
            route_line += f" -> {next_step}"
        lines.append(f"{prefix}{bullet}route sketch: {route_line}")

    gate = audit.get("validation_gate") or {}
    if gate:
        gate_state = _gate_state({"validation_gate": gate})
        lines.append(f"{prefix}{bullet}validation gate: {gate_state}{_gate_summary(gate)}")

    card_ids = audit.get("applied_experience_card_ids", []) or []
    if card_ids:
        lines.append(f"{prefix}{bullet}applied experience cards: {', '.join(card_ids)}")

    prompt_events = ((audit.get("prompt_state") or {}).get("events", []) or [])
    if prompt_events:
        lines.append(f"{prefix}{bullet}prompt events: {', '.join(prompt_events[:8])}")

    selected = _selected_attempt(audit)
    why_rejected = (
        selected.get("why_existing_actions_rejected", "")
        or selected.get("why_existing_candidates_rejected", "")
    )
    rationale = selected.get("rationale_summary", "")
    if why_rejected or rationale:
        lines.append(f"{prefix}{bullet}custom provenance:")
        if why_rejected:
            lines.append(f"{prefix}  {bullet}why existing actions rejected: {why_rejected}")
        if rationale:
            lines.append(f"{prefix}  {bullet}rationale: {rationale}")

    comparison = audit.get("action_comparison", []) or audit.get("candidate_comparison", []) or []
    if comparison:
        lines.append(f"{prefix}{bullet}sandbox evidence:")
        for item in comparison[:max_attempts]:
            lines.append(
                f"{prefix}  {bullet}{_candidate_audit_line(item, candidate_format=candidate_format)}"
            )
        if len(comparison) > max_attempts:
            lines.append(f"{prefix}  {bullet}+{len(comparison) - max_attempts} more attempts in session/tree JSON")

    rejected = audit.get("rejected_actions", []) or audit.get("rejected_candidates", []) or []
    if rejected:
        lines.append(f"{prefix}{bullet}rejected alternatives:")
        if isinstance(rejected, str):
            lines.append(f"{prefix}  {bullet}{rejected.strip()}")
        else:
            for item in rejected:
                lines.append(f"{prefix}  {bullet}{_format_rejected_alt(item)}")


def format_decision_audit_markdown(decision: Any) -> List[str]:
    audit = getattr(decision, "decision_audit", {}) or {}
    if not audit:
        return []
    lines = ["- **Decision Audit**:"]
    _append_decision_audit_core(lines, audit, prefix="  ", bullet="- ", candidate_format="`{}`")
    return lines


def _append_decision_audit(lines: List[str], audit: Dict[str, Any]) -> None:
    if not audit:
        return
    lines.append("  Decision Audit:")
    _append_decision_audit_core(lines, audit, prefix="    ", bullet="")


def generate_forward_report(tree: RetrosynthesisTree) -> str:
    """将逆合成树反转为正向合成报告文本。

    拓扑排序: 叶节点反应在前，target 反应在后。
    """
    if not tree.reaction_nodes:
        target_label = tree.target_name or tree.target
        return f"正向合成报告: {target_label}\n\n（无反应步骤）"

    sorted_rxns = _topological_sort(tree)
    terminals = _collect_terminals(tree)

    lines: List[str] = []

    # 标题
    target_label = tree.target_name or tree.target
    lines.append(f"正向合成报告: {target_label}")
    lines.append("=" * 50)
    lines.append("")

    # 起始原料
    lines.append(f"起始原料 ({len(terminals)} 种):")
    for t in terminals:
        cs_info = ""
        if t.complexity:
            cs_info = f"  [CS={t.cs_score:.1f}, {t.complexity.get('classification', '')}]"
        lines.append(f"  • {t.smiles}{cs_info}")
    lines.append("")

    # 合成步骤
    lines.append(f"合成步骤 ({len(sorted_rxns)} 步):")
    lines.append("-" * 40)

    for i, rxn in enumerate(sorted_rxns, 1):
        lines.append("")
        lines.append(f"Step {i}: {rxn.reaction_smiles}")

        reactant_smiles = _get_reactant_smiles(tree, rxn)
        product_smiles = _get_product_smiles(tree, rxn)
        lines.append(f"  前体: {' + '.join(reactant_smiles)}")
        if rxn.reagents:
            lines.append(f"  当前步试剂: {' + '.join(rxn.reagents)}")
        lines.append(f"  产物: {product_smiles}")

        if rxn.reaction_type:
            lines.append(f"  反应类型: {rxn.reaction_type}")

        if rxn.template_evidence and rxn.template_evidence.template_name:
            lines.append(f"  模板: {rxn.template_evidence.template_name}")

        if rxn.llm_decision and rxn.llm_decision.selection_reasoning:
            lines.append(f"  理由: {rxn.llm_decision.selection_reasoning}")
        rejected = (rxn.llm_decision.rejected_alternatives or []) if rxn.llm_decision else []
        if rejected:
            if isinstance(rejected, str):
                lines.append(f"  rejected: {rejected}")
            else:
                for item in rejected:
                    lines.append(f"  rejected: {_format_rejected_alt(item)}")
        if rxn.llm_decision:
            _append_decision_audit(lines, rxn.llm_decision.decision_audit or {})

        if rxn.forward_validation:
            fv = rxn.forward_validation
            score = fv.get("assessment", {}).get("feasibility_score")
            passed = fv.get("assessment", {}).get("pass")
            if score is not None:
                icon = "✓" if passed else "✗"
                lines.append(f"  验证: {icon} feasibility={score:.3f}")

    # 总结
    lines.append("")
    lines.append("-" * 40)
    lines.append(f"总计: {len(sorted_rxns)} 步, {len(terminals)} 种起始原料")
    if tree.llm_summary:
        lines.append(f"\nLLM 总结: {tree.llm_summary}")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────
# 起始原料清单
# ─────────────────────────────────────────────────────────────────────────

def _node_id_sort_key(node_id: str) -> tuple[int, str]:
    if not isinstance(node_id, str):
        return (10**9, str(node_id))
    if "_" not in node_id:
        return (10**9, node_id)
    try:
        return (int(node_id.split("_")[-1]), node_id)
    except ValueError:
        return (10**9, node_id)

def get_terminal_list(tree: RetrosynthesisTree) -> List[Dict[str, Any]]:
    """收集所有 terminal 叶节点（起始原料），返回结构化清单。"""
    result: List[Dict[str, Any]] = []
    for node in tree.get_starting_material_nodes():
        entry: Dict[str, Any] = {
            "smiles": node.smiles,
            "node_id": node.node_id,
        }
        if node.complexity:
            entry["cs_score"] = node.cs_score
            entry["classification"] = node.complexity.get("classification", "")
        result.append(entry)
    result.sort(key=lambda x: _node_id_sort_key(str(x.get("node_id", ""))))
    return result


# ─────────────────────────────────────────────────────────────────────────
# 可视化数据
# ─────────────────────────────────────────────────────────────────────────

def to_visualization_data(tree: RetrosynthesisTree) -> Dict[str, Any]:
    """输出 nodes/edges 图数据，供前端可视化。

    边方向遵循逆合成方向（产物 → 反应 → 前体），前端可自行反转。
    """
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []

    # 分子节点
    for nid, mol in tree.molecule_nodes.items():
        node_data: Dict[str, Any] = {
            "id": nid,
            "type": "molecule",
            "smiles": mol.smiles,
            "role": mol.role,
            "depth": mol.depth,
        }
        if mol.complexity:
            node_data["cs_score"] = mol.cs_score
            node_data["classification"] = mol.complexity.get("classification", "")
        nodes.append(node_data)

    # 反应节点 + 边
    for rxn in tree.reaction_nodes:
        label = rxn.reaction_type
        if rxn.template_evidence and rxn.template_evidence.template_name:
            label = rxn.template_evidence.template_name

        rxn_data: Dict[str, Any] = {
            "id": rxn.step_id,
            "type": "reaction",
            "label": label,
            "depth": rxn.depth,
            "reaction_smiles": rxn.reaction_smiles,
        }
        nodes.append(rxn_data)

        # 产物 → 反应节点
        edges.append({
            "source": rxn.product_node,
            "target": rxn.step_id,
            "type": "retro_product",
        })

        # 反应节点 → 前体
        for rid in rxn.reactant_nodes:
            edges.append({
                "source": rxn.step_id,
                "target": rid,
                "type": "retro_reactant",
            })

    meta = {
        "target": tree.target,
        "target_name": tree.target_name,
        "status": tree.status,
        "total_steps": tree.total_steps,
        "total_molecules": len(tree.molecule_nodes),
    }

    return {"nodes": nodes, "edges": edges, "meta": meta}


# ─────────────────────────────────────────────────────────────────────────
# 内部辅助
# ─────────────────────────────────────────────────────────────────────────

def _topological_sort(tree: RetrosynthesisTree) -> List[ReactionNode]:
    """拓扑排序: 叶节点反应在前，target 反应在后（正向合成顺序）。"""
    product_to_rxn: Dict[str, ReactionNode] = {}
    for rxn in tree.reaction_nodes:
        product_to_rxn[rxn.product_node] = rxn

    # 依赖图: rxn_A 依赖 rxn_B = rxn_A 的某个前体是 rxn_B 的产物
    in_degree: Dict[str, int] = {rxn.step_id: 0 for rxn in tree.reaction_nodes}
    forward: Dict[str, List[str]] = defaultdict(list)

    for rxn in tree.reaction_nodes:
        for rid in rxn.reactant_nodes:
            if rid in product_to_rxn:
                dep_rxn = product_to_rxn[rid]
                in_degree[rxn.step_id] += 1
                forward[dep_rxn.step_id].append(rxn.step_id)

    # Kahn's algorithm
    queue = sorted([sid for sid, deg in in_degree.items() if deg == 0])
    result: List[ReactionNode] = []
    rxn_by_id = {rxn.step_id: rxn for rxn in tree.reaction_nodes}

    while queue:
        current = queue.pop(0)
        result.append(rxn_by_id[current])
        for neighbor in sorted(forward[current]):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    return result


def _collect_terminals(tree: RetrosynthesisTree) -> List[MoleculeNode]:
    terminals = list(tree.get_starting_material_nodes())
    terminals.sort(key=lambda n: _node_id_sort_key(n.node_id))
    return terminals


def _get_reactant_smiles(tree: RetrosynthesisTree, rxn: ReactionNode) -> List[str]:
    result = []
    for rid in rxn.reactant_nodes:
        node = tree.molecule_nodes.get(rid)
        result.append(node.smiles if node else rid)
    return result


def _get_product_smiles(tree: RetrosynthesisTree, rxn: ReactionNode) -> str:
    node = tree.molecule_nodes.get(rxn.product_node)
    return node.smiles if node else rxn.product_node
