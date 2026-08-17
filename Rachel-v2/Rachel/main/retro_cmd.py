#!/usr/bin/env python
"""
retro_cmd.py — LLM 多步逆合成命令接口
======================================
标准化的 JSON-in / JSON-out 命令层。
LLM 通过 Python 调用此脚本的函数，所有 SMILES 和上下文
只在 JSON 文件中流转，不经过终端。

公共命令列表:
  init          创建新会话
  next          取下一个分子（自动跳过 quick_pass）
  context       获取当前上下文（compact/full/status/tree）
  guide         记录合成专家对当前节点的自然语言指导
  route_plan    设置或修订长期全局合成路线 thesis
  route_sketch  记录弱 action-space 下的短路线策略草图
  reaction_sites 完整第一层 site/reaction 菜单
  explore_site  展开同一真实 site 下的所有 action
  try_action    沙盒验证 action-space 条目
  propose_action 登记 LLM 自提前体 action
  sandbox_list  查看沙盒历史
  sandbox_clear 清空沙盒
  select        选中沙盒方案
  commit        提交决策写入树
  accept        标记当前分子为 terminal
  skip          跳过当前分子
  tree          打印合成树
  status        查看编排状态
  finalize      完成编排
  report        生成正向合成报告
  export        导出完整路线产物
  smart_cap     专家 capping 辅助
  custom_cap    专家自定义 capping 辅助

隐藏 legacy 入口仍保留给旧脚本和诊断，但不会出现在默认 available/help 中；
普通 LLM 流程应使用 reaction_sites -> explore_site -> try_action。

用法:
  python -m Rachel.main.retro_cmd <command> [session_file] [args_json]

  或在 Python 中:
    from Rachel.main.retro_cmd import RetroCmd
    cmd = RetroCmd("session.json")
    result = cmd.execute("init", {"target": "CC(=O)Nc1ccc(O)cc1", "name": "Paracetamol"})
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# 确保项目根目录在 path 中
ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Rachel.main.retro_session import RetroSession
from Rachel.main.retro_report import generate_forward_report, get_terminal_list
from Rachel.main.retro_output import export_results
from Rachel.main.public_protocol import internal_continuation_id, project_public_payload
from Rachel.chem_tools.cs_score import CS_TRIVIAL
from Rachel.chem_tools.validation_contract import build_validation_contract


_LEGACY_VALIDATION_KEYS = {
    "success",
    "forward_validation",
    "validation_gate",
    "validation_micro",
    "evidence_packet",
    "site_audit",
}

_PUBLIC_GATE_REASON_MAP = {
    "validation_missing_gate": "validation_result_missing",
    "validation_hard_block": "validation_blocked",
    "validation_override_required": "validation_proof_required",
}


def _canonical_public_control_fields(result: Dict[str, Any]) -> None:
    gate_reason = str(result.get("gate_reason", "") or "")
    if gate_reason in _PUBLIC_GATE_REASON_MAP:
        result["gate_reason"] = _PUBLIC_GATE_REASON_MAP[gate_reason]

    error = str(result.get("error", "") or "")
    if error == "validation gate missing; commit blocked":
        result["error"] = "validation result missing; commit blocked"
    elif error == "validation gate hard-blocked commit":
        result["error"] = "validation decision gate blocked commit"
    elif error.startswith("validation gate requires explicit override:"):
        result["error"] = (
            "validation decision gate is proof_required: add evidence, revise "
            "the action, or provide validation_override={allowed: true, "
            "reason: ..., evidence: ...}"
        )


def _public_validation_result(
    raw: Dict[str, Any],
    *,
    execution_scope: str,
) -> Dict[str, Any]:
    """Project internal validation payloads into the public v2 contract."""
    result = {
        key: value
        for key, value in raw.items()
        if key not in _LEGACY_VALIDATION_KEYS
    }
    _canonical_public_control_fields(result)
    forward_validation = raw.get("forward_validation") or {}
    if not forward_validation and raw.get("validation_gate"):
        forward_validation = {"gate": raw.get("validation_gate")}
    has_validation = bool(
        forward_validation
        or raw.get("validation_micro")
        or raw.get("site_audit")
        or raw.get("validation_gate")
    )
    if has_validation:
        result["validation"] = build_validation_contract(
            forward_validation,
            validation_micro=raw.get("validation_micro") or {},
            site_audit=raw.get("site_audit") or {},
            execution_success=bool(raw.get("success", not raw.get("error"))),
            execution_scope=execution_scope,
        )
    else:
        result["execution"] = {
            "status": "failed" if raw.get("error") else "completed",
            "scope": execution_scope,
        }
    return result


PUBLIC_COMMANDS = [
    "init", "next", "context", "guide", "route_plan", "route_sketch", "reaction_sites", "explore_site",
    "try_action", "propose_action",
    "sandbox_list", "sandbox_clear", "select",
    "commit", "accept", "review_terminal", "skip",
    "tree", "status", "continuation_status", "continuation_abort", "finalize", "report", "export",
    "smart_cap", "custom_cap",
]

HIDDEN_LEGACY_COMMANDS = [
    "explore",
    "explore_reaction",
    "explore_fgi",
    "try_bond",
    "try_candidate",
    "propose_candidate",
    "try_fgi",
    "try_precursors",
    "rescue_status",
    "rescue_abort",
]


class RetroCmd:
    """LLM 逆合成命令接口。

    所有方法返回 dict，可直接 json.dumps。
    session_file 是唯一的状态载体。
    """

    def __init__(self, session_file: str = ".rachel_session.json"):
        self.session_file = session_file
        self._session: Optional[RetroSession] = None

    @property
    def session(self) -> RetroSession:
        if self._session is None:
            self._session = RetroSession.load(self.session_file)
        return self._session

    def execute(self, command: str, args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """统一入口。command → 对应方法。"""
        args = args or {}
        dispatch = {
            "init": self.cmd_init,
            "next": self.cmd_next,
            "context": self.cmd_context,
            "guide": self.cmd_guide,
            "route_plan": self.cmd_route_plan,
            "route_sketch": self.cmd_route_sketch,
            "reaction_sites": self.cmd_reaction_sites,
            "explore": self.cmd_explore,
            "explore_site": self.cmd_explore_site,
            "explore_reaction": self.cmd_explore_reaction,
            "explore_fgi": self.cmd_explore_fgi,
            "try_bond": self.cmd_try_bond,
            "try_action": self.cmd_try_action,
            "try_candidate": self.cmd_try_candidate,
            "propose_action": self.cmd_propose_action,
            "propose_candidate": self.cmd_propose_candidate,
            "try_fgi": self.cmd_try_fgi,
            "try_precursors": self.cmd_try_precursors,
            "sandbox_list": self.cmd_sandbox_list,
            "sandbox_clear": self.cmd_sandbox_clear,
            "select": self.cmd_select,
            "commit": self.cmd_commit,
            "accept": self.cmd_accept,
            "review_terminal": self.cmd_review_terminal,
            "skip": self.cmd_skip,
            "tree": self.cmd_tree,
            "status": self.cmd_status,
            "continuation_status": self.cmd_rescue_status,
            "continuation_abort": self.cmd_rescue_abort,
            "rescue_status": self.cmd_rescue_status,
            "rescue_abort": self.cmd_rescue_abort,
            "finalize": self.cmd_finalize,
            "report": self.cmd_report,
            "export": self.cmd_export,
            "smart_cap": self.cmd_smart_cap,
            "custom_cap": self.cmd_custom_cap,
        }
        fn = dispatch.get(command)
        if fn is None:
            return {"error": f"unknown command: {command}", "available": list(PUBLIC_COMMANDS)}
        try:
            result = fn(args)
            if command in PUBLIC_COMMANDS:
                return project_public_payload(result)
            return result
        except Exception as e:
            return {"error": str(e), "command": command}

    # ── 会话管理 ──

    def cmd_init(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """创建新会话。
        args: target (SMILES), name, max_depth, max_steps, terminal_cs_threshold
        """
        target = args.get("target", "")
        if not target:
            return {"error": "target SMILES required"}

        self._session = RetroSession.create(
            target,
            session_path=self.session_file,
            target_name=args.get("name", ""),
            max_depth=args.get("max_depth", 15),
            max_steps=args.get("max_steps", 50),
            terminal_cs_threshold=args.get("terminal_cs_threshold", CS_TRIVIAL),
        )
        return {
            "ok": True,
            "session_id": self._session.session_id,
            "session_file": str(self._session.path),
            "target": target,
            "name": args.get("name", ""),
            "hint": "调用 next 获取第一个分子的上下文",
        }

    # ── 编排流程 ──

    def cmd_next(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """取下一个分子。自动跳过所有 quick_pass terminal，
        直到遇到 standard 分子或队列为空。

        返回 compact 上下文 + 沙盒状态。
        """
        auto_terminals = []
        while True:
            ctx = self.session.prepare_next()
            if ctx is None:
                if auto_terminals:
                    return {
                        "action": "queue_empty",
                        "auto_terminals": auto_terminals,
                        "hint": "队列已空。调用 finalize 完成编排，或 tree 查看当前树。",
                    }
                return {
                    "action": "queue_empty",
                    "hint": "队列已空。调用 finalize 完成编排。",
                }

            if ctx.get("action") == "auto_terminal":
                auto_terminals.append({
                    "smiles": ctx["smiles"],
                    "cs_score": ctx["cs_score"],
                })
                continue

            # standard 分子
            result = ctx
            if auto_terminals:
                result["auto_terminals_skipped"] = auto_terminals
            return result

    def cmd_context(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """获取当前上下文。detail: compact/structure/full/diagnostic/status/tree"""
        detail = args.get("detail", "compact")
        return self.session.get_context(
            detail,
            bond_offset=args.get("bond_offset", 0),
            bond_limit=args.get("bond_limit"),
            fgi_offset=args.get("fgi_offset", 0),
            fgi_limit=args.get("fgi_limit", 5),
        )

    def cmd_guide(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Record chemist natural-language guidance for the active node."""
        return self.session.guide(
            text=args.get("text", ""),
            intent=args.get("intent", "directive"),
            site_hint=args.get("site_hint", ""),
            reaction_hint=args.get("reaction_hint", ""),
            precursors=args.get("precursors"),
            constraints=args.get("constraints"),
            terminal_hint=args.get("terminal_hint", ""),
            summary=args.get("summary", ""),
        )

    def cmd_route_plan(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Set or revise the persistent route-level synthesis thesis."""
        return self.session.route_plan(
            route_thesis=args.get("route_thesis", ""),
            route_mode=args.get("route_mode", ""),
            key_disconnections=args.get("key_disconnections"),
            preferred_precursor_logic=args.get("preferred_precursor_logic"),
            protect_or_preserve=args.get("protect_or_preserve"),
            mode_evidence=args.get("mode_evidence"),
            strategic_risks=args.get("strategic_risks"),
            revision_triggers=args.get("revision_triggers"),
            terminal_rescue_policy=args.get("terminal_rescue_policy", ""),
            revision_reason=args.get("revision_reason", ""),
        )

    def cmd_route_sketch(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Record a short route strategy sketch for weak action-space cases."""
        return self.session.route_sketch(
            problem=args.get("problem", ""),
            macro_strategy=args.get("macro_strategy", ""),
            key_disconnections=args.get("key_disconnections"),
            rejected_action_space_reason=args.get("rejected_action_space_reason", ""),
            next_executable_step=args.get("next_executable_step", ""),
            terminal_review=bool(args.get("terminal_review", False)),
            summary=args.get("summary", ""),
            rescue_steps=args.get("continuation_steps", args.get("rescue_steps")),
        )

    def cmd_explore(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """展开键位详情。args: bond_idx"""
        bond_idx = args.get("bond_idx", 0)
        return self.session.explore_bond(bond_idx)

    def cmd_reaction_sites(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Return the complete first-layer site/reaction menu."""
        return self.session.reaction_sites()

    def cmd_explore_site(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Expand all candidates competing at one real site. args: site_id"""
        site_id = args.get("site_id", "")
        if not site_id:
            return {"error": "site_id required"}
        return self.session.explore_site(site_id)

    def cmd_explore_reaction(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Expand one reaction family. args: reaction_id"""
        reaction_id = args.get("reaction_id", "")
        if not reaction_id:
            return {"error": "reaction_id required"}
        return self.session.explore_reaction(reaction_id)

    def cmd_explore_fgi(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """展开 FGI 详情。"""
        return self.session.explore_fgi()

    # ── 沙盒 ──

    def cmd_try_bond(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """沙盒试断键。args: bond_idx, alt_idx"""
        return self.session.sandbox_try(
            bond_idx=args.get("bond_idx", 0),
            alt_idx=args.get("alt_idx", 0),
        )

    def cmd_try_candidate(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """沙盒验证标准化候选。args: candidate_id"""
        candidate_id = args.get("candidate_id", "")
        if not candidate_id:
            return {"error": "candidate_id required"}
        return self.session.try_candidate(candidate_id)

    def cmd_try_action(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Sandbox one action-space entry. args: action_id"""
        action_id = args.get("action_id") or args.get("candidate_id") or ""
        if not action_id:
            return {"error": "action_id required"}
        return _public_validation_result(
            self.session.try_action(action_id),
            execution_scope="sandbox_validation",
        )

    def cmd_propose_candidate(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """登记 LLM 自建前体候选。args: strategy_id, precursors, reaction_type, ..."""
        return self.session.propose_candidate(
            strategy_id=args.get("strategy_id", ""),
            precursors=args.get("precursors", []),
            reaction_type=args.get("reaction_type", ""),
            reaction_id=args.get("reaction_id", ""),
            reaction_name=args.get("reaction_name", ""),
            candidate_label=args.get("candidate_label", ""),
            why_existing_candidates_rejected=args.get("why_existing_candidates_rejected", ""),
            rationale_summary=args.get("rationale_summary", ""),
            route_sketch_id=args.get("route_sketch_id", ""),
            rescue_id=internal_continuation_id(
                args.get("continuation_id", args.get("rescue_id", ""))
            ),
            rescue_step_idx=args.get("continuation_step_idx", args.get("rescue_step_idx")),
            continuation_precursor=args.get("continuation_precursor", ""),
            risk_tags=args.get("risk_tags"),
            intended_deltas=args.get("intended_deltas"),
            expected_ring_change=args.get("expected_ring_change", ""),
            changed_bonds=args.get("changed_bonds"),
            preserved_anchors=args.get("preserved_anchors"),
            mechanistic_evidence=args.get("mechanistic_evidence"),
            family_evidence=args.get("family_evidence"),
            experience_card_hints=args.get("experience_card_hints"),
        )

    def cmd_propose_action(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Register an LLM-proposed custom action."""
        return self.session.propose_action(
            strategy_id=args.get("strategy_id", ""),
            precursors=args.get("precursors", []),
            reagents=args.get("reagents", []),
            reaction_type=args.get("reaction_type", ""),
            reaction_id=args.get("reaction_id", ""),
            reaction_name=args.get("reaction_name", ""),
            action_label=args.get("action_label") or args.get("candidate_label", ""),
            why_existing_actions_rejected=(
                args.get("why_existing_actions_rejected")
                or args.get("why_existing_candidates_rejected", "")
            ),
            rationale_summary=args.get("rationale_summary", ""),
            route_sketch_id=args.get("route_sketch_id", ""),
            rescue_id=internal_continuation_id(
                args.get("continuation_id", args.get("rescue_id", ""))
            ),
            rescue_step_idx=args.get("continuation_step_idx", args.get("rescue_step_idx")),
            continuation_precursor=args.get("continuation_precursor", ""),
            risk_tags=args.get("risk_tags"),
            intended_deltas=args.get("intended_deltas"),
            expected_ring_change=args.get("expected_ring_change", ""),
            changed_bonds=args.get("changed_bonds"),
            preserved_anchors=args.get("preserved_anchors"),
            mechanistic_evidence=args.get("mechanistic_evidence"),
            family_evidence=args.get("family_evidence"),
            experience_card_hints=args.get("experience_card_hints"),
        )

    def cmd_try_fgi(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """沙盒试 FGI。args: fgi_idx"""
        return self.session.sandbox_try(fgi_idx=args.get("fgi_idx", 0))

    def cmd_try_precursors(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """沙盒试 LLM 自提前体。args: precursors (list), reaction_type"""
        precursors = args.get("precursors", [])
        if not precursors:
            return {"error": "precursors list required"}
        candidate_meta = {
            "source": "custom_precursors",
            "reaction_type": args.get("reaction_type", ""),
            "risk_tags": args.get("risk_tags", []),
            "intended_deltas": args.get("intended_deltas", []),
            "expected_ring_change": args.get("expected_ring_change", ""),
            "changed_bonds": args.get("changed_bonds", []),
            "preserved_anchors": args.get("preserved_anchors", []),
            "mechanistic_evidence": args.get("mechanistic_evidence", []),
            "family_evidence": args.get("family_evidence", {}),
            "rationale_summary": args.get("rationale_summary", ""),
        }
        if "in_ring" in args:
            candidate_meta["in_ring"] = bool(args.get("in_ring"))
        return self.session.sandbox_try(
            precursors=precursors,
            reaction_type=args.get("reaction_type", ""),
            candidate_meta=candidate_meta,
        )

    def cmd_sandbox_list(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """查看沙盒历史。"""
        attempts = self.session._sandbox_attempts
        selected = self.session._sandbox_selected

        def site_id_for(attempt: Dict[str, Any]) -> str:
            summary = attempt.get("candidate_summary") or {}
            source = summary.get("source") or attempt.get("source", "")
            if source == "bond" or str(source).startswith("bond["):
                bond_id = summary.get("actual_bond_idx")
                if bond_id is None:
                    bond_id = summary.get("bond_idx")
                return f"bond:{bond_id}" if bond_id is not None else "bond:unknown"
            if source == "fgi" or str(source).startswith("fgi["):
                fgi_id = summary.get("fgi_idx")
                return f"fgi:{fgi_id}" if fgi_id is not None else "fgi:unknown"
            if source == "smart_capping":
                bond_id = summary.get("actual_bond_idx")
                if bond_id is None:
                    bond_id = summary.get("bond_idx")
                return f"bond:{bond_id}" if bond_id is not None else "bond:unknown"
            if source == "custom_precursors":
                return f"custom:{attempt.get('candidate_id', 'unknown')}"
            return "unassigned"

        def attempt_row(i: int, attempt: Dict[str, Any]) -> Dict[str, Any]:
            return _public_validation_result({
                "idx": i,
                "action_id": attempt.get("candidate_id", ""),
                "site_id": site_id_for(attempt),
                "source": attempt.get("source", "?"),
                "success": attempt.get("success", False),
                "precursors": attempt.get("precursors", []),
                "reagents": attempt.get("reagents", []),
                "reaction_type": attempt.get("reaction_type", ""),
                "forward_validation": attempt.get("forward_validation") or {},
                "validation_micro": attempt.get("validation_micro") or {},
                "site_audit": attempt.get("site_audit") or {},
            }, execution_scope="sandbox_validation")

        by_site: Dict[str, Dict[str, Any]] = {}
        by_reaction: Dict[str, Dict[str, Any]] = {}
        for i, attempt in enumerate(attempts):
            summary = attempt.get("candidate_summary") or {}
            site_id = site_id_for(attempt)
            site_bucket = by_site.setdefault(site_id, {"site_id": site_id, "attempt_idxs": []})
            site_bucket["attempt_idxs"].append(i)

            reaction_id = summary.get("reaction_id") or ""
            reaction_name = attempt.get("reaction_type", "") or summary.get("reaction_type", "") or "unknown"
            reaction_key = reaction_id or reaction_name
            reaction_bucket = by_reaction.setdefault(
                reaction_key,
                {
                    "reaction_id": reaction_id,
                    "reaction_name": reaction_name,
                    "attempt_idxs": [],
                },
            )
            reaction_bucket["attempt_idxs"].append(i)
        return {
            "n_attempts": len(attempts),
            "selected": selected,
            "by_site": list(by_site.values()),
            "by_reaction": list(by_reaction.values()),
            "attempts": [
                attempt_row(i, a)
                for i, a in enumerate(attempts)
            ],
            "prompt_brief": self.session._build_prompt_brief(
                "sandbox_list",
                attempts=attempts,
                payload={"by_site": list(by_site.values()), "by_reaction": list(by_reaction.values())},
            ),
        }

    def cmd_sandbox_clear(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """清空沙盒。"""
        self.session.sandbox_clear()
        return {"ok": True, "hint": "沙盒已清空"}

    def cmd_select(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """选中沙盒方案。args: idx"""
        idx = args.get("idx", 0)
        return _public_validation_result(
            self.session.sandbox_select(idx),
            execution_scope="sandbox_selection",
        )

    # ── 决策提交 ──

    def cmd_commit(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """提交决策写入树。
        args: idx (attempt), reasoning, confidence, rejected (list),
              validation_override
        """
        result = self.session.commit(
            attempt_idx=args.get("idx"),
            expected_action_id=args.get("expected_action_id", ""),
            reasoning=args.get("reasoning", ""),
            confidence=args.get("confidence", "medium"),
            rejected=args.get("rejected"),
            validation_override=args.get("validation_override"),
            route_plan_alignment=args.get("route_plan_alignment", ""),
            route_plan_note=args.get("route_plan_note", ""),
        )
        return _public_validation_result(result, execution_scope="commit")

    def cmd_accept(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """标记当前分子为 terminal。args: reason"""
        return self.session.accept_terminal(
            reason=args.get("reason", ""),
            rescue_not_actionable_reason=args.get("rescue_not_actionable_reason", ""),
            force_accept_without_rescue=bool(args.get("force_accept_without_rescue", False)),
        )

    def cmd_review_terminal(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Requeue an existing terminal leaf for normal LLM review."""
        return self.session.review_terminal(
            smiles=args.get("smiles", ""),
            reason=args.get("reason", ""),
            additional_steps=args.get("additional_steps", 0),
        )

    def cmd_skip(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """跳过当前分子。args: reason"""
        self.session.skip(reason=args.get("reason", ""))
        return {"ok": True, "action": "skipped"}

    # ── 查看 ──

    def cmd_tree(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """打印合成树。"""
        tree_text = self.session.orch.tree.print_tree()
        terminals = self.session.orch.tree.get_terminal_smiles()
        pending = self.session.orch.tree.get_pending_molecules()
        return {
            "tree": tree_text,
            "terminal_count": len(terminals),
            "pending_count": len(pending),
            "terminals": terminals,
        }

    def cmd_status(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """查看编排状态。"""
        return self.session.get_status()

    def cmd_rescue_status(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Inspect active multi-step strategy continuations."""
        return self.session.rescue_status()

    def cmd_rescue_abort(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Close a pending rescue continuation with an explicit reason."""
        return self.session.rescue_abort(
            rescue_id=internal_continuation_id(
                args.get("continuation_id", args.get("rescue_id", ""))
            ),
            reason=args.get("reason", ""),
        )

    def cmd_finalize(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """完成编排。args: summary"""
        return self.session.finalize(summary=args.get("summary", ""))

    def cmd_report(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """生成正向合成报告。"""
        tree = self.session.orch.tree
        report_text = generate_forward_report(tree)
        terminals = get_terminal_list(tree)
        return {
            "report": report_text,
            "starting_materials": terminals,
        }

    def cmd_export(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """导出结果到 output/ 目录。args: name, output_dir"""
        return export_results(
            self.session,
            output_dir=args.get("output_dir"),
            name=args.get("name"),
        )

    def cmd_smart_cap(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """智能断键推理。args: bond_idx 或 bond (atom pair) + smiles (可选)"""
        from Rachel.chem_tools.smart_cap import suggest_capping

        # 方式 1: 直接指定 smiles + bond
        smiles = args.get("smiles")
        bond = args.get("bond")
        if smiles and bond:
            return suggest_capping(smiles, tuple(bond), max_proposals=args.get("max", 5))

        # 方式 2: 从当前 context 中按 bond_idx 查询
        bond_idx = args.get("bond_idx", 0)
        orch = self.session.orch
        ctx = orch._current_context
        if ctx is None or ctx.decision_context is None:
            return {"error": "no active context, use smiles+bond or call next first"}

        bonds = ctx.decision_context.get("disconnectable_bonds", [])
        if bond_idx < 0 or bond_idx >= len(bonds):
            return {"error": "bond_idx %d out of range (0-%d)" % (bond_idx, len(bonds) - 1)}

        atoms = tuple(bonds[bond_idx]["atoms"])
        return suggest_capping(ctx.smiles, atoms, max_proposals=args.get("max", 5))

    def cmd_custom_cap(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """LLM 自定义 capping。args: cap_i, cap_j + (bond_idx 或 smiles+bond), reaction_type"""
        from Rachel.chem_tools.smart_cap import custom_cap

        cap_i = args.get("cap_i", "")
        cap_j = args.get("cap_j", "")
        if not cap_i or not cap_j:
            return {"error": "cap_i and cap_j required"}

        # 方式 1: 直接指定 smiles + bond
        smiles = args.get("smiles")
        bond = args.get("bond")
        if smiles and bond:
            return custom_cap(smiles, tuple(bond), cap_i, cap_j,
                              reaction_type=args.get("reaction_type", "llm_custom"))

        # 方式 2: 从当前 context 按 bond_idx
        bond_idx = args.get("bond_idx", 0)
        orch = self.session.orch
        ctx = orch._current_context
        if ctx is None or ctx.decision_context is None:
            return {"error": "no active context, use smiles+bond or call next first"}

        bonds = ctx.decision_context.get("disconnectable_bonds", [])
        if bond_idx < 0 or bond_idx >= len(bonds):
            return {"error": "bond_idx %d out of range (0-%d)" % (bond_idx, len(bonds) - 1)}

        atoms = tuple(bonds[bond_idx]["atoms"])
        return custom_cap(ctx.smiles, atoms, cap_i, cap_j,
                          reaction_type=args.get("reaction_type", "llm_custom"))


# ── 固定路径 JSON 通信 ──
# .rachel/ 目录下:
#   cmd.json     — LLM 写入命令 {"command": "next", "args": {...}}
#   result.json  — 系统写入结果
#   session.json — 会话状态（持久化）
#
# 两种 CLI 模式:
#   模式 1 (直接): python retro_cmd.py <command> [session] [args.json]
#   模式 2 (JSON): python retro_cmd.py --run [rachel_dir]
#     读 .rachel/cmd.json → 执行 → 写 .rachel/result.json → 清空 cmd.json

RACHEL_DIR = Path(__file__).resolve().parent.parent / ".rachel"
DEFAULT_SESSION = str(RACHEL_DIR / "session.json")
CMD_FILE = RACHEL_DIR / "cmd.json"
RESULT_FILE = RACHEL_DIR / "result.json"


def _ensure_rachel_dir():
    """确保 .rachel/ 目录存在。"""
    RACHEL_DIR.mkdir(parents=True, exist_ok=True)


def _run_from_cmd_json(rachel_dir: Optional[Path] = None):
    """模式 2: 读 cmd.json → 执行 → 写 result.json。"""
    rdir = rachel_dir or RACHEL_DIR
    cmd_file = rdir / "cmd.json"
    result_file = rdir / "result.json"
    session_file = str(rdir / "session.json")

    if not cmd_file.exists():
        result = {"error": f"cmd.json not found at {cmd_file}"}
        result_file.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        return

    # Be tolerant of UTF-8 BOM (common on Windows) in cmd.json.
    with open(cmd_file, "r", encoding="utf-8-sig") as f:
        cmd_data = json.load(f)

    command = cmd_data.get("command", "")
    args = cmd_data.get("args", {})

    if not command:
        result = {"error": "cmd.json missing 'command' field"}
        result_file.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        return

    cmd = RetroCmd(session_file)
    result = cmd.execute(command, args)

    result_file.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    # 清空 cmd.json（标记已消费）
    cmd_file.write_text("{}", encoding="utf-8")


def _cli_main():
    import sys
    args_list = sys.argv[1:]

    # 静默 RDKit 警告
    try:
        from rdkit import RDLogger
        RDLogger.DisableLog("rdApp.*")
    except ImportError:
        pass

    _ensure_rachel_dir()

    if not args_list:
        print(json.dumps({
            "error": "usage: retro_cmd <command> [session_file] [args.json]",
            "alt_usage": "retro_cmd --run [rachel_dir]  (读 cmd.json 模式)",
            "commands": list(PUBLIC_COMMANDS),
            "rachel_dir": str(RACHEL_DIR),
            "session_file": DEFAULT_SESSION,
        }, indent=2, ensure_ascii=False))
        return

    # 模式 2: --run
    if args_list[0] == "--run":
        rdir = Path(args_list[1]) if len(args_list) > 1 else None
        _run_from_cmd_json(rdir)
        return

    # 模式 1: 直接命令
    command = args_list[0]
    session_file = args_list[1] if len(args_list) > 1 else DEFAULT_SESSION
    args_input = args_list[2] if len(args_list) > 2 else None

    # 解析 args
    cmd_args: Dict[str, Any] = {}
    if args_input:
        args_path = Path(args_input)
        if args_path.exists() and args_path.suffix == ".json":
            with open(args_path, "r", encoding="utf-8") as f:
                cmd_args = json.load(f)
        else:
            try:
                cmd_args = json.loads(args_input)
            except json.JSONDecodeError:
                print(json.dumps({"error": f"invalid args: {args_input}"}))
                return

    cmd = RetroCmd(session_file)
    result = cmd.execute(command, cmd_args)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    _cli_main()
