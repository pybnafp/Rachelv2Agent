"""
JSON 会话持久化层
=================
用一个 JSON 文件维护编排器的完整状态，解决三个核心问题:

1. SMILES 安全 — JSON 中 [N+](=O)[O-] 是纯字符串，不被转义
2. 上下文恢复 — LLM 对话断了，读 JSON 即可恢复
3. 沙盒可擦除 — sandbox 区域随时擦除重写，commit 后才进 tree

JSON 结构:
{
  "session_id": "abc123",
  "target": { smiles, name, cs_score },
  "config": { max_depth, max_steps, terminal_cs_threshold, ... },
  "status": { phase, steps_executed, pending_count, ... },

  "current": {                    ← LLM 当前工作区
    "smiles": "...",
    "node_id": "mol_3",
    "depth": 2,
    "analysis": { cs_score, classification, functional_groups, ... },
    "bond_summary": [...],        ← 精简键位概览
    "fgi_summary": [...],
    "sandbox": {                  ← 沙盒试探结果（可擦除）
      "attempts": [
        { precursors, validation, reaction_type, ... },
      ],
      "selected": null | index    ← LLM 选中的方案
    }
  },

  "tree": { ... },               ← RetrosynthesisTree.to_dict()
  "audit_state": { ... },        ← SynthesisAuditState.to_dict()
  "queue": [ [smiles, depth], ... ]
}

用法:
  session = RetroSession.create("CCO", name="Ethanol")
  session.save("path/to/session.json")

  # LLM 对话断了，恢复:
  session = RetroSession.load("path/to/session.json")
  orch = session.get_orchestrator()
"""

from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from Rachel.chem_tools._rdkit_utils import canonical
from Rachel.chem_tools.cs_score import CS_TRIVIAL
from Rachel.chem_tools.precursor_normalization import normalize_precursor_set, normalize_reagent_set
from Rachel.chem_tools.site_audit import reasoning_claims_site_retention
from Rachel.tools.llm_retro_platform import build_decision_context
from .retro_orchestrator import (
    RetrosynthesisOrchestrator,
    ProposalContext,
    SandboxResult,
    CommitResult,
)
from .retro_tree import RetrosynthesisTree, MoleculeRole, TreeStatus, LLMDecision
from .retro_state import SynthesisAuditState
from .strategy_disclosure import build_candidate_units, find_candidate
from .prompt_mount import build_prompt_brief, build_prompt_mount


_ACTION_FIELD_RENAMES = {
    "candidate_id": "action_id",
    "candidate_label": "action_label",
    "candidate_summary": "action_summary",
    "candidate_comparison": "action_comparison",
    "candidate_consistency": "action_consistency",
    "selected_candidate_id": "selected_action_id",
    "rejected_candidates": "rejected_actions",
    "rejected_candidate_ids": "rejected_action_ids",
    "why_existing_candidates_rejected": "why_existing_actions_rejected",
}

_VALIDATION_INTENT_FIELDS = (
    "intended_deltas",
    "expected_ring_change",
    "changed_bonds",
    "preserved_anchors",
    "mechanistic_evidence",
    "family_evidence",
    "rationale_summary",
)


def _action_facing_payload(value: Any) -> Any:
    """Return a copy of a session payload using the public action schema."""
    if isinstance(value, dict):
        projected: Dict[str, Any] = {}
        for key, item in value.items():
            projected[_ACTION_FIELD_RENAMES.get(key, key)] = _action_facing_payload(item)
        return projected
    if isinstance(value, list):
        return [_action_facing_payload(item) for item in value]
    return value


def _copy_validation_intent(source: Dict[str, Any]) -> Dict[str, Any]:
    """Copy non-empty LLM-declared validation intent fields."""
    out: Dict[str, Any] = {}
    for key in _VALIDATION_INTENT_FIELDS:
        value = source.get(key)
        if value in (None, "", [], {}):
            continue
        out[key] = value
    return out


class RetroSession:
    """JSON 持久化会话。包装 RetrosynthesisOrchestrator，
    每次操作后自动保存状态到 JSON 文件。

    核心设计:
      - 所有 SMILES 只存在 JSON 中，不经过终端/shell
      - sandbox 区域可随时擦除，commit 后才写入 tree
      - LLM 读 JSON 获取上下文，写 JSON 提交决策
      - 对话断了读 JSON 即可恢复完整状态
    """

    def __init__(
        self,
        orchestrator: RetrosynthesisOrchestrator,
        session_path: str,
        session_id: str = "",
    ):
        self.orch = orchestrator
        self.path = Path(session_path)
        self.session_id = session_id or uuid.uuid4().hex[:8]
        self._sandbox_attempts: List[Dict[str, Any]] = []
        self._sandbox_selected: Optional[int] = None
        self._chemist_guidance: List[Dict[str, Any]] = []
        self._route_sketches: List[Dict[str, Any]] = []
        self._rescue_continuations: List[Dict[str, Any]] = []
        self._route_plan: Dict[str, Any] = {}
        self._route_plan_history: List[Dict[str, Any]] = []

    def _active_molecule(self) -> str:
        ctx = self.orch._current_context
        return ctx.smiles if ctx else ""

    def _archive_sandbox(self, event: str, selected_idx: Optional[int] = None) -> None:
        if not self._sandbox_attempts:
            return
        self.orch.audit_state.record_candidate_audit(
            event=event,
            molecule=self._active_molecule(),
            attempts=self._sandbox_attempts,
            selected_idx=selected_idx,
        )

    def _candidate_lookup(self, candidate_id: str) -> Optional[Dict[str, Any]]:
        ctx = self.orch._current_context
        if ctx is None or ctx.decision_context is None:
            return None
        return find_candidate(ctx.decision_context, candidate_id)

    def _precursor_key(self, precursors: List[str]) -> Tuple[str, ...]:
        normalized = []
        for smi in precursors:
            normalized.append(canonical(smi) or smi)
        return tuple(sorted(normalized))

    def _custom_candidate_role_slug(self, strategy_id: str) -> str:
        raw = str(strategy_id or "llm_custom").strip() or "llm_custom"
        slug = re.sub(r"[^A-Za-z0-9]+", "_", raw).strip("_").lower()
        return slug or "llm_custom"

    def _find_duplicate_candidate(
        self,
        precursors: List[str],
        *,
        reagents: Optional[List[str]] = None,
        exclude_prefix: str = "custom:",
    ) -> str:
        ctx = self.orch._current_context
        if ctx is None or ctx.decision_context is None:
            return ""
        target_key = self._precursor_key(precursors)
        target_reagent_key = self._precursor_key(list(reagents or []))
        for candidate in build_candidate_units(ctx.decision_context):
            candidate_id = candidate.candidate_id
            if exclude_prefix and candidate_id.startswith(exclude_prefix):
                continue
            preview = candidate.precursors_preview or candidate.fragments
            reagent_key = self._precursor_key(list(candidate.reagents or []))
            if (
                preview
                and self._precursor_key(preview) == target_key
                and reagent_key == target_reagent_key
            ):
                return candidate_id
        return ""

    def _guidance_summary_text(self, text: str, *, max_chars: int = 240) -> str:
        summary = re.sub(r"\s+", " ", str(text or "")).strip()
        if len(summary) <= max_chars:
            return summary
        return summary[: max_chars - 3].rstrip() + "..."

    def _guidance_brief(self) -> List[Dict[str, str]]:
        brief: List[Dict[str, str]] = []
        for item in self._chemist_guidance:
            if not isinstance(item, dict):
                continue
            guidance_id = str(item.get("id", "")).strip()
            summary = str(item.get("summary", "")).strip()
            if not guidance_id or not summary:
                continue
            brief.append({
                "id": guidance_id,
                "intent": str(item.get("intent", "") or "directive").strip()[:80],
                "summary": summary[:240],
            })
            if len(brief) >= 2:
                break
        return brief

    def _guidance_provenance(self) -> List[Dict[str, Any]]:
        provenance: List[Dict[str, Any]] = []
        for item in self._chemist_guidance:
            if not isinstance(item, dict):
                continue
            provenance.append(dict(item))
        return provenance

    def _canonical_smiles_text(self, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        return canonical(text) or text

    def _normalize_rescue_steps(self, steps: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        if not isinstance(steps, list):
            return normalized
        for idx, raw in enumerate(steps):
            if not isinstance(raw, dict):
                continue
            try:
                step_idx = int(raw.get("step_idx", idx))
            except (TypeError, ValueError):
                step_idx = idx
            entry: Dict[str, Any] = {
                "step_idx": step_idx,
                "status": str(raw.get("status") or "planned").strip()[:40] or "planned",
            }
            for source_key, target_key, limit in (
                ("target_smiles", "target_smiles", 0),
                ("target_hint", "target_hint", 160),
                ("reaction_name", "reaction_name", 120),
                ("rationale", "rationale", 220),
            ):
                value = str(raw.get(source_key, "") or "").strip()
                if not value:
                    continue
                if target_key == "target_smiles":
                    value = self._canonical_smiles_text(value)
                else:
                    value = self._guidance_summary_text(value, max_chars=limit)
                if value:
                    entry[target_key] = value
            expected = []
            for smi in raw.get("expected_precursors", []) or []:
                can = self._canonical_smiles_text(smi)
                if can:
                    expected.append(can)
            if expected:
                entry["expected_precursors"] = expected[:6]
            continuation = (
                raw.get("continuation_precursor")
                or raw.get("continuation_smiles")
                or raw.get("focus_precursor")
                or ""
            )
            continuation_can = self._canonical_smiles_text(continuation)
            if continuation_can:
                entry["continuation_precursor"] = continuation_can
            if len(entry) > 2:
                normalized.append(entry)
        normalized.sort(key=lambda item: int(item.get("step_idx", 0)))
        return normalized[:8]

    def _compact_rescue_steps(
        self,
        steps: Optional[List[Dict[str, Any]]],
        *,
        limit: int = 3,
    ) -> List[Dict[str, Any]]:
        compact: List[Dict[str, Any]] = []
        for step in (steps or [])[:limit]:
            if not isinstance(step, dict):
                continue
            item: Dict[str, Any] = {"step_idx": step.get("step_idx", len(compact))}
            for key in (
                "target_smiles",
                "target_hint",
                "reaction_name",
                "expected_precursors",
                "continuation_precursor",
                "status",
            ):
                value = step.get(key)
                if value not in ("", [], {}, None):
                    item[key] = value
            compact.append(item)
        return compact

    def _find_route_sketch(self, sketch_id: str) -> Dict[str, Any]:
        if not sketch_id:
            return {}
        for item in reversed(self._route_sketches):
            if isinstance(item, dict) and item.get("id") == sketch_id:
                return item
        return {}

    def _pending_rescue_continuations(self) -> List[Dict[str, Any]]:
        return [
            item
            for item in self._rescue_continuations
            if isinstance(item, dict) and item.get("status") == "pending"
        ]

    def _active_rescue_continuation_for_smiles(self, smiles: str) -> Dict[str, Any]:
        can = self._canonical_smiles_text(smiles)
        if not can:
            return {}
        for item in self._pending_rescue_continuations():
            if item.get("focus_smiles") == can:
                return item
        return {}

    def _rescue_next_step(self, item: Dict[str, Any]) -> Dict[str, Any]:
        remaining = item.get("remaining_steps") or []
        for step in remaining:
            if isinstance(step, dict):
                return step
        return {}

    def _rescue_continuation_brief(self, item: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(item, dict) or not item:
            return {}
        brief = {
            "id": item.get("id", ""),
            "route_sketch_id": item.get("route_sketch_id", ""),
            "focus_smiles": item.get("focus_smiles", ""),
            "status": item.get("status", ""),
            "reason": item.get("reason", ""),
            "next_step": self._rescue_next_step(item),
            "remaining_step_count": len(item.get("remaining_steps") or []),
        }
        return {key: value for key, value in brief.items() if value not in ("", [], {}, None)}

    def _active_rescue_continuation_brief(self) -> Dict[str, Any]:
        ctx = self.orch._current_context
        if ctx is None:
            return {}
        return self._rescue_continuation_brief(
            self._active_rescue_continuation_for_smiles(ctx.smiles)
        )

    def _attach_rescue_affordances(
        self,
        current: Dict[str, Any],
        rescue_brief: Dict[str, Any],
    ) -> None:
        if not rescue_brief:
            return
        current["rescue_continuation_brief"] = rescue_brief
        commands = current.setdefault("commands", {})
        commands["rescue_status"] = "rescue_status()"
        commands["rescue_abort"] = "rescue_abort(rescue_id, reason)"

    def _ensure_rescue_focus_routed(self, item: Dict[str, Any]) -> None:
        focus = self._canonical_smiles_text(item.get("focus_smiles", ""))
        if not focus:
            return
        node = self.orch.tree.get_molecule_by_smiles(focus)
        if node is not None:
            self.orch.tree.mark_intermediate(focus)
            depth = node.depth
        else:
            depth = int(item.get("depth", 0) or 0)
        self.orch._force_standard_smiles.add(focus)
        current = self.orch._current_context
        if current is not None and current.smiles == focus:
            return
        if self.orch.select_next(focus):
            return
        self.orch._queue.appendleft((focus, depth))
        self.orch._seen.add(focus)

    def _prioritize_pending_rescue(self) -> None:
        for item in self._pending_rescue_continuations():
            self._ensure_rescue_focus_routed(item)
            return

    def _step_idx_value(self, value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _plan_steps_for_commit(
        self,
        route_sketch_id: str,
        active_rescue: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        sketch = self._find_route_sketch(route_sketch_id)
        sketch_steps = sketch.get("rescue_steps") if sketch else []
        if isinstance(sketch_steps, list) and sketch_steps:
            return [dict(step) for step in sketch_steps if isinstance(step, dict)]
        if isinstance(active_rescue, dict):
            remaining = active_rescue.get("remaining_steps") or []
            return [dict(step) for step in remaining if isinstance(step, dict)]
        return []

    def _default_rescue_step_idx(
        self,
        steps: List[Dict[str, Any]],
        active_rescue: Optional[Dict[str, Any]],
    ) -> int:
        if isinstance(active_rescue, dict) and active_rescue:
            next_step = self._rescue_next_step(active_rescue)
            if next_step:
                return self._step_idx_value(next_step.get("step_idx"), 0)
        if steps:
            return self._step_idx_value(steps[0].get("step_idx"), 0)
        return 0

    def _choose_rescue_focus(
        self,
        *,
        attempt: Dict[str, Any],
        current_step: Dict[str, Any],
        remaining_steps: List[Dict[str, Any]],
    ) -> str:
        summary = attempt.get("candidate_summary") or {}
        precursors = [
            self._canonical_smiles_text(smi)
            for smi in attempt.get("precursors", []) or []
            if self._canonical_smiles_text(smi)
        ]
        requested = (
            summary.get("continuation_precursor")
            or attempt.get("continuation_precursor")
            or current_step.get("continuation_precursor")
            or ""
        )
        focus = self._canonical_smiles_text(requested)
        if focus and focus in precursors:
            return focus
        next_target = self._canonical_smiles_text(
            (remaining_steps[0] or {}).get("target_smiles", "") if remaining_steps else ""
        )
        if next_target and next_target in precursors:
            return next_target
        if len(precursors) == 1:
            return precursors[0]
        return ""

    def _close_active_rescue_after_commit(
        self,
        active_rescue: Optional[Dict[str, Any]],
        result: CommitResult,
    ) -> None:
        if not isinstance(active_rescue, dict) or not active_rescue:
            return
        rescue_id = active_rescue.get("id", "")
        for item in self._rescue_continuations:
            if item.get("id") == rescue_id and item.get("status") == "pending":
                item["status"] = "completed"
                item["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                if result.reaction_node:
                    item["completed_step_id"] = result.reaction_node.step_id
                focus = item.get("focus_smiles", "")
                if focus:
                    self.orch._force_standard_smiles.discard(focus)
                return

    def _register_rescue_continuation_after_commit(
        self,
        *,
        attempt: Dict[str, Any],
        result: CommitResult,
        route_sketch_id: str,
        active_rescue: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not result.success:
            return {}
        plan_steps = self._plan_steps_for_commit(route_sketch_id, active_rescue)
        if len(plan_steps) < 2 and not active_rescue:
            return {}
        summary = attempt.get("candidate_summary") or {}
        selected_idx = (
            summary.get("rescue_step_idx")
            if summary.get("rescue_step_idx") is not None
            else attempt.get("rescue_step_idx")
        )
        selected_step_idx = self._step_idx_value(
            selected_idx,
            self._default_rescue_step_idx(plan_steps, active_rescue),
        )
        current_step = {}
        for step in plan_steps:
            if self._step_idx_value(step.get("step_idx"), -1) == selected_step_idx:
                current_step = step
                break
        remaining = [
            dict(step)
            for step in plan_steps
            if self._step_idx_value(step.get("step_idx"), -1) > selected_step_idx
        ]
        self._close_active_rescue_after_commit(active_rescue, result)
        if not remaining:
            return {}

        focus = self._choose_rescue_focus(
            attempt=attempt,
            current_step=current_step,
            remaining_steps=remaining,
        )
        if not focus:
            return {
                "warning": "rescue_continuation_unbound",
                "route_sketch_id": route_sketch_id,
                "selected_step_idx": selected_step_idx,
            }

        node = self.orch.tree.get_molecule_by_smiles(focus)
        depth = node.depth if node else 0
        rescue_id = f"rescue:{route_sketch_id or 'continuation'}:{selected_step_idx + 1}:{len(self._rescue_continuations)}"
        entry: Dict[str, Any] = {
            "id": rescue_id,
            "route_sketch_id": route_sketch_id,
            "parent_rescue_id": active_rescue.get("id", "") if isinstance(active_rescue, dict) else "",
            "origin_step_id": result.reaction_node.step_id if result.reaction_node else "",
            "focus_smiles": focus,
            "depth": depth,
            "status": "pending",
            "reason": "route_sketch_multi_step_rescue",
            "selected_step_idx": selected_step_idx,
            "remaining_steps": remaining,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        for existing in self._pending_rescue_continuations():
            if existing.get("focus_smiles") == focus and existing.get("route_sketch_id") == route_sketch_id:
                existing.update(entry)
                entry = existing
                break
        else:
            self._rescue_continuations.append(entry)

        if focus in result.new_terminal:
            result.new_terminal = [smi for smi in result.new_terminal if smi != focus]
        if focus not in result.new_pending:
            result.new_pending.append(focus)
        self._ensure_rescue_focus_routed(entry)
        return self._rescue_continuation_brief(entry)

    def _route_strategy_brief(self) -> Dict[str, Any]:
        if not self._route_sketches:
            return {}
        item = self._route_sketches[-1]
        if not isinstance(item, dict):
            return {}
        sketch_id = str(item.get("id", "")).strip()
        macro = str(item.get("macro_strategy", "")).strip()
        if not sketch_id or not macro:
            return {}
        brief = {
            "id": sketch_id,
            "macro_strategy": macro[:240],
        }
        next_step = str(item.get("next_executable_step", "")).strip()
        if next_step:
            brief["next_executable_step"] = next_step[:120]
        problem = str(item.get("problem", "")).strip()
        if problem:
            brief["problem"] = problem[:160]
        if item.get("terminal_review"):
            brief["terminal_review"] = True
        rescue_steps = self._compact_rescue_steps(item.get("rescue_steps"))
        if rescue_steps:
            brief["rescue_steps"] = rescue_steps
        return brief

    def _route_sketch_provenance(self) -> List[Dict[str, Any]]:
        return [dict(item) for item in self._route_sketches if isinstance(item, dict)]

    def _latest_route_sketch_id(self) -> str:
        brief = self._route_strategy_brief()
        return brief.get("id", "")

    def _clear_route_sketch_state(self) -> None:
        self._route_sketches = []
        strategic_plan = dict(self.orch.audit_state.strategic_plan or {})
        for key in ("active_route_sketch", "problem", "next_executable_step"):
            strategic_plan.pop(key, None)
        self.orch.audit_state.update_strategic_plan(strategic_plan)

    def _latest_terminal_review_sketch(self) -> Dict[str, Any]:
        for item in reversed(self._route_sketches):
            if isinstance(item, dict) and item.get("terminal_review"):
                return item
        return {}

    def _terminal_rescue_attempt_count(self, sketch_id: str) -> int:
        if not sketch_id:
            return 0
        count = 0
        for attempt in self._sandbox_attempts:
            summary = attempt.get("candidate_summary") or {}
            attempt_sketch_id = summary.get("route_sketch_id") or attempt.get("route_sketch_id", "")
            source = summary.get("source") or attempt.get("source", "")
            candidate_id = attempt.get("candidate_id", "")
            is_custom = source == "custom_precursors" or str(candidate_id).startswith("custom:")
            if is_custom and attempt_sketch_id == sketch_id:
                count += 1
        return count

    def _terminal_rescue_gate(
        self,
        *,
        rescue_not_actionable_reason: str = "",
        force_accept_without_rescue: bool = False,
    ) -> Dict[str, Any]:
        sketch = self._latest_terminal_review_sketch()
        if not sketch:
            return {}

        sketch_id = str(sketch.get("id", "")).strip()
        rescue_attempt_count = self._terminal_rescue_attempt_count(sketch_id)
        reason = self._guidance_summary_text(rescue_not_actionable_reason, max_chars=320)
        rescue_steps = [
            dict(step)
            for step in (sketch.get("rescue_steps") or [])
            if isinstance(step, dict)
        ]
        has_multistep_plan = len(rescue_steps) >= 2
        if has_multistep_plan and rescue_attempt_count > 0:
            if force_accept_without_rescue and reason:
                return {
                    "route_sketch_id": sketch_id,
                    "terminal_review": True,
                    "rescue_attempt_count": rescue_attempt_count,
                    "rescue_step_count": len(rescue_steps),
                    "force_accept_without_rescue": True,
                    "rescue_not_actionable_reason": reason,
                }
            return {
                "error": "terminal_rescue_continuation_required",
                "route_sketch_id": sketch_id,
                "terminal_review": True,
                "rescue_attempt_count": rescue_attempt_count,
                "rescue_step_count": len(rescue_steps),
                "required_next_action": "commit credible attempt to create rescue_continuation, or force_accept_without_rescue with reason",
                "hint": (
                    "This terminal-review sketch defines a multi-step mini-route. A sandbox "
                    "attempt alone is not route completion; commit a credible first event so "
                    "the continuation precursor is reviewed by next(), or explicitly explain "
                    "why the mini-route cannot be repaired."
                ),
            }
        if rescue_attempt_count > 0:
            return {
                "route_sketch_id": sketch_id,
                "terminal_review": True,
                "rescue_attempt_count": rescue_attempt_count,
            }

        if force_accept_without_rescue and reason:
            return {
                "route_sketch_id": sketch_id,
                "terminal_review": True,
                "rescue_attempt_count": 0,
                "rescue_step_count": len(rescue_steps),
                "force_accept_without_rescue": True,
                "rescue_not_actionable_reason": reason,
            }

        return {
            "error": "terminal_rescue_required",
            "route_sketch_id": sketch_id,
            "terminal_review": True,
            "rescue_attempt_count": 0,
            "required_next_action": "propose_action -> try_action -> sandbox_list",
            "hint": (
                "Terminal-review sketches must be followed by at least one route-sketch-derived "
                "custom action sandbox attempt before accept. If no one-step action can even be "
                "defined, pass force_accept_without_rescue=true with rescue_not_actionable_reason."
            ),
        }

    def _route_plan_brief(self) -> Dict[str, Any]:
        if not isinstance(self._route_plan, dict) or not self._route_plan:
            return {}
        plan_id = str(self._route_plan.get("id", "")).strip()
        thesis = str(self._route_plan.get("route_thesis", "")).strip()
        if not plan_id or not thesis:
            return {}
        brief: Dict[str, Any] = {
            "id": plan_id,
            "revision": int(self._route_plan.get("revision", 0) or 0),
            "route_thesis": thesis[:260],
        }
        route_mode = str(self._route_plan.get("route_mode", "")).strip()
        if route_mode:
            brief["route_mode"] = route_mode[:80]
        for key, limit, max_chars in (
            ("key_disconnections", 4, 120),
            ("preferred_precursor_logic", 3, 140),
            ("protect_or_preserve", 3, 120),
            ("mode_evidence", 4, 140),
            ("strategic_risks", 4, 160),
            ("revision_triggers", 4, 160),
        ):
            items = [
                str(item).strip()[:max_chars]
                for item in self._route_plan.get(key, []) or []
                if str(item).strip()
            ][:limit]
            if items:
                brief[key] = items
        terminal_policy = str(self._route_plan.get("terminal_rescue_policy", "")).strip()
        if terminal_policy:
            brief["terminal_rescue_policy"] = terminal_policy[:180]
        reason = str(self._route_plan.get("last_revision_reason", "")).strip()
        if reason:
            brief["last_revision_reason"] = reason[:120]
        return brief

    def _route_plan_provenance(self) -> Dict[str, Any]:
        return {
            "current": dict(self._route_plan) if isinstance(self._route_plan, dict) else {},
            "history": [dict(item) for item in self._route_plan_history if isinstance(item, dict)],
        }

    def _route_plan_items(
        self,
        items: Optional[List[str]],
        *,
        max_items: int = 5,
        max_chars: int = 180,
    ) -> List[str]:
        return [
            self._guidance_summary_text(item, max_chars=max_chars)
            for item in (items or [])
            if str(item).strip()
        ][:max_items]

    def _build_prompt_brief(
        self,
        stage: str,
        *,
        decision_context: Optional[Dict[str, Any]] = None,
        payload: Optional[Dict[str, Any]] = None,
        candidate: Optional[Dict[str, Any]] = None,
        attempt: Optional[Dict[str, Any]] = None,
        attempts: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        brief = build_prompt_brief(
            build_prompt_mount(
                stage,
                decision_context=decision_context,
                payload=payload,
                candidate=candidate,
                attempt=attempt,
                attempts=attempts,
                chemist_guidance=self._chemist_guidance,
                route_plan=self._route_plan_brief(),
                route_strategy=self._route_strategy_brief(),
            )
        )
        return self._attach_rescue_to_prompt_brief(brief)

    def _attach_rescue_to_prompt_brief(self, brief: Dict[str, Any]) -> Dict[str, Any]:
        rescue_brief = self._active_rescue_continuation_brief()
        if rescue_brief:
            brief["rescue_continuation_brief"] = rescue_brief
            brief["rescue_controls"] = {
                "status": "rescue_status()",
                "abort": "rescue_abort(rescue_id, reason)",
            }
            events = brief.setdefault("events", [])
            if "strategy.rescue_continuation_active" not in events:
                events.append("strategy.rescue_continuation_active")
            guardrails = brief.setdefault("quality_guardrails", [])
            rescue_rule = (
                "If strategy continuation is active, resolve that forced precursor review "
                "before accepting the molecule or finalizing the route."
            )
            if rescue_rule not in guardrails:
                guardrails.append(rescue_rule)
            next_step = rescue_brief.get("next_step") or {}
            expected_precursors = list(next_step.get("expected_precursors") or [])
            if (
                "action.intentional_attachment_placeholder" in events
                and expected_precursors
                and all("*" not in str(smiles) for smiles in expected_precursors)
            ):
                completion_rule = (
                    "The system precursor preview still contains an intentional '*' attachment marker. "
                    "Use strategy_continuation_brief.next_step.expected_precursors as the sole executable "
                    "realization for this action; this completes the same system disconnection and is not "
                    "a separate chemistry alternative."
                )
                existing_self_prompt = list(brief.get("self_prompt") or [])
                brief["self_prompt"] = [completion_rule] + existing_self_prompt[1:]
        return brief

    def _context_prompt_brief(self) -> Dict[str, Any]:
        ctx = self.orch._current_context
        return self._build_prompt_brief(
            "context_compact",
            decision_context=ctx.decision_context if ctx else None,
        )

    def _decision_source(self, attempt: Dict[str, Any]) -> str:
        candidate_summary = attempt.get("candidate_summary") or {}
        source = candidate_summary.get("source") or attempt.get("source", "")
        candidate_id = attempt.get("candidate_id", "")
        route_sketch_id = (
            candidate_summary.get("route_sketch_id")
            or attempt.get("route_sketch_id")
            or self._latest_route_sketch_id()
        )
        if route_sketch_id:
            if source == "custom_precursors" or str(candidate_id).startswith("custom:"):
                return "route_sketch_derived_custom"
            return "route_sketch_guided_system_action"
        if not self._chemist_guidance:
            return "llm_selected"
        if source == "custom_precursors" or str(candidate_id).startswith("custom:"):
            return "chemist_directed_custom"
        intents = " ".join(str(item.get("intent", "")) for item in self._chemist_guidance).lower()
        if "approval" in intents or "approve" in intents:
            return "chemist_approved"
        return "chemist_guided"

    def guide(
        self,
        *,
        text: str,
        intent: str = "directive",
        site_hint: str = "",
        reaction_hint: str = "",
        precursors: Optional[List[str]] = None,
        constraints: Optional[List[str]] = None,
        terminal_hint: str = "",
        summary: str = "",
    ) -> Dict[str, Any]:
        """Attach short chemist guidance to the current active node.

        This never changes the route tree or sandbox. Raw text is persisted for
        audit; the default LLM prompt only receives the compact summary.
        """
        ctx = self.orch._current_context
        if ctx is None or ctx.decision_context is None:
            return {"error": "no active context. call next first"}
        raw_text = str(text or "").strip()
        if not raw_text:
            return {"error": "text required"}

        normalized_precursors = [str(item) for item in (precursors or []) if str(item).strip()]
        normalized_constraints = [str(item) for item in (constraints or []) if str(item).strip()]
        guidance_id = f"cg_{uuid.uuid4().hex[:8]}"
        entry = {
            "id": guidance_id,
            "node_id": ctx.node_id,
            "smiles": ctx.smiles,
            "intent": str(intent or "directive").strip() or "directive",
            "summary": self._guidance_summary_text(summary or raw_text),
            "raw_text": raw_text,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        if site_hint:
            entry["site_hint"] = str(site_hint).strip()
        if reaction_hint:
            entry["reaction_hint"] = str(reaction_hint).strip()
        if normalized_precursors:
            entry["precursors"] = normalized_precursors
        if normalized_constraints:
            entry["constraints"] = normalized_constraints
        if terminal_hint:
            entry["terminal_hint"] = str(terminal_hint).strip()

        self._chemist_guidance.append(entry)
        self.save()
        return {
            "ok": True,
            "guidance_id": guidance_id,
            "node_id": ctx.node_id,
            "smiles": ctx.smiles,
            "chemist_guidance": self._guidance_brief(),
            "prompt_brief": self._build_prompt_brief(
                "reaction_sites",
                decision_context=ctx.decision_context,
                payload={"chemist_guidance": self._guidance_brief()},
            ),
            "next_step": "reaction_sites()",
            "hint": "Guidance recorded only. Continue the normal reaction_sites -> explore_site -> try_action loop.",
        }

    def _action_space_summary(self) -> Dict[str, Any]:
        ctx = self.orch._current_context
        decision_context = ctx.decision_context if ctx else {}
        bond_actions = 0
        smart_actions = 0
        for bond in decision_context.get("disconnectable_bonds", []) or []:
            bond_actions += len(bond.get("alternatives", []) or [])
            smart_actions += len(bond.get("smart_capping", []) or [])
        fgi_actions = len(decision_context.get("fgi_options", []) or [])
        custom_actions = len(decision_context.get("custom_candidates", []) or [])
        return {
            "bond_actions": bond_actions,
            "smart_actions": smart_actions,
            "fgi_actions": fgi_actions,
            "custom_actions": custom_actions,
            "total_actions": bond_actions + smart_actions + fgi_actions + custom_actions,
        }

    def route_plan(
        self,
        *,
        route_thesis: str,
        route_mode: str = "",
        key_disconnections: Optional[List[str]] = None,
        preferred_precursor_logic: Optional[List[str]] = None,
        protect_or_preserve: Optional[List[str]] = None,
        mode_evidence: Optional[List[str]] = None,
        strategic_risks: Optional[List[str]] = None,
        revision_triggers: Optional[List[str]] = None,
        terminal_rescue_policy: str = "",
        revision_reason: str = "",
    ) -> Dict[str, Any]:
        """Set or revise the persistent route-level synthesis thesis.

        This is long-lived context. It does not mutate the route tree and does
        not replace route_sketch, which remains a local strategy-to-action
        checkpoint.
        """
        route_thesis = self._guidance_summary_text(route_thesis, max_chars=360)
        if not route_thesis:
            return {"error": "route_thesis required"}

        ctx = self.orch._current_context
        previous_revision = -1
        if self._route_plan:
            try:
                previous_revision = int(self._route_plan.get("revision", -1))
            except (TypeError, ValueError):
                previous_revision = -1
        revision = previous_revision + 1 if previous_revision >= 0 else 0
        plan_id = str(self._route_plan.get("id", "") or f"plan:{self.session_id}").strip()
        reason = self._guidance_summary_text(
            revision_reason or ("initial" if revision == 0 else "revision"),
            max_chars=160,
        )
        entry: Dict[str, Any] = {
            "id": plan_id,
            "revision": revision,
            "route_thesis": route_thesis,
            "route_mode": self._guidance_summary_text(route_mode, max_chars=100),
            "key_disconnections": self._route_plan_items(key_disconnections, max_items=5, max_chars=160),
            "preferred_precursor_logic": self._route_plan_items(preferred_precursor_logic, max_items=4, max_chars=180),
            "protect_or_preserve": self._route_plan_items(protect_or_preserve, max_items=4, max_chars=160),
            "mode_evidence": self._route_plan_items(mode_evidence, max_items=5, max_chars=180),
            "strategic_risks": self._route_plan_items(strategic_risks, max_items=5, max_chars=180),
            "revision_triggers": self._route_plan_items(revision_triggers, max_items=5, max_chars=180),
            "terminal_rescue_policy": self._guidance_summary_text(
                terminal_rescue_policy
                or "Before accepting advanced terminal, attempt a short mechanistic rollback to simpler credible precursors.",
                max_chars=220,
            ),
            "last_revision_reason": reason,
            "node_id": ctx.node_id if ctx else "",
            "smiles": ctx.smiles if ctx else self.orch.tree.target,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        if revision == 0:
            entry["created_at"] = entry["updated_at"]
        else:
            entry["previous_revision"] = previous_revision

        self._route_plan = entry
        self._route_plan_history.append(dict(entry))
        self.orch.audit_state.update_strategic_plan({
            "route_plan": self._route_plan_brief(),
            "active_route_sketch": self._route_strategy_brief(),
            "history_count": len(self._route_plan_history),
        })
        self.save()

        prompt_brief = self._build_prompt_brief(
            "route_plan",
            decision_context=ctx.decision_context if ctx else None,
            payload={"route_plan_updated": True},
        )
        return {
            "ok": True,
            "route_plan": self._route_plan_brief(),
            "route_plan_history_count": len(self._route_plan_history),
            "prompt_brief": prompt_brief,
            "next_step": "reaction_sites()",
            "hint": "Route plan recorded only. Continue the normal site/action/sandbox loop.",
        }

    def route_sketch(
        self,
        *,
        problem: str,
        macro_strategy: str,
        key_disconnections: Optional[List[str]] = None,
        rejected_action_space_reason: str = "",
        next_executable_step: str = "",
        terminal_review: bool = False,
        summary: str = "",
        rescue_steps: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Record a short route sketch for strategy-driven action design.

        The sketch is strategy only. It cannot mutate the route tree and cannot
        bypass propose_action/try_action/sandbox/commit.
        """
        ctx = self.orch._current_context
        if ctx is None or ctx.decision_context is None:
            return {"error": "no active context. call next first"}
        problem = self._guidance_summary_text(problem, max_chars=320)
        macro_strategy = self._guidance_summary_text(macro_strategy, max_chars=320)
        if not problem:
            return {"error": "problem required"}
        if not macro_strategy:
            return {"error": "macro_strategy required"}

        requested_next_step = str(next_executable_step or "propose_action").strip() or "propose_action"
        next_step_aliases = {
            "propose_action": "propose_action",
            "propose_action(...)": "propose_action",
            "explore_site": "explore_site",
            "explore_site(site_id)": "explore_site",
            "try_action": "try_action",
            "try_action(action_id)": "try_action",
            "try_existing_action": "try_action",
            "reaction_sites": "reaction_sites",
            "reaction_sites()": "reaction_sites",
        }
        next_step_hints = {
            "propose_action": "propose_action(...)",
            "explore_site": "explore_site(site_id)",
            "try_action": "try_action(action_id)",
            "reaction_sites": "reaction_sites()",
        }
        next_step = next_step_aliases.get(requested_next_step.lower())
        if next_step is None:
            return {
                "error": "invalid_next_executable_step",
                "next_executable_step": requested_next_step,
                "allowed_next_executable_steps": sorted(next_step_hints),
                "hint": (
                    "route_sketch records strategy only. For terminal review, use "
                    "next_executable_step='propose_action'; then call accept separately with "
                    "force_accept_without_rescue and rescue_not_actionable_reason only if no "
                    "executable next action can be defined."
                ),
            }
        disconnections = [
            self._guidance_summary_text(item, max_chars=180)
            for item in (key_disconnections or [])
            if str(item).strip()
        ][:6]
        sketch_id = f"sketch:{ctx.node_id}:{len(self._route_sketches)}"
        entry: Dict[str, Any] = {
            "id": sketch_id,
            "node_id": ctx.node_id,
            "smiles": ctx.smiles,
            "problem": problem,
            "macro_strategy": macro_strategy,
            "key_disconnections": disconnections,
            "rejected_action_space_reason": self._guidance_summary_text(
                rejected_action_space_reason,
                max_chars=320,
            ),
            "next_executable_step": next_step,
            "terminal_review": bool(terminal_review),
            "action_space_summary": self._action_space_summary(),
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        if summary:
            entry["summary"] = self._guidance_summary_text(summary, max_chars=240)
        normalized_rescue_steps = self._normalize_rescue_steps(rescue_steps)
        if normalized_rescue_steps:
            entry["rescue_steps"] = normalized_rescue_steps

        self._route_sketches.append(entry)
        self.orch.audit_state.update_strategic_plan({
            "route_plan": self._route_plan_brief(),
            "active_route_sketch": self._route_strategy_brief(),
            "problem": problem,
            "next_executable_step": next_step,
        })
        self.save()
        prompt_brief = self._build_prompt_brief(
            "route_sketch",
            decision_context=ctx.decision_context,
            payload={
                "route_strategy_brief": self._route_strategy_brief(),
                "action_space_summary": entry["action_space_summary"],
                "terminal_review": bool(terminal_review),
            },
        )
        next_hint = next_step_hints[next_step]
        return {
            "ok": True,
            "route_sketch_id": sketch_id,
            "node_id": ctx.node_id,
            "smiles": ctx.smiles,
            "route_strategy_brief": self._route_strategy_brief(),
            "prompt_brief": prompt_brief,
            "next_step": next_hint,
            "hint": "Strategy recorded only. Convert exactly one next chemical event through the normal action/sandbox flow.",
        }

    def _attempt_summary(self, attempt: Dict[str, Any]) -> Dict[str, Any]:
        fv = attempt.get("forward_validation") or {}
        validation_gate = fv.get("gate") or {}
        summary = {
            "attempt_idx": attempt.get("attempt_idx"),
            "candidate_id": attempt.get("candidate_id", ""),
            "candidate_label": (attempt.get("candidate_summary") or {}).get("candidate_label", ""),
            "source": attempt.get("source", ""),
            "success": bool(attempt.get("success", False)),
            "precursors": list(attempt.get("precursors", []) or []),
            "reagents": list(attempt.get("reagents", []) or []),
            "reaction_type": attempt.get("reaction_type", ""),
            "template_id": attempt.get("template_id", ""),
            "template_name": attempt.get("template_name", ""),
            "forward_pass": fv.get("pass"),
            "validation_gate_state": validation_gate.get("gate_state", ""),
            "validation_micro": attempt.get("validation_micro", {}),
            "risk_tags": (attempt.get("candidate_summary") or {}).get("risk_tags", []),
            "precursor_normalization": attempt.get("precursor_normalization"),
            "why_existing_candidates_rejected": (
                attempt.get("candidate_summary") or {}
            ).get("why_existing_candidates_rejected", ""),
            "rationale_summary": (attempt.get("candidate_summary") or {}).get("rationale_summary", ""),
            "duplicate_of": (attempt.get("candidate_summary") or {}).get("duplicate_of", ""),
            "error": attempt.get("error", ""),
        }
        if attempt.get("strategy_id"):
            summary["strategy_id"] = attempt.get("strategy_id", "")
        if validation_gate:
            summary["validation_gate"] = {
                "gate_state": validation_gate.get("gate_state", ""),
                "commit_policy": validation_gate.get("commit_policy", ""),
                "hard_blocks": [
                    item.get("code", "")
                    for item in validation_gate.get("hard_blocks", []) or []
                ],
                "override_allowed": [
                    item.get("code", "")
                    for item in validation_gate.get("override_allowed", []) or []
                ],
                "missing_evidence": [
                    item.get("code", "")
                    for item in validation_gate.get("missing_evidence", []) or []
                ],
            }
        route_sketch_id = (
            (attempt.get("candidate_summary") or {}).get("route_sketch_id")
            or attempt.get("route_sketch_id", "")
        )
        if route_sketch_id:
            summary["route_sketch_id"] = route_sketch_id
        candidate_summary = attempt.get("candidate_summary") or {}
        if candidate_summary.get("rescue_id") or attempt.get("rescue_id"):
            summary["rescue_id"] = candidate_summary.get("rescue_id") or attempt.get("rescue_id")
        if candidate_summary.get("rescue_step_idx") is not None:
            summary["rescue_step_idx"] = candidate_summary.get("rescue_step_idx")
        if candidate_summary.get("continuation_precursor"):
            summary["continuation_precursor"] = candidate_summary.get("continuation_precursor")
        prompt_brief = attempt.get("prompt_brief") or {}
        if prompt_brief.get("active_experience_card_ids"):
            summary["active_experience_card_ids"] = list(prompt_brief["active_experience_card_ids"])
        return summary

    def _compact_validation_gate(self, attempt: Dict[str, Any]) -> Dict[str, Any]:
        gate = (attempt.get("forward_validation") or {}).get("gate") or {}
        row = {
            "state": gate.get("gate_state", ""),
            "hard_blocks": [
                item.get("code", "")
                for item in gate.get("hard_blocks", []) or []
                if item.get("code")
            ],
            "override_allowed": [
                item.get("code", "")
                for item in gate.get("override_allowed", []) or []
                if item.get("code")
            ],
            "missing_evidence": [
                item.get("code", "")
                for item in gate.get("missing_evidence", []) or []
                if item.get("code")
            ],
        }
        policy_adjustments = [
            {
                "family_key": item.get("family_key", ""),
                "applied_downgrade_codes": list(item.get("applied_downgrade_codes", []) or []),
            }
            for item in gate.get("policy_adjustments", []) or []
            if item.get("applied_downgrade_codes")
        ]
        if policy_adjustments:
            row["policy_adjustments"] = policy_adjustments
        return row

    def _sandbox_summary(self) -> Dict[str, Any]:
        gate_states: Dict[str, int] = {}
        success_count = 0
        failure_count = 0
        for attempt in self._sandbox_attempts:
            if attempt.get("success"):
                success_count += 1
            else:
                failure_count += 1
            state = self._compact_validation_gate(attempt).get("state") or "not_available"
            gate_states[state] = gate_states.get(state, 0) + 1
        return {
            "n_attempts": len(self._sandbox_attempts),
            "selected": self._sandbox_selected,
            "success_count": success_count,
            "failure_count": failure_count,
            "gate_states": gate_states,
            "command": "sandbox_list",
        }

    def _record_gate_failed_attempt(
        self,
        attempt: Dict[str, Any],
        *,
        reason: str,
        reasoning: str,
        confidence: str,
    ) -> None:
        """Persist gate failures without destroying the active sandbox context."""
        ctx = self.orch._current_context
        molecule = ctx.smiles if ctx else ""
        reaction_name = (
            attempt.get("template_name")
            or attempt.get("reaction_type")
            or attempt.get("source")
            or "llm_proposed"
        )
        self.orch.audit_state.record_failure(
            molecule,
            reaction_name,
            reason,
        )
        self.orch.audit_state.record_decision(
            step_id="",
            molecule=molecule,
            action="commit",
            reaction_name=reaction_name,
            reasoning_summary=reasoning or reason,
            outcome="gate_failed",
            confidence=confidence,
        )

    def _evaluate_validation_gate(
        self,
        attempt: Dict[str, Any],
        *,
        validation_override: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Apply forward-validation gate semantics before committing."""
        fv_raw = attempt.get("forward_validation")
        fv = fv_raw if isinstance(fv_raw, dict) else {}
        gate = fv.get("gate") or {}
        if not gate:
            missing_gate = {
                "gate_state": "hard_block",
                "commit_policy": "block",
                "hard_blocks": [
                    {
                        "code": "validation_gate_missing",
                        "category": "validation",
                        "message": "successful sandbox attempt has no forward_validation.gate",
                    }
                ],
                "soft_warnings": [],
                "override_allowed": [],
                "missing_evidence": [],
                "llm_override_allowed": False,
                "recommended_action": "Rerun try_action to obtain a validation gate before commit.",
            }
            return {
                "error": "validation gate missing; commit blocked",
                "gate_failed": True,
                "gate_reason": "validation_missing_gate",
                "validation_gate": missing_gate,
                "validation_override": validation_override or {},
            }

        gate_state = str(gate.get("gate_state", "") or "")
        if gate_state == "hard_block":
            return {
                "error": "validation gate hard-blocked commit",
                "gate_failed": True,
                "gate_reason": "validation_hard_block",
                "validation_gate": gate,
                "validation_override": validation_override or {},
            }

        if gate_state != "override_required":
            return None

        override = validation_override or {}
        reason = str(override.get("reason", "") or "").strip()
        if override.get("allowed") is True and reason:
            return None

        return {
            "error": (
                "validation gate requires explicit override: provide "
                "validation_override={allowed: true, reason: ..., evidence: ...}"
            ),
            "gate_failed": True,
            "gate_reason": "validation_override_required",
            "validation_gate": gate,
            "validation_override": override,
        }

    def _evaluate_site_retention_gate(
        self,
        attempt: Dict[str, Any],
        *,
        reasoning: str,
        validation_override: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Require proof for unresolved strict same-core site-fidelity audits."""
        if attempt.get("source") != "llm_proposed":
            return None

        site_audit = attempt.get("site_audit") or {}
        validation_micro = attempt.get("validation_micro") or {}
        site_retentive = bool(site_audit.get("site_retentive"))
        strict_audit_required = bool(site_audit.get("strict_audit_required"))
        site_summary = str(site_audit.get("summary", "") or "")
        site_rows = site_audit.get("site_rows")
        changed_sites = site_audit.get("changed_sites")
        preserved_sites = site_audit.get("preserved_sites")
        changed_site_count = site_audit.get("changed_site_count")

        if reasoning_claims_site_retention(reasoning) and not site_summary:
            return {
                "error": (
                    "site-retention gate blocked commit: reasoning claimed same-site rollback "
                    "but no explicit site audit summary was available."
                ),
                "gate_failed": True,
                "gate_reason": "missing_explicit_site_audit",
                "site_audit": site_audit,
                "validation_micro": validation_micro,
            }

        if not site_retentive or not strict_audit_required:
            return None

        override = validation_override or {}
        override_reason = str(override.get("reason", "") or "").strip()

        def proof_required(code: str, message: str) -> Optional[Dict[str, Any]]:
            if override.get("allowed") is True and override_reason:
                return None
            gate = {
                "gate_state": "override_required",
                "commit_policy": "requires_override",
                "hard_blocks": [],
                "soft_warnings": [],
                "override_allowed": [
                    {
                        "code": code,
                        "source": "site_fidelity",
                        "message": message,
                        "evidence": {
                            "summary": site_summary,
                            "changed_site_count": changed_site_count,
                        },
                    }
                ],
                "missing_evidence": [],
                "llm_override_allowed": True,
                "recommended_action": (
                    "Treat this as a site-fidelity proof obligation: revise the precursor map "
                    "or provide independent substituent-position evidence before commit."
                ),
            }
            return {
                "error": message,
                "gate_failed": True,
                "gate_reason": "site_fidelity_proof_required",
                "validation_gate": gate,
                "validation_override": override,
                "site_audit": site_audit,
                "validation_micro": validation_micro,
            }

        if not site_summary:
            return proof_required(
                "site_mapping_summary_missing",
                "Strict same-core site mapping did not produce an audit summary.",
            )

        if not isinstance(site_rows, list) or not site_rows:
            return proof_required(
                "site_mapping_rows_unavailable",
                "Strict same-core site mapping is unavailable; revise the precursor map or provide independent position evidence.",
            )

        if not isinstance(changed_sites, list) or not isinstance(preserved_sites, list):
            return proof_required(
                "site_mapping_details_unavailable",
                "Strict same-core site mapping lacks changed/preserved site details.",
            )

        try:
            changed_site_count_int = int(changed_site_count)
        except (TypeError, ValueError):
            return proof_required(
                "site_change_count_unavailable",
                "Strict same-core site mapping did not produce a usable changed-site count.",
            )

        if len(changed_sites) != changed_site_count_int:
            return proof_required(
                "site_mapping_count_inconsistent",
                "Strict same-core site mapping has inconsistent site-count details.",
            )

        if not bool(site_audit.get("pass", False)):
            return proof_required(
                "multiple_scaffold_sites_changed_requires_evidence",
                "Multiple scaffold attachment sites changed in the heuristic site map; provide independent position evidence or revise the precursor.",
            )

        if changed_site_count_int > 1:
            return proof_required(
                "multiple_scaffold_sites_changed_requires_evidence",
                "Multiple scaffold attachment sites changed in the heuristic site map; provide independent position evidence or revise the precursor.",
            )

        # Historical scaffold-alignment hard gate kept as comments instead of deleting it.
        # Reason: scaffold_alignment is useful global MCS telemetry, but it is not a
        # bond/site-specific audit and was blocking chemically valid same-site rollbacks.
        # template_attempted = validation_micro.get("template_attempted")
        # scaffold_alignment = float(validation_micro.get("scaffold_alignment", 1.0))
        # if template_attempted is False and scaffold_alignment < 1.0:
        #     return {
        #         "error": (
        #             "site-retention gate blocked commit: template_execution.attempted=false "
        #             f"and scaffold_alignment={scaffold_alignment:.3f} < 1.0 for a same-core proposal."
        #         ),
        #         "gate_failed": True,
        #         "gate_reason": "scaffold_alignment_below_1_for_same_core",
        #         "site_audit": site_audit,
        #         "validation_micro": validation_micro,
        #     }

        return None

    # ── 工厂方法 ──

    @classmethod
    def create(
        cls,
        target_smiles: str,
        session_path: str = ".rachel_session.json",
        target_name: str = "",
        *,
        max_depth: int = 15,
        max_steps: int = 50,
        terminal_cs_threshold: float = CS_TRIVIAL,
    ) -> RetroSession:
        """创建新会话。"""
        orch = RetrosynthesisOrchestrator(
            target_smiles,
            target_name=target_name,
            max_depth=max_depth,
            max_steps=max_steps,
            terminal_cs_threshold=terminal_cs_threshold,
        )
        session = cls(orch, session_path)
        session.save()
        return session

    @classmethod
    def load(cls, session_path: str) -> RetroSession:
        """从 JSON 文件恢复会话。"""
        path = Path(session_path)
        if not path.exists():
            raise FileNotFoundError(f"Session file not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 重建 orchestrator
        config = data.get("config", {})
        target = data.get("target", {})

        orch = RetrosynthesisOrchestrator(
            target["smiles"],
            target_name=target.get("name", ""),
            max_depth=config.get("max_depth", 15),
            max_steps=config.get("max_steps", 50),
            terminal_cs_threshold=config.get("terminal_cs_threshold", CS_TRIVIAL),
        )

        # 恢复树
        if "tree" in data:
            orch.tree = RetrosynthesisTree.from_dict(data["tree"])

        # 恢复审计状态
        if "audit_state" in data:
            orch.audit_state = SynthesisAuditState.from_dict(data["audit_state"])

        # 恢复队列
        from collections import deque
        orch._queue = deque()
        for item in data.get("queue", []):
            orch._queue.append(tuple(item))

        # 恢复计数器
        status = data.get("status", {})
        orch._steps_executed = status.get("steps_executed", 0)

        # 恢复 seen 集合
        orch._seen = set(data.get("seen_smiles", []))

        session = cls(
            orch, session_path,
            session_id=data.get("session_id", ""),
        )

        # 恢复 sandbox
        current = data.get("current") or {}
        sandbox = current.get("sandbox") or {}
        session._sandbox_attempts = sandbox.get("attempts", [])
        session._sandbox_selected = sandbox.get("selected")
        guidance = current.get("chemist_guidance") or []
        session._chemist_guidance = guidance if isinstance(guidance, list) else []
        route_sketches = current.get("route_sketches") or []
        session._route_sketches = route_sketches if isinstance(route_sketches, list) else []
        if not session._route_sketches:
            session._clear_route_sketch_state()
        route_plan_state = data.get("route_plan") or {}
        if isinstance(route_plan_state, dict):
            route_plan_current = route_plan_state.get("current") or {}
            route_plan_history = route_plan_state.get("history") or []
            session._route_plan = route_plan_current if isinstance(route_plan_current, dict) else {}
            session._route_plan_history = route_plan_history if isinstance(route_plan_history, list) else []
        elif isinstance(route_plan_state, list):
            session._route_plan_history = route_plan_state
            session._route_plan = route_plan_state[-1] if route_plan_state else {}
        rescue_continuations = data.get("rescue_continuations") or []
        session._rescue_continuations = (
            rescue_continuations if isinstance(rescue_continuations, list) else []
        )
        for item in session._pending_rescue_continuations():
            focus = item.get("focus_smiles", "")
            if focus:
                orch._force_standard_smiles.add(focus)
        orch._force_standard_smiles.update(
            data.get("force_standard_smiles", []) or []
        )

        # 恢复 _current_context（关键：让 explore/try_* 跨进程可用）
        if current and current.get("decision_tier") == "standard":
            cur_smiles = current.get("smiles", "")
            cur_depth = current.get("depth", 0)
            if cur_smiles:
                # 重新生成 decision_context（包含完整断键方案）
                decision_ctx = build_decision_context(cur_smiles)
                if current.get("custom_candidates"):
                    decision_ctx["custom_candidates"] = current.get("custom_candidates", [])

                node = orch.tree.get_molecule_by_smiles(cur_smiles)
                is_target = (node.role == MoleculeRole.TARGET.value) if node else False

                ctx = ProposalContext(
                    smiles=cur_smiles,
                    node_id=current.get("node_id", node.node_id if node else ""),
                    depth=cur_depth,
                    cs_score=current.get("cs_score", 0),
                    classification=current.get("classification", ""),
                    is_terminal=current.get("is_terminal", False),
                    is_target=is_target,
                    depth_limited=cur_depth > config.get("max_depth", 15),
                    decision_context=decision_ctx,
                    seen_smiles=set(data.get("seen_smiles", [])),
                    steps_executed=status.get("steps_executed", 0),
                    steps_remaining=max(0, config.get("max_steps", 50) - status.get("steps_executed", 0)),
                    audit_state_summary=orch.audit_state.get_summary(),
                    failed_attempts_for_current=orch.audit_state.get_failures_for_molecule(cur_smiles),
                    decision_tier="standard",
                )
                orch._current_context = ctx

        if (
            orch.tree.status == TreeStatus.COMPLETE.value
            and not orch.tree.is_complete()
        ):
            orch.tree.reopen()

        return session

    # ── 序列化 ──

    def to_dict(self) -> Dict[str, Any]:
        """导出完整会话状态。"""
        orch = self.orch
        target_node = orch.tree.get_molecule_by_smiles(orch.tree.target)

        data: Dict[str, Any] = {
            "session_id": self.session_id,
            "target": {
                "smiles": orch.tree.target,
                "name": orch.tree.target_name,
                "cs_score": target_node.cs_score if target_node else 0,
            },
            "config": {
                "max_depth": orch.max_depth,
                "max_steps": orch.max_steps,
                "max_queue_size": orch.max_queue_size,
                "terminal_cs_threshold": orch.terminal_cs_threshold,
                "auto_forward_validate": orch.auto_forward_validate,
            },
            "status": self.get_status(),
        }
        if self._route_plan or self._route_plan_history:
            data["route_plan"] = self._route_plan_provenance()
        if self._rescue_continuations:
            data["rescue_continuations"] = [
                dict(item)
                for item in self._rescue_continuations
                if isinstance(item, dict)
            ]
        if orch._force_standard_smiles:
            data["force_standard_smiles"] = sorted(orch._force_standard_smiles)

        # 当前工作区
        ctx = orch._current_context
        if ctx and ctx.decision_tier != "quick_pass":
            # Historical manual session-current builder kept as comments instead of
            # being deleted. Reason: session.json should now persist the exact default
            # compact contract returned by next/context(compact), rather than a wider
            # hand-built variant that drifted from live output.
            # current = {
            #     "smiles": ctx.smiles,
            #     "node_id": ctx.node_id,
            #     ...
            # }
            # if ctx.decision_context:
            #     ...
            current = ctx.to_dict(
                detail="compact",
                bond_offset=0,
                bond_limit=5,
                fgi_offset=0,
                fgi_limit=5,
            )

            # 沙盒
            if ctx.decision_context and ctx.decision_context.get("custom_candidates"):
                current["custom_candidates"] = ctx.decision_context.get("custom_candidates", [])

            current["prompt_brief"] = self._context_prompt_brief()
            if self._route_plan:
                current["route_plan_brief"] = self._route_plan_brief()
            if self._chemist_guidance:
                current["chemist_guidance"] = self._guidance_provenance()
            if self._route_sketches:
                current["route_sketches"] = self._route_sketch_provenance()
            rescue_brief = self._active_rescue_continuation_brief()
            if rescue_brief:
                self._attach_rescue_affordances(current, rescue_brief)

            current["sandbox"] = {
                "attempts": self._sandbox_attempts,
                "selected": self._sandbox_selected,
                "n_attempts": len(self._sandbox_attempts),
            }

            data["current"] = current
        elif ctx and ctx.decision_tier == "quick_pass":
            data["current"] = {
                "smiles": ctx.smiles,
                "cs_score": ctx.cs_score,
                "decision_tier": "quick_pass",
                "hint": "terminal 分子，直接 accept_terminal",
            }
        else:
            data["current"] = None

        # 队列
        data["queue"] = list(orch._queue)
        data["seen_smiles"] = sorted(orch._seen)

        # 树和审计状态
        data["tree"] = orch.tree.to_dict()
        data["audit_state"] = orch.audit_state.to_dict()

        return data

    def save(self) -> Path:
        """保存到 JSON 文件。"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = self.to_dict()
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return self.path

    # ── LLM 上下文输出（分层） ──

    def get_context(
        self,
        detail: str = "compact",
        *,
        bond_offset: int = 0,
        bond_limit: Optional[int] = None,
        fgi_offset: int = 0,
        fgi_limit: int = 5,
    ) -> Dict[str, Any]:
        """获取 LLM 决策上下文。

        detail:
          "status"  — 只看状态（最省 token）
          "compact" — 当前分子 + 键位概览 + 沙盒历史
          "full"    — 包含完整断键方案（慎用）
          "tree"    — 包含完整树（调试用）
        """
        ctx = self.orch._current_context
        if ctx is None:
            return {
                "status": self.orch.get_status(),
                "current": None,
                "hint": "调用 prepare_next() 获取下一个分子",
            }

        if detail == "status":
            return {"status": self.orch.get_status()}

        result: Dict[str, Any] = {
            "status": self.orch.get_status(),
            "current": ctx.to_dict(
                detail=detail,
                bond_offset=bond_offset,
                bond_limit=bond_limit,
                fgi_offset=fgi_offset,
                fgi_limit=fgi_limit,
            ),
        }
        if isinstance(result.get("current"), dict):
            result["current"]["prompt_brief"] = self._context_prompt_brief()
            if self._route_plan:
                result["current"]["route_plan_brief"] = self._route_plan_brief()
            if self._chemist_guidance:
                result["current"]["chemist_guidance"] = self._guidance_brief()
            if self._route_sketches:
                result["current"]["route_strategy_brief"] = self._route_strategy_brief()
            rescue_brief = self._active_rescue_continuation_brief()
            if rescue_brief:
                self._attach_rescue_affordances(result["current"], rescue_brief)

        # 附加沙盒历史
        if self._sandbox_attempts:
            result["sandbox_summary"] = self._sandbox_summary()
            if detail != "compact":
                result["sandbox_history"] = {
                    "n_attempts": len(self._sandbox_attempts),
                    "attempts": self._sandbox_attempts,
                    "selected": self._sandbox_selected,
                }

        if detail == "tree":
            result["tree_text"] = self.orch.tree.print_tree()

        return result

    # ── 编排操作（自动保存） ──

    def prepare_next(self) -> Optional[Dict[str, Any]]:
        """取下一个分子，返回精简上下文 dict。自动保存。"""
        self._archive_sandbox("prepare_next", selected_idx=self._sandbox_selected)
        self._sandbox_attempts = []
        self._sandbox_selected = None
        self._chemist_guidance = []
        self._clear_route_sketch_state()
        self._prioritize_pending_rescue()

        ctx = self.orch.prepare_next()
        if ctx is None:
            self.save()
            return None

        # quick_pass 自动处理
        if ctx.decision_tier == "quick_pass":
            result = {
                "action": "auto_terminal",
                "smiles": ctx.smiles,
                "cs_score": ctx.cs_score,
                "classification": ctx.classification,
            }
            self.orch.accept_terminal(reason="quick_pass")
            self.save()
            return result

        self.save()
        return self.get_context("compact")

    def explore_bond(self, bond_idx: int) -> Dict[str, Any]:
        """按需展开键位详情。不保存（只读操作）。"""
        return self.orch.explore_bond(bond_idx)

    def explore_fgi(self) -> Dict[str, Any]:
        """按需展开 FGI 详情。不保存。"""
        return self.orch.explore_fgi()

    def explore_reaction(self, reaction_id: str) -> Dict[str, Any]:
        """按具体 reaction family 展开模板/候选详情。不保存。"""
        return self.orch.explore_reaction(reaction_id)

    def reaction_sites(self) -> Dict[str, Any]:
        """Return the complete first-layer site/reaction menu."""
        result = self.orch.reaction_sites()
        ctx = self.orch._current_context
        if "error" not in result:
            result["prompt_brief"] = self._build_prompt_brief(
                "reaction_sites",
                decision_context=ctx.decision_context if ctx else None,
                payload={"site_reaction_map": result.get("site_reaction_map", [])},
            )
        return result

    def explore_site(self, site_id: str) -> Dict[str, Any]:
        """Expand all normalized candidates competing at one real reaction site."""
        result = self.orch.explore_site(site_id)
        if "error" not in result:
            prompt_payload = {key: value for key, value in result.items() if key != "prompt_brief"}
            result["prompt_brief"] = self._build_prompt_brief(
                "explore_site",
                payload=prompt_payload,
            )
        return result

    def propose_candidate(
        self,
        *,
        precursors: List[str],
        reagents: Optional[List[str]] = None,
        strategy_id: str = "",
        reaction_type: str = "",
        reaction_id: str = "",
        reaction_name: str = "",
        candidate_label: str = "",
        why_existing_candidates_rejected: str = "",
        rationale_summary: str = "",
        route_sketch_id: str = "",
        rescue_id: str = "",
        rescue_step_idx: Optional[int] = None,
        continuation_precursor: str = "",
        risk_tags: Optional[List[str]] = None,
        intended_deltas: Optional[List[str]] = None,
        expected_ring_change: str = "",
        changed_bonds: Optional[List[Dict[str, Any]]] = None,
        preserved_anchors: Optional[List[Any]] = None,
        mechanistic_evidence: Optional[List[str]] = None,
        family_evidence: Optional[Dict[str, Any]] = None,
        experience_card_hints: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Register an LLM-proposed precursor set as a normal strategy candidate."""
        ctx = self.orch._current_context
        if ctx is None or ctx.decision_context is None:
            return {"error": "no active context"}

        strategy_id = str(strategy_id or "").strip()
        strategy_slug = self._custom_candidate_role_slug(strategy_id)
        if not precursors:
            return {"error": "precursors list required"}
        reaction_name = reaction_name or reaction_type or "llm_proposed"
        reaction_type = reaction_type or reaction_name

        preflight = normalize_precursor_set(precursors)
        normalized_precursors = list(preflight.get("precursors", []) or [])
        invalid_precursors = list(preflight.get("invalid", []) or [])
        precursor_normalization = None
        if preflight.get("normalizations"):
            precursor_normalization = {
                "original_precursors": list(precursors),
                "normalized_precursors": normalized_precursors,
                "normalizations": list(preflight.get("normalizations", []) or []),
                "invalid": invalid_precursors,
                "changed": bool(preflight.get("changed", False)),
            }
        if invalid_precursors:
            detail = "; ".join(
                f"{item.get('smiles', '')} ({item.get('reason', '')})"
                for item in invalid_precursors
            )
            return {
                "error": f"invalid precursor SMILES after preflight: {detail}",
                "precursor_normalization": precursor_normalization,
            }
        if not normalized_precursors:
            return {"error": "no valid precursors after normalization"}

        # 试剂/条件宽松归一化：催化剂/碱/溶剂/温度常以名称或缩写给出(CuI/K2CO3/DMF/heat)，
        # 本就不是 SMILES——分子试剂进 forward validation，其余按 free-text 条件保留，不丢弃 proposal。
        reagent_norm = normalize_reagent_set(reagents)
        normalized_reagents = reagent_norm["reagents"]
        condition_reagents = reagent_norm["conditions"]

        duplicate_of = self._find_duplicate_candidate(
            normalized_precursors,
            reagents=normalized_reagents,
        )
        merged_risk_tags = list(risk_tags or [])
        active_rescue = self._active_rescue_continuation_brief()
        linked_route_sketch_id = str(
            route_sketch_id
            or active_rescue.get("route_sketch_id", "")
            or self._latest_route_sketch_id()
        ).strip()
        linked_rescue_id = str(rescue_id or active_rescue.get("id", "")).strip()
        if rescue_step_idx is None and active_rescue.get("next_step"):
            try:
                rescue_step_idx = int(active_rescue["next_step"].get("step_idx"))
            except (TypeError, ValueError):
                rescue_step_idx = None
        if linked_route_sketch_id and "route_sketch_derived" not in merged_risk_tags:
            merged_risk_tags.append("route_sketch_derived")
        if linked_rescue_id and "rescue_continuation" not in merged_risk_tags:
            merged_risk_tags.append("rescue_continuation")
        if duplicate_of and "duplicates_existing_candidate" not in merged_risk_tags:
            merged_risk_tags.append("duplicates_existing_candidate")

        custom_candidates = ctx.decision_context.setdefault("custom_candidates", [])
        custom_idx = len(custom_candidates)
        candidate_id = f"custom:{strategy_slug}:{custom_idx}"
        entry = {
            "candidate_id": candidate_id,
            "source": "custom_precursors",
            "source_label": f"custom[{strategy_slug}:{custom_idx}]",
            "candidate_label": candidate_label or f"custom candidate {custom_idx}",
            "precursors": normalized_precursors,
            "reagents": normalized_reagents,
            "reaction_type": reaction_type,
            "reaction_name": reaction_name,
            "why_existing_candidates_rejected": why_existing_candidates_rejected,
            "rationale_summary": rationale_summary,
            "risk_tags": merged_risk_tags,
        }
        if precursor_normalization:
            entry["precursor_normalization"] = precursor_normalization
            if "organometallic_source_obligation" not in merged_risk_tags:
                merged_risk_tags.append("organometallic_source_obligation")
            entry["risk_tags"] = merged_risk_tags
        entry.update(_copy_validation_intent({
            "intended_deltas": list(intended_deltas or []),
            "expected_ring_change": expected_ring_change,
            "changed_bonds": list(changed_bonds or []),
            "preserved_anchors": list(preserved_anchors or []),
            "mechanistic_evidence": list(mechanistic_evidence or []),
            "family_evidence": dict(family_evidence or {}),
            "rationale_summary": rationale_summary,
        }))
        if strategy_id:
            entry["strategy_id"] = strategy_id
        if experience_card_hints:
            entry["experience_card_hints"] = list(experience_card_hints)
        if reaction_id:
            entry["reaction_id"] = reaction_id
        if linked_route_sketch_id:
            entry["route_sketch_id"] = linked_route_sketch_id
            entry["route_strategy_brief"] = self._route_strategy_brief()
        if linked_rescue_id:
            entry["rescue_id"] = linked_rescue_id
        if rescue_step_idx is not None:
            entry["rescue_step_idx"] = int(rescue_step_idx)
        continuation_can = self._canonical_smiles_text(continuation_precursor)
        if continuation_can:
            entry["continuation_precursor"] = continuation_can
        if duplicate_of:
            entry["duplicate_of"] = duplicate_of
            entry["duplicate_warning"] = (
                "custom candidate has the same canonical precursor set as an existing candidate"
            )
        if condition_reagents:
            entry["reagent_conditions"] = condition_reagents
        custom_candidates.append(entry)
        self.save()
        prompt_mount = build_prompt_mount(
            "propose_action",
            decision_context=ctx.decision_context,
            payload=entry,
            candidate=entry,
            chemist_guidance=self._chemist_guidance,
            route_plan=self._route_plan_brief(),
            route_strategy=self._route_strategy_brief(),
        )
        prompt_brief = self._attach_rescue_to_prompt_brief(build_prompt_brief(prompt_mount))
        return {
            **entry,
            "hint": "Registered only. Use try_action(action_id) to sandbox this custom precursor set.",
            "prompt_brief": prompt_brief,
        }

    def propose_action(
        self,
        *,
        precursors: List[str],
        reagents: Optional[List[str]] = None,
        strategy_id: str = "",
        reaction_type: str = "",
        reaction_id: str = "",
        reaction_name: str = "",
        action_label: str = "",
        why_existing_actions_rejected: str = "",
        rationale_summary: str = "",
        route_sketch_id: str = "",
        rescue_id: str = "",
        rescue_step_idx: Optional[int] = None,
        continuation_precursor: str = "",
        risk_tags: Optional[List[str]] = None,
        intended_deltas: Optional[List[str]] = None,
        expected_ring_change: str = "",
        changed_bonds: Optional[List[Dict[str, Any]]] = None,
        preserved_anchors: Optional[List[Any]] = None,
        mechanistic_evidence: Optional[List[str]] = None,
        family_evidence: Optional[Dict[str, Any]] = None,
        experience_card_hints: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Register an LLM-proposed precursor set as a public action."""
        result = self.propose_candidate(
            strategy_id=strategy_id,
            precursors=precursors,
            reagents=reagents,
            reaction_type=reaction_type,
            reaction_id=reaction_id,
            reaction_name=reaction_name,
            candidate_label=action_label,
            why_existing_candidates_rejected=why_existing_actions_rejected,
            rationale_summary=rationale_summary,
            route_sketch_id=route_sketch_id,
            rescue_id=rescue_id,
            rescue_step_idx=rescue_step_idx,
            continuation_precursor=continuation_precursor,
            risk_tags=risk_tags,
            intended_deltas=intended_deltas,
            expected_ring_change=expected_ring_change,
            changed_bonds=changed_bonds,
            preserved_anchors=preserved_anchors,
            mechanistic_evidence=mechanistic_evidence,
            family_evidence=family_evidence,
            experience_card_hints=experience_card_hints,
        )
        return _action_facing_payload(result)

    def sandbox_try(
        self,
        *,
        bond_idx: int = -1,
        alt_idx: int = 0,
        fgi_idx: int = -1,
        precursors: Optional[List[str]] = None,
        reaction_type: str = "",
        candidate_id: str = "",
        candidate_meta: Optional[Dict[str, Any]] = None,
        template_id: str = "",
        allow_template_fallback: bool = True,
    ) -> Dict[str, Any]:
        """统一沙盒试探入口。结果追加到 sandbox.attempts，自动保存。

        三种模式:
          precursors=[...]           → LLM 自提前体
          bond_idx=0, alt_idx=0      → 试断键
          fgi_idx=0                  → 试 FGI
        """
        sb: SandboxResult
        action_context: Optional[Dict[str, Any]] = None
        if candidate_meta:
            action_context = {
                "source": candidate_meta.get("source", ""),
                "source_label": candidate_meta.get("source_label", ""),
                "action_id": candidate_id or candidate_meta.get("candidate_id", ""),
                "candidate_id": candidate_meta.get("candidate_id", candidate_id),
                "reaction_type": candidate_meta.get("reaction_type", ""),
                "template_id": candidate_meta.get("template_id", ""),
                "template_name": candidate_meta.get("template_name", ""),
                "bond_idx": candidate_meta.get("bond_idx"),
                "alt_idx": candidate_meta.get("alt_idx"),
                "fgi_idx": candidate_meta.get("fgi_idx"),
                "smart_idx": candidate_meta.get("smart_idx"),
                "actual_bond_idx": candidate_meta.get("actual_bond_idx"),
                "atoms": list(candidate_meta.get("atoms", []) or []),
                "bond_type": candidate_meta.get("bond_type", ""),
                "risk_tags": list(candidate_meta.get("risk_tags", []) or []),
                "precursor_normalization": candidate_meta.get("precursor_normalization"),
            }
            if "in_ring" in candidate_meta:
                action_context["in_ring"] = bool(candidate_meta.get("in_ring", False))
            action_context.update(_copy_validation_intent(candidate_meta))

        if precursors is not None:
            sb = self.orch.try_precursors(
                precursors,
                reaction_type,
                action_context=action_context,
                reagents=list((candidate_meta or {}).get("reagents", []) or []),
            )
        elif bond_idx >= 0:
            sb = self.orch.try_disconnection(
                bond_idx,
                alt_idx,
                template_id=template_id,
                allow_template_fallback=allow_template_fallback,
                action_context=action_context,
            )
        elif fgi_idx >= 0:
            sb = self.orch.try_fgi(
                fgi_idx,
                action_context=action_context,
            )
        else:
            return {"error": "specify precursors, bond_idx, or fgi_idx"}

        attempt = sb.to_dict()
        attempt["attempt_idx"] = len(self._sandbox_attempts)
        if precursors is not None:
            attempt["source"] = "llm_proposed"
            attempt["input_precursors"] = precursors
        elif bond_idx >= 0:
            attempt["source"] = f"bond[{bond_idx}].alt[{alt_idx}]"
        else:
            attempt["source"] = f"fgi[{fgi_idx}]"

        if candidate_meta is None:
            if candidate_id:
                candidate_meta = self._candidate_lookup(candidate_id)
            elif bond_idx >= 0:
                candidate_id = f"bond:{bond_idx}:alt:{alt_idx}"
                candidate_meta = self._candidate_lookup(candidate_id)
            elif fgi_idx >= 0:
                candidate_id = f"fgi:{fgi_idx}"
                candidate_meta = self._candidate_lookup(candidate_id)

        if candidate_meta:
            attempt["candidate_id"] = candidate_meta.get("candidate_id", candidate_id)
            if candidate_meta.get("strategy_id"):
                attempt["strategy_id"] = candidate_meta.get("strategy_id", "")
            if candidate_meta.get("source_label") and candidate_meta.get("source") != "custom_precursors":
                attempt["source"] = candidate_meta["source_label"]
            candidate_summary = {
                "source": candidate_meta.get("source", ""),
                "source_label": candidate_meta.get("source_label", ""),
                "candidate_label": candidate_meta.get("candidate_label", ""),
                "reaction_id": candidate_meta.get("reaction_id", ""),
                "reaction_type": candidate_meta.get("reaction_type", ""),
                "template_id": candidate_meta.get("template_id", ""),
                "template_name": candidate_meta.get("template_name", ""),
                "precursors_preview": candidate_meta.get("precursors_preview", []),
                "reagents": candidate_meta.get("reagents", []),
                "execution": candidate_meta.get("execution", {}),
                "why_existing_candidates_rejected": candidate_meta.get("why_existing_candidates_rejected", ""),
                "rationale_summary": candidate_meta.get("rationale_summary", ""),
                "duplicate_of": candidate_meta.get("duplicate_of", ""),
                "route_sketch_id": candidate_meta.get("route_sketch_id", ""),
                "route_strategy_brief": candidate_meta.get("route_strategy_brief", {}),
                "rescue_id": candidate_meta.get("rescue_id", ""),
                "rescue_step_idx": candidate_meta.get("rescue_step_idx"),
                "continuation_precursor": candidate_meta.get("continuation_precursor", ""),
                "bond_idx": candidate_meta.get("bond_idx"),
                "alt_idx": candidate_meta.get("alt_idx"),
                "fgi_idx": candidate_meta.get("fgi_idx"),
                "smart_idx": candidate_meta.get("smart_idx"),
                "actual_bond_idx": candidate_meta.get("actual_bond_idx"),
                "atoms": candidate_meta.get("atoms", []),
                "risk_tags": candidate_meta.get("risk_tags", []),
            }
            candidate_summary.update(_copy_validation_intent(candidate_meta))
            if candidate_meta.get("experience_card_hints"):
                candidate_summary["experience_card_hints"] = candidate_meta.get("experience_card_hints", [])
            attempt["candidate_summary"] = candidate_summary
        elif candidate_id:
            attempt["candidate_id"] = candidate_id

        # ── 自动保护基建议：forbidden_fg 时附带 actionable 建议 ──
        fv = attempt.get("forward_validation", {})
        hard_fails = fv.get("hard_fail_reasons") or []
        if "forbidden_fg" in hard_fails and sb.success:
            try:
                from Rachel.chem_tools.fg_warnings import suggest_protection_needs
                ctx = self.orch._current_context
                target_smi = ctx.smiles if ctx else ""
                rtype = attempt.get("reaction_type", "")
                if target_smi and rtype:
                    prot = suggest_protection_needs(target_smi, rtype)
                    if prot.get("needs_protection"):
                        attempt["protection_needed"] = prot["suggestions"]
                        attempt["hint"] = (
                            "forbidden_fg 检测到官能团冲突。建议先保护相关基团，"
                            "将保护/脱保护作为候选登记后再用 try_candidate 验证。"
                            "详见 protection_needed 字段。"
                        )
            except Exception:
                pass

        ctx_for_mount = self.orch._current_context
        attempt_prompt_mount = build_prompt_mount(
            "try_action" if attempt.get("candidate_id") else "sandbox_try",
            decision_context=ctx_for_mount.decision_context if ctx_for_mount else None,
            payload=attempt,
            candidate=candidate_meta or attempt.get("candidate_summary") or {},
            attempt=attempt,
            chemist_guidance=self._chemist_guidance,
            route_plan=self._route_plan_brief(),
            route_strategy=self._route_strategy_brief(),
        )
        attempt["prompt_brief"] = self._attach_rescue_to_prompt_brief(
            build_prompt_brief(attempt_prompt_mount)
        )

        self._sandbox_attempts.append(attempt)
        self.save()
        return attempt

    def try_candidate(self, candidate_id: str) -> Dict[str, Any]:
        """Sandbox one normalized strategy candidate by stable candidate_id."""
        candidate = self._candidate_lookup(candidate_id)
        if candidate is None:
            return {"error": f"candidate_id not found: {candidate_id}"}

        source = candidate.get("source", "")
        risk_tags = set(candidate.get("risk_tags") or [])
        if "requires_llm_completion" in risk_tags:
            previews = candidate.get("fragments") or candidate.get("precursors_preview") or []
            execution = candidate.get("execution") or {}
            intentional_placeholder = "intentional_attachment_placeholder" in risk_tags
            hint = (
                "The '*' dummy atom is an intentional attachment-site marker and the "
                "system template remains a valid disconnection cue. The preview is not "
                "a real precursor set: complete this same action with propose_action, "
                "then validate the completed action with try_action."
                if intentional_placeholder
                else (
                    "This action is structural information, not a commit-ready reaction. "
                    "Correct or complete the precursors and evidence with propose_action, "
                    "then validate that custom action with try_action."
                )
            )
            return {
                "status": "llm_completion_required",
                "candidate_id": candidate_id,
                "source": source,
                "reaction_type_hint": candidate.get("reaction_type", source),
                "structural_hint_precursors": list(previews),
                "completion_obligation": execution.get("completion_obligation") or {
                    "task": "construct a complete one-step reaction proposal",
                    "next_step": "propose_action",
                },
                "hint": hint,
                "next_step": "propose_action",
            }
        if source == "bond":
            return self.sandbox_try(
                bond_idx=int(candidate.get("bond_idx", -1)),
                alt_idx=int(candidate.get("alt_idx", 0)),
                candidate_id=candidate_id,
                candidate_meta=candidate,
                template_id=candidate.get("template_id", ""),
                allow_template_fallback=False,
            )
        if source == "fgi":
            return self.sandbox_try(
                fgi_idx=int(candidate.get("fgi_idx", -1)),
                candidate_id=candidate_id,
                candidate_meta=candidate,
            )
        if source == "smart_capping":
            return {"error": "smart-capping candidate is missing its completion-required tag"}
        if source == "custom_precursors":
            precursor_normalization = candidate.get("precursor_normalization") or {}
            precursors = (
                precursor_normalization.get("original_precursors")
                or candidate.get("precursors_preview")
                or candidate.get("fragments")
                or []
            )
            if not precursors:
                return {"error": f"candidate {candidate_id} has no precursors to validate"}
            return self.sandbox_try(
                precursors=list(precursors),
                reaction_type=candidate.get("reaction_type", "llm_proposed"),
                candidate_id=candidate_id,
                candidate_meta=candidate,
            )
        if source == "terminal":
            return {
                "error": "terminal acceptance is not a sandbox reaction",
                "candidate_id": candidate_id,
                "hint": "Use accept_terminal(reason=...) after checking buyability and route criteria.",
            }

        return {"error": f"unsupported candidate source: {source}", "candidate_id": candidate_id}

    def try_action(self, action_id: str) -> Dict[str, Any]:
        """Sandbox one public action by stable action_id."""
        if self._candidate_lookup(action_id) is None:
            return {"error": f"action_id not found: {action_id}"}
        return _action_facing_payload(self.try_candidate(action_id))

    def sandbox_clear(self) -> None:
        """擦除沙盒。"""
        self._archive_sandbox("sandbox_clear", selected_idx=self._sandbox_selected)
        self._sandbox_attempts = []
        self._sandbox_selected = None
        self.save()

    def sandbox_select(self, attempt_idx: int) -> Dict[str, Any]:
        """选中沙盒中的某个方案。"""
        if attempt_idx < 0 or attempt_idx >= len(self._sandbox_attempts):
            return {"error": f"attempt_idx {attempt_idx} out of range"}
        self._sandbox_selected = attempt_idx
        self.save()
        return self._sandbox_attempts[attempt_idx]

    def commit(
        self,
        attempt_idx: Optional[int] = None,
        *,
        expected_action_id: str = "",
        reasoning: str = "",
        confidence: str = "medium",
        rejected: Optional[List[Dict[str, str]]] = None,
        validation_override: Optional[Dict[str, Any]] = None,
        route_plan_alignment: str = "",
        route_plan_note: str = "",
    ) -> Dict[str, Any]:
        """提交决策，写入树。自动保存。

        attempt_idx: 沙盒方案索引（默认用 sandbox_selected）
        """
        idx = attempt_idx if attempt_idx is not None else self._sandbox_selected
        if idx is None:
            return {"error": "no attempt selected. call sandbox_select(idx) first"}
        if idx < 0 or idx >= len(self._sandbox_attempts):
            return {"error": f"attempt_idx {idx} out of range"}

        attempt = self._sandbox_attempts[idx]
        selected_action_id = str(attempt.get("candidate_id", "") or "")
        expected_action_id = str(expected_action_id or "").strip()
        if expected_action_id and selected_action_id != expected_action_id:
            return {
                "error": "selected sandbox action does not match expected_action_id",
                "attempt_idx": idx,
                "expected_action_id": expected_action_id,
                "selected_action_id": selected_action_id,
            }
        if not attempt.get("success"):
            return {"error": "selected attempt was not successful"}

        precursors = attempt.get("precursors", [])
        reaction_type = attempt.get("reaction_type", "llm_proposed")
        template_id = attempt.get("template_id", "")
        template_name = attempt.get("template_name", "")
        gate_failure = self._evaluate_site_retention_gate(
            attempt,
            reasoning=reasoning,
            validation_override=validation_override,
        )
        if gate_failure:
            self._record_gate_failed_attempt(
                attempt,
                reason=gate_failure.get("error", "site-retention gate failed"),
                reasoning=reasoning,
                confidence=confidence,
            )
            self.save()
            return gate_failure

        validation_gate_failure = self._evaluate_validation_gate(
            attempt,
            validation_override=validation_override,
        )
        if validation_gate_failure:
            self._record_gate_failed_attempt(
                attempt,
                reason=validation_gate_failure.get("error", "validation gate failed"),
                reasoning=reasoning,
                confidence=confidence,
            )
            self.save()
            return validation_gate_failure

        candidate_comparison = [self._attempt_summary(a) for a in self._sandbox_attempts]
        action_comparison = _action_facing_payload(candidate_comparison)
        selected_summary = _action_facing_payload(self._attempt_summary(attempt))
        ctx_for_mount = self.orch._current_context
        active_rescue = (
            self._active_rescue_continuation_for_smiles(ctx_for_mount.smiles)
            if ctx_for_mount
            else {}
        )
        commit_prompt_mount = build_prompt_mount(
            "commit",
            decision_context=ctx_for_mount.decision_context if ctx_for_mount else None,
            payload={
                "validation_override": validation_override,
                "rejected": rejected or [],
            },
            candidate=attempt.get("candidate_summary") or {},
            attempt=attempt,
            attempts=self._sandbox_attempts,
            chemist_guidance=self._chemist_guidance,
            route_plan=self._route_plan_brief(),
            route_strategy=self._route_strategy_brief(),
        )
        decision_audit = {
            "selected_attempt_idx": idx,
            "selected_action_id": attempt.get("candidate_id", ""),
            "selected_attempt": selected_summary,
            "action_comparison": action_comparison,
            "rejected_actions": _action_facing_payload(rejected or []),
            "sandbox_evidence_count": len(action_comparison),
            "prompt_state": commit_prompt_mount["prompt_state"],
            "decision_source": self._decision_source(attempt),
        }
        if attempt.get("reagents"):
            decision_audit["reagents"] = list(attempt.get("reagents", []) or [])
        if attempt.get("precursor_normalization"):
            decision_audit["precursor_normalization"] = attempt.get("precursor_normalization")
        route_plan_brief = self._route_plan_brief()
        if route_plan_brief:
            decision_audit["route_plan_brief"] = route_plan_brief
            decision_audit["route_plan_id"] = route_plan_brief.get("id", "")
            decision_audit["route_plan_revision"] = route_plan_brief.get("revision", 0)
            if route_plan_alignment:
                decision_audit["route_plan_alignment"] = self._guidance_summary_text(
                    route_plan_alignment,
                    max_chars=80,
                )
            if route_plan_note:
                decision_audit["route_plan_note"] = self._guidance_summary_text(
                    route_plan_note,
                    max_chars=220,
                )
        if self._chemist_guidance:
            decision_audit["chemist_guidance_ids"] = [
                item["id"] for item in self._guidance_brief()
            ]
            decision_audit["chemist_guidance_summary"] = self._guidance_brief()
            decision_audit["chemist_guidance_provenance"] = self._guidance_provenance()
        route_sketch_id = (
            (attempt.get("candidate_summary") or {}).get("route_sketch_id")
            or attempt.get("route_sketch_id")
            or active_rescue.get("route_sketch_id", "")
            or self._latest_route_sketch_id()
        )
        if route_sketch_id:
            decision_audit["route_sketch_id"] = route_sketch_id
            decision_audit["route_strategy_brief"] = self._route_strategy_brief()
            decision_audit["route_sketch_provenance"] = self._route_sketch_provenance()
        selected_gate = (attempt.get("forward_validation") or {}).get("gate")
        if selected_gate:
            decision_audit["validation_gate"] = selected_gate
        if validation_override:
            decision_audit["validation_override"] = validation_override
        if commit_prompt_mount.get("active_experience_card_ids"):
            decision_audit["applied_experience_card_ids"] = list(
                commit_prompt_mount["active_experience_card_ids"]
            )
        elif (attempt.get("prompt_brief") or {}).get("active_experience_card_ids"):
            decision_audit["applied_experience_card_ids"] = list(
                attempt["prompt_brief"]["active_experience_card_ids"]
            )
        if attempt.get("strategy_id"):
            decision_audit["selected_strategy_id"] = attempt.get("strategy_id", "")

        decision = LLMDecision(
            selection_reasoning=reasoning,
            confidence=confidence,
            rejected_alternatives=rejected or [],
            site_audit_summary=(attempt.get("site_audit") or {}).get("summary", ""),
            selected_candidate_id=attempt.get("candidate_id", ""),
            selected_strategy_id=attempt.get("strategy_id", ""),
            decision_audit=decision_audit,
        )

        result = self.orch.commit_decision(
            precursor_override=precursors,
            reagents=list(attempt.get("reagents", []) or []),
            reaction_type=reaction_type,
            template_id=template_id,
            template_name=template_name,
            validated_forward_validation=attempt.get("forward_validation"),
            llm_decision=decision,
        )
        rescue_continuation = {}
        if result.success and route_sketch_id:
            rescue_continuation = self._register_rescue_continuation_after_commit(
                attempt=attempt,
                result=result,
                route_sketch_id=route_sketch_id,
                active_rescue=active_rescue,
            )

        self._archive_sandbox("commit", selected_idx=idx)
        # 清空沙盒
        self._sandbox_attempts = []
        self._sandbox_selected = None
        self._chemist_guidance = []
        self._clear_route_sketch_state()
        self.save()

        result_dict = result.to_dict()
        if rescue_continuation:
            result_dict["rescue_continuation"] = rescue_continuation
        result_dict["prompt_brief"] = self._attach_rescue_to_prompt_brief(
            build_prompt_brief(commit_prompt_mount)
        )
        return result_dict

    def accept_terminal(
        self,
        reason: str = "",
        *,
        rescue_not_actionable_reason: str = "",
        force_accept_without_rescue: bool = False,
    ) -> Dict[str, Any]:
        """标记当前分子为 terminal。自动保存。"""
        terminal_rescue = self._terminal_rescue_gate(
            rescue_not_actionable_reason=rescue_not_actionable_reason,
            force_accept_without_rescue=force_accept_without_rescue,
        )
        if terminal_rescue.get("error"):
            return terminal_rescue

        active_smiles = self._active_molecule()
        self._archive_sandbox("accept_terminal", selected_idx=self._sandbox_selected)
        self.orch.accept_terminal(reason=reason)
        if active_smiles:
            self.orch._force_standard_smiles.discard(active_smiles)
        self._sandbox_attempts = []
        self._sandbox_selected = None
        self._chemist_guidance = []
        self._clear_route_sketch_state()
        self.save()
        result = {"ok": True, "action": "accepted_terminal"}
        if terminal_rescue:
            result["terminal_rescue"] = terminal_rescue
        return result

    def review_terminal(
        self,
        smiles: str,
        reason: str,
        additional_steps: int = 0,
    ) -> Dict[str, Any]:
        """Route an existing terminal leaf through the normal LLM decision loop."""
        if (
            isinstance(additional_steps, bool)
            or not isinstance(additional_steps, int)
            or additional_steps < 0
        ):
            return {"error": "additional_steps must be a non-negative integer"}
        can = self._canonical_smiles_text(smiles)
        reason = self._guidance_summary_text(reason, max_chars=320)
        if not can:
            return {"error": "valid terminal smiles required"}
        if not reason:
            return {"error": "reason required"}
        node = self.orch.tree.get_molecule_by_smiles(can)
        if node is None:
            return {"error": "terminal molecule not found in tree", "smiles": can}
        if node.role != MoleculeRole.TERMINAL.value:
            return {"error": "molecule is not terminal", "smiles": can}
        expanded_products = {
            reaction.product_node for reaction in self.orch.tree.reaction_nodes
        }
        if node.node_id in expanded_products:
            return {"error": "expanded molecule cannot be reopened", "smiles": can}
        if (
            self.orch._steps_executed >= self.orch.max_steps
            and additional_steps == 0
        ):
            return {
                "error": "step budget exhausted",
                "steps_executed": self.orch._steps_executed,
                "max_steps": self.orch.max_steps,
                "hint": "retry review_terminal with additional_steps > 0",
            }

        if additional_steps > 0:
            self.orch.max_steps += additional_steps
        self.orch.tree.reopen()
        self.orch.tree.mark_intermediate(can)
        self.orch._force_standard_smiles.add(can)
        self.orch._queue = type(self.orch._queue)(
            (queued, depth)
            for queued, depth in self.orch._queue
            if queued != can
        )
        self.orch._queue.appendleft((can, node.depth))
        self.orch._seen.add(can)
        self.orch.audit_state.record_decision(
            step_id="",
            molecule=can,
            action="review-terminal",
            reasoning_summary=reason[:120],
            outcome="reopened",
        )
        self.save()
        return {
            "ok": True,
            "action": "terminal_review_queued",
            "smiles": can,
            "reason": reason,
            "next_step": "next",
        }

    def skip(self, reason: str = "") -> None:
        """跳过当前分子。自动保存。"""
        self._archive_sandbox("skip", selected_idx=self._sandbox_selected)
        self.orch.skip_current(reason)
        self._sandbox_attempts = []
        self._sandbox_selected = None
        self._chemist_guidance = []
        self._clear_route_sketch_state()
        self.save()

    def rescue_status(self) -> Dict[str, Any]:
        active = [
            self._rescue_continuation_brief(item)
            for item in self._pending_rescue_continuations()
        ]
        return {
            "active_rescue_continuations": active,
            "blocked_rescue_count": len(active),
            "total_rescue_continuations": len(self._rescue_continuations),
        }

    def get_status(self) -> Dict[str, Any]:
        status = self.orch.get_status()
        status.update(self.rescue_status())
        return status

    def rescue_abort(self, *, rescue_id: str = "", reason: str = "") -> Dict[str, Any]:
        reason = self._guidance_summary_text(reason, max_chars=320)
        if not reason:
            return {"error": "reason required"}
        target: Optional[Dict[str, Any]] = None
        for item in self._pending_rescue_continuations():
            if not rescue_id or item.get("id") == rescue_id:
                target = item
                break
        if target is None:
            return {"error": "rescue_continuation_not_found", "rescue_id": rescue_id}

        target["status"] = "aborted"
        target["abort_reason"] = reason
        target["closed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        focus = target.get("focus_smiles", "")
        if focus:
            self.orch._force_standard_smiles.discard(focus)
            self.orch._queue = type(self.orch._queue)(
                (smi, depth)
                for smi, depth in self.orch._queue
                if smi != focus
            )
            if self.orch._current_context and self.orch._current_context.smiles == focus:
                self.orch._current_context = None
            self.orch.tree.mark_terminal(focus)
            self.orch.audit_state.record_decision(
                step_id="",
                molecule=focus,
                action="rescue-abort",
                reasoning_summary=reason[:120],
                outcome="terminal",
            )
        self.save()
        return {
            "ok": True,
            "action": "rescue_aborted",
            "rescue_continuation": self._rescue_continuation_brief(target),
        }

    def finalize(self, summary: str = "") -> Dict[str, Any]:
        """完成编排。自动保存。"""
        pending = [
            self._rescue_continuation_brief(item)
            for item in self._pending_rescue_continuations()
        ]
        if pending:
            self.save()
            return {
                "error": "rescue_continuation_pending",
                "active_rescue_continuations": pending,
                "hint": "Close the strategy continuation with continuation_abort(reason=...) or commit the pending continuation step before finalize.",
            }
        result = self.orch.finalize(summary)
        self.save()
        return result

    def get_orchestrator(self) -> RetrosynthesisOrchestrator:
        """获取底层编排器（高级用法）。"""
        return self.orch
