"""Prompt-policy and experience-card mounting for Rachel LLM payloads.

This module is intentionally deterministic. It selects short, executable
experience cards from the current molecule/site/sandbox context; it does not
perform chemistry generation and does not expose diagnostic payloads.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

from Rachel.chem_tools.cs_score import CS_TRIVIAL
from Rachel.chem_tools.topology_intent import action_declares_topology_change
from Rachel.chem_tools.validation_contract import (
    build_validation_contract,
)


CARD_SOURCE_NAME = "experience_cards.json"
CARD_SOURCE_PATH = Path(__file__).resolve().parent.parent / CARD_SOURCE_NAME
POLICY_VERSION = "rachel-v2-policy-003"
DEFAULT_MAX_EXPERIENCE_CARDS = 4
TERMINAL_MAX_EXPERIENCE_CARDS = 5
TERMINAL_RESCUE_MAX_EXPERIENCE_CARDS = 5
CUSTOM_TOPOLOGY_MAX_EXPERIENCE_CARDS = 5
TERMINAL_RESCUE_EVENTS = {
    "stage.terminal",
    "decision.accept_terminal",
    "action.terminal_acceptance",
    "strategy.advanced_terminal_rescue_requested",
}
TOPOLOGY_AUDIT_TAGS = {
    "topology",
    "ring",
    "ring_bond",
    "ring_construction",
    "ring_closure",
    "ring_opening",
    "annulation",
    "cyclization",
    "scaffold",
    "scaffold_edit",
    "fused_ring",
    "spiro",
    "bridged",
    "macrocycle",
    "new_fused_ring_system",
    "new_spiro_center",
    "new_bridged_system",
    "new_medium_ring",
    "new_macrocycle",
    "ring_system_merge",
    "new_fused_medium_ring_requires_evidence",
    "new_fused_ring_requires_evidence",
    "new_spiro_center_requires_evidence",
    "new_bridged_system_requires_evidence",
    "new_macrocycle_requires_evidence",
    "high_risk_topology_requires_independent_evidence",
}
TOPOLOGY_SIGNAL_RISK_TAGS = TOPOLOGY_AUDIT_TAGS - {"scaffold"}
HIGH_RISK_TOPOLOGY_CARD_TAGS = {
    "fused_ring",
    "spiro",
    "bridged",
    "macrocycle",
    "new_fused_ring_system",
    "new_spiro_center",
    "new_bridged_system",
    "new_medium_ring",
    "new_macrocycle",
    "ring_system_merge",
    "new_fused_medium_ring_requires_evidence",
    "new_fused_ring_requires_evidence",
    "new_spiro_center_requires_evidence",
    "new_bridged_system_requires_evidence",
    "new_macrocycle_requires_evidence",
    "high_risk_topology_requires_independent_evidence",
}
ATOM_SOURCE_CARD_TAGS = {
    "atom_mapping",
    "atom_source",
    "formed_bonds",
    "cleaved_bonds",
    "unmapped_product_atoms",
    "validation_micro",
    "evidence_packet",
    "family_interpretation",
    "proof_obligation",
}
STAGE_ALIASES = {
    "try_candidate": "try_action",
    "propose_candidate": "propose_action",
}
DISCOVERY_STAGES = {
    "context_compact",
    "guide",
    "route_plan",
    "reaction_sites",
    "explore_site",
    "explore_reaction",
    "route_sketch",
    "propose_action",
}

STANDING_RULES = [
    "Rachel supplies structured chemical facts, candidate scaffolds, risks, and audit obligations; the LLM owns route strategy, reaction design, precursor completion, and final chemistry judgment.",
    "For a complex target without an active route plan, the LLM normally records a short revision-0 provisional whole-molecule thesis from the target, molecule_brief, and functional_group_brief, then uses reaction_sites/explore_site evidence to support, falsify, or enrich it into an evidence-enriched complete revision-1 plan. If molecule-level facts cannot yet support a useful seed, inspect relevant sites first and let the first route_plan call record an evidence-first complete revision-0 plan. Revise whenever evidence changes a recorded substantive plan claim; Rachel listed actions are evidence and peer candidates, not the plan itself.",
    "System action-space is a candidate scaffold, not the full retrosynthesis boundary; a stronger complete one-step LLM hypothesis may go directly through propose_action -> try_action, while route_sketch is useful for route-thesis changes or multi-event ideas.",
    "For routine site identity, explore_site provides atoms, actual_bond_idx, role_pair, bond_type, in_ring, and bond_fg_context.",
    "Treat route_plan as a revisable strategic hypothesis; keep it short and update it when evidence changes the route thesis.",
    "Before committing the first route thesis for a complex target, compare late FGI/editing with scaffold assembly or electronic-state strategy.",
    "Template pass is evidence, not a sufficient reason to commit.",
    "Do not commit a blocked validation result; distinguish chemistry contradictions from validator errors.",
    "Prefer preserving mature heteroaryl scaffolds when routes are comparably credible; ring construction remains available when chemically justified.",
    "Treat listed Rachel actions and complete LLM-designed one-step actions as peer chemical hypotheses. When an LLM-designed action appears stronger or more route-coherent, lead with its positive chemical case and use comparison only to explain why it is worth testing; then validate the selected executable candidate through try_action.",
    "For custom scaffold/ring actions, declare intended_deltas, expected_ring_change, changed_bonds, preserved_anchors, and mechanistic_evidence before sandboxing; family_evidence is optional support.",
    "Treat chemist guidance as high-priority route direction, not as validation evidence.",
    "When local action-space is route-incoherent or an idea spans multiple events, consider a target-oriented route_sketch before forcing deep disconnections.",
    "Before accepting a nontrivial advanced terminal, explicitly ask: can this small target be made in 1-3 mechanistically selective steps from simpler precursors?",
]

QUALITY_GUARDRAILS = [
    "Rachel supplies structured chemical facts, candidate scaffolds, risks, and challenges; the LLM owns provisional route hypotheses, reaction design, comparison, and final chemistry judgment.",
    "Chemical plausibility and route quality outrank template score, validation convenience, and route depth.",
    "Prefer preserving established scaffold topology when routes are comparably credible; any ring construction, opening, or scaffold change still requires explicit mechanistic and atom-source justification.",
    "At route-plan initialization, record the likely route paradigm, evidence, strategic risks, and revision triggers.",
    "Treat local action-space as evidence, not the full retrosynthesis boundary; when it captures only local FGI while core construction remains unresolved, consider revising route_plan or using route_sketch.",
    "If terminal review exposes a hidden core-construction problem, revise route_plan before accepting or committing.",
    "Account for key C/N/S/halogen/protecting-group atoms and missing small molecules before commit.",
    "Prefer installing reactive temporary handles late when compatible with the route; protection/deprotection must remain explicit tree steps.",
    "Drive toward simple, stable, purchasable precursors when chemistry remains credible; accept honest advanced terminals over speculative low-confidence deep disconnections.",
    "Listed Rachel actions and complete LLM-designed one-step actions are peer hypotheses. For an LLM-designed candidate, build the positive chemical case first; use comparison as secondary selection provenance, then validate the selected event through the shared sandbox and commit path.",
    "Treat proof_required as a proof-obligation signal: first add atom-source/tether/anchor/mechanistic evidence or revise the precursor; use validation_override only after the concern is chemically managed.",
    "For ring, fused, spiro, bridged, macrocycle, rearrangement, or scaffold-editing actions, use reaction topology verification: observed deltas must match the declared mechanism, atom-source/tether evidence, preserved anchors, and any optional family interpretation.",
    "Do not accept a nontrivial advanced terminal until a short target-oriented rescue sketch has asked whether simpler precursors, selectivity, and one executable next step exist.",
    "If strategy continuation is active, resolve that forced precursor review before accepting the molecule or finalizing the route.",
    "Clear validation has no gate objection; continue normal chemistry review because clear is not proof.",
    "Address the named validation warnings and their chemical consequences before commit.",
    "For inconclusive validation, separate evidence gaps from tool limits; tool or template absence is neither proof nor chemical disproof, so complete the chemistry review and repair or rerun tools when useful.",
    "Treat proof_required as a proof obligation: add the named atom-source, tether, anchor, or mechanistic evidence, revise the precursor/action, or use an explicit override only after the concern is chemically managed.",
    "A blocked validation caused by a system error is an execution stop: repair or rerun validation; it is not chemical disproof, and validation_override must not conceal unavailable validation.",
    "A chemically contradictory blocked result cannot be committed; revise or reject the candidate on the named contradiction.",
]

STAGE_TAGS: Dict[str, List[str]] = {
    "context_compact": ["molecule_triage", "scaffold", "convergent", "route_mode"],
    "guide": ["chemist_guidance", "site_fidelity", "reaction_direction", "audit"],
    "route_plan": ["route_plan", "route_mode", "strategic_rescue", "audit"],
    "reaction_sites": ["site_fidelity", "convergent", "top_level", "handle_timing"],
    "explore_site": ["site_fidelity", "competition"],
    "explore_reaction": ["site_fidelity", "competition"],
    "route_sketch": ["strategic_rescue", "action_space_weak", "custom_precursor", "audit"],
    "propose_action": ["custom_precursor", "propose_action", "action_rejection", "audit"],
    "try_action": ["sandbox", "template_evidence", "forward_validation"],
    "sandbox_try": ["sandbox", "template_evidence", "forward_validation"],
    "sandbox_list": ["sandbox", "template_evidence", "action_rejection"],
    "commit": ["commit", "atom_accounting", "site_fidelity", "forward_validation"],
    "terminal": ["advanced_terminal", "terminal", "buyability"],
}

EVENT_TAGS: Dict[str, List[str]] = {
    "stage.context_compact": STAGE_TAGS["context_compact"],
    "stage.guide": STAGE_TAGS["guide"],
    "stage.route_plan": STAGE_TAGS["route_plan"],
    "stage.reaction_sites": STAGE_TAGS["reaction_sites"],
    "stage.explore_site": STAGE_TAGS["explore_site"],
    "stage.explore_reaction": STAGE_TAGS["explore_reaction"],
    "stage.route_sketch": STAGE_TAGS["route_sketch"],
    "stage.propose_action": STAGE_TAGS["propose_action"],
    "stage.try_action": STAGE_TAGS["try_action"],
    "stage.sandbox_try": STAGE_TAGS["sandbox_try"],
    "stage.sandbox_list": STAGE_TAGS["sandbox_list"],
    "stage.commit": STAGE_TAGS["commit"],
    "stage.terminal": STAGE_TAGS["terminal"],
    "action.system_template": ["template_evidence"],
    "action.intentional_attachment_placeholder": [
        "intentional_attachment_placeholder",
        "custom_precursor",
        "propose_action",
        "audit",
    ],
    "action.custom_precursors": ["custom_precursor", "llm_proposed", "action_rejection", "audit"],
    "action.precursor_normalization": [
        "precursor_normalization",
        "organometallic_source_obligation",
        "organometallic",
    ],
    "action.duplicates_existing_action": ["action_rejection", "custom_precursor", "site_fidelity"],
    "action.smart_capping": ["handle_timing", "compatibility"],
    "action.terminal_acceptance": ["terminal", "advanced_terminal", "buyability"],
    "sandbox.success": ["sandbox"],
    "sandbox.failure": ["sandbox", "action_rejection"],
    "site.same_site_competition": ["competition", "site_fidelity"],
    "site.ring_bond_review": ["topology_signal", "topology", "ring_bond", "ring_construction"],
    "site.same_core_custom_precursor": ["site_fidelity", "custom_precursor"],
    "site.site_anchor_drift": ["site_fidelity", "site_shift"],
    "site.site_retention_missing_evidence": ["site_fidelity", "forward_validation"],
    "site.fused_heteroaryl_site_sensitive": ["site_fidelity", "fused_heteroaryl", "heteroaryl"],
    "validation.clear": ["forward_validation", "clear", "template_evidence"],
    "validation.warning": ["forward_validation"],
    "validation.inconclusive": ["forward_validation", "inconclusive", "commit_gate"],
    "validation.proof_required": ["forward_validation", "proof_required", "proof_obligation", "commit_gate"],
    "validation.blocked": ["forward_validation", "blocked", "hard_fail"],
    "validation.forward_template_unavailable": ["forward_validation", "tool_limit"],
    "validation.forward_template_target_not_regenerated": ["forward_validation", "tool_limit"],
    "validation.major_scaffold_not_inherited": ["site_fidelity", "forward_validation"],
    "validation.new_fused_medium_ring_requires_evidence": ["topology_signal", "topology", "ring_construction", "fused_ring", "scaffold_edit"],
    "validation.new_fused_ring_requires_evidence": ["topology_signal", "topology", "ring_construction", "fused_ring", "scaffold_edit"],
    "validation.new_spiro_center_requires_evidence": ["topology_signal", "topology", "ring_construction", "spiro", "scaffold_edit"],
    "validation.new_bridged_system_requires_evidence": ["topology_signal", "topology", "ring_construction", "bridged", "scaffold_edit"],
    "validation.new_macrocycle_requires_evidence": ["topology_signal", "topology", "ring_construction", "macrocycle", "scaffold_edit"],
    "validation.high_risk_topology_requires_independent_evidence": ["topology_signal", "topology", "ring_construction", "scaffold_edit"],
    "validation.skeleton_imbalance": ["atom_accounting", "skeleton_imbalance", "multicomponent"],
    "validation.severe_imbalance": ["atom_accounting", "hard_fail"],
    "validation.functional_group_condition_conflict": ["compatibility", "protection"],
    "decision.commit_requested": ["commit", "audit"],
    "decision.commit_with_override": ["commit", "audit", "forward_validation", "commit_gate"],
    "decision.sandbox_clear": ["sandbox", "action_rejection"],
    "decision.accept_terminal": ["terminal", "advanced_terminal", "buyability"],
    "decision.skip_blocked": ["terminal", "action_rejection"],
    "chemist.directive": ["chemist_guidance", "audit"],
    "chemist.site_hint": ["chemist_guidance", "site_fidelity"],
    "chemist.reaction_hint": ["chemist_guidance", "reaction_direction"],
    "chemist.precursor_hint": ["chemist_guidance", "custom_precursor"],
    "chemist.terminal_hint": ["chemist_guidance", "terminal", "advanced_terminal"],
    "chemist.approval": ["chemist_guidance", "commit", "audit"],
    "strategy.action_space_weak": ["strategic_rescue", "action_space_weak", "custom_precursor"],
    "strategy.route_plan_active": ["route_plan", "strategic_rescue", "audit"],
    "strategy.route_plan_revised": ["route_plan", "strategic_rescue", "audit"],
    "strategy.route_mode_triage": ["route_mode", "late_functionalization", "scaffold_assembly", "electronic_state_strategy", "strategic_rescue"],
    "strategy.route_sketch_requested": ["strategic_rescue", "route_sketch", "action_rejection"],
    "strategy.route_sketch_active": ["strategic_rescue", "route_sketch", "audit"],
    "strategy.route_sketch_used_for_custom_action": ["strategic_rescue", "custom_precursor", "audit"],
    "strategy.advanced_terminal_rescue_requested": ["strategic_rescue", "advanced_terminal", "terminal_rescue", "custom_precursor"],
}

STAGE_SELF_PROMPTS: Dict[str, List[str]] = {
    "context_compact": [
        "With no active route_plan_brief, normally register a short revision-0 provisional thesis from molecule_brief and functional_group_brief before broad local search; if the target is simple or those facts cannot yet support a useful seed, use reaction_sites() first. If ring membership, stereocenter location, or whole-molecule atom/bond indexing is specifically needed, use context(detail=\"structure\").",
        "Compare route paradigms first: late FGI/editing vs scaffold assembly vs electronic-state strategy.",
        "Prefer real convergent handles and preserve mature scaffolds unless deep construction is justified.",
    ],
    "reaction_sites": [
        "Choose a real reaction site, not a reaction name in isolation.",
        "Prioritize convergence, site fidelity, handle timing, and functional-group compatibility; use context(detail=\"structure\") only when whole-molecule topology or atom-index evidence blocks site choice.",
        "If no route_plan_brief exists after site evidence, establish an evidence-first complete revision-0 plan; if route_plan_brief is a short seed, use the site map and selected explore_site evidence to enrich it into a complete revision-1 plan; if a complete plan is active, identify support, falsification, or evidence that materially revises recorded disconnections, precursor logic, sequence, handle timing, preserve/build choices, risks, or revision triggers.",
    ],
    "guide": [
        "Convert chemist guidance into route constraints and candidate priorities.",
        "Still validate the chosen action; guidance is direction, not proof.",
    ],
    "route_plan": [
        "Use route_plan in two paths: revision 0 may be a short LLM-owned provisional thesis seed grounded in the target and molecule-level Rachel facts and must use revision_reason=\"initial\"; if that seed was recorded, relevant reaction_sites/explore_site Rachel molecule/site facts should produce an evidence-enriched complete revision 1 plan, while an evidence-first initial call with no prior seed records the complete revision-0 plan directly.",
        "On every later revision, restate the complete current plan because route_plan replaces rather than merges omitted fields; include route_mode, mode evidence, key disconnections, precursor logic, preserve/build decisions, strategic risks, revision triggers, terminal policy, and revision reason.",
        "Revise when evidence changes a recorded substantive claim, including precursor family, sequence, handle timing, preserve/build choice, or selectivity strategy; do not revise for catalyst, reagent, solvent, or template-only changes within the same planned event.",
        "Rachel listed actions and LLM-designed actions are peer executable evidence, not the global plan; use them to support, falsify, enrich, or revise the thesis rather than copying the local action menu.",
    ],
    "explore_site": [
        "For site identity, first read atoms, actual_bond_idx, role_pair, bond_type, in_ring, and bond_fg_context; if these local facts are insufficient, use context(detail=\"structure\").",
        "Treat listed and LLM-designed actions as peer chemical hypotheses. A stronger different same-site reaction or unlisted disconnection may go directly through propose_action when it is one complete event. Focus first on its positive chemical case: complete precursors and reagents, reaction/site, mechanism, atom sources, selectivity, topology/site fidelity, and route-plan alignment; compare listed actions only to explain why this candidate is worth testing. route_sketch is optional when the idea changes route strategy or spans multiple events.",
        "If this evidence changes a recorded key disconnection, precursor family, sequence, handle timing, preserve/build decision, or selectivity strategy, revise route_plan and restate the complete current plan; if only catalyst, reagent, solvent, or template implementation changes within the same planned event, continue without a plan revision and record alignment at commit.",
    ],
    "explore_reaction": [
        "Use this auxiliary reaction-family view to compare mechanism, site fidelity, precursor realism, and compatibility across actions.",
        "Return to explore_site(site_id) for the normal site-first decision; validate a selected listed or LLM-designed peer action through try_action.",
    ],
    "route_sketch": [
        "Consider 1-3 target-oriented short hypotheses, then record exactly one next executable chemical event.",
        "For advanced-terminal review, actionable means a complete precursor set, one real event, and a selectivity source; otherwise use no-actionable.",
        "If the next event is unlisted, use propose_action(...) with complete precursor SMILES before try_action.",
    ],
    "propose_action": [
        "Build the positive chemical case for one real chemical event: provide complete precursor SMILES and reagents, reaction name/site, mechanism, atom sources, selectivity, topology/site fidelity, route-plan alignment, and atom accounting; include route_sketch_id only when a route sketch actually guides the action. Comparison is secondary; cite rejected action IDs/reasons only when actually rejecting those actions.",
        "For ring/scaffold edits, fill intended_deltas, expected_ring_change, changed_bonds, preserved_anchors, and mechanistic_evidence; family_evidence is optional support.",
    ],
    "try_action": [
        "Treat sandbox execution as transport status only; inspect canonical validation, atom accounting, and site fidelity.",
        "Read the current validation state and its named observations, contradictions, proof_obligations, evidence_gaps, tool_limits, warnings, system_errors, and optional mechanism_interpretation; follow the state-specific recovery instruction without substituting the state label for chemical judgment.",
        "Do not treat a reaction-family name, hidden steps, missing selectivity, or incomplete atom accounting as commit-ready support; add the missing chemical evidence, revise the action, or reject it on chemistry.",
    ],
    "sandbox_list": [
        "Compare attempts by action_id, reaction type, precursor realism, validation, and rejected alternatives.",
        "For custom topology attempts, reconcile validation observations with the declared mechanism, changed bonds, atom source, tether/anchor evidence, and optional mechanism interpretation before override or commit.",
        "For terminal review, choose one outcome: commit a credible mini-route step, try one more concrete action, or accept only with explicit no-actionable reason.",
    ],
    "commit": [
        "Commit only after recording the selected action, sandbox evidence, applied card ids, and required audit evidence; when an alternative is actually rejected, record its id and state whether the rejection is chemical or only about the current Rachel representation/evidence.",
        "If overriding a topology gate, cite proof_obligations plus changed bonds, preserved anchors, atom-source/tether evidence, and any optional mechanism support.",
    ],
    "terminal": [
        "Before nontrivial advanced-terminal accept, run route_sketch(..., terminal_review=True) to test for a 1-3 step rescue.",
        "After a terminal-review sketch, accept requires one route-sketch-derived custom sandbox attempt or an explicit no-actionable override.",
    ],
}

DEFAULT_COMMAND_POLICY = {
    "primary_next": ["reaction_sites()"],
    "support": ["status", "tree"],
    "guardrails": [
        "Do not use hidden legacy bond/FGI commands as the default route.",
        "Use accept(reason) for explicit terminal decisions; skip marks the node terminal and is a last resort.",
    ],
}

COMMAND_POLICIES: Dict[str, Dict[str, List[str]]] = {
    "context_compact": {
        "primary_next": [
            "route_plan(...) for a short revision-0 provisional complex-target thesis",
            "reaction_sites() if the target is simple or site evidence is needed before a useful seed",
        ],
        "support": ["status", "tree"],
        "guardrails": [
            "Use reaction_sites() to open the first-layer site menu before sandboxing.",
            "Use accept(reason) only for explicit terminal or advanced-terminal stopping criteria.",
            "skip marks the current molecule terminal; do not use it as a temporary defer.",
        ],
    },
    "guide": {
        "primary_next": ["reaction_sites()", "explore_site(site_id) if the guided site is already known"],
        "support": ["route_plan(...) if guidance changes the global route thesis", "route_sketch(...) if the chemist direction is strategic rather than one-step"],
        "guardrails": [
            "Treat chemist guidance as high-priority direction but still validate chemistry.",
            "If guidance specifies a precursor or reaction, convert it through propose_action(...) before try_action.",
        ],
    },
    "route_plan": {
        "primary_next": ["reaction_sites()", "explore_site(site_id) if the next site is already known"],
        "support": ["route_sketch(...) for a local strategy-to-action checkpoint", "propose_action(...) only for one executable next step"],
        "guardrails": [
            "A route plan is a persistent synthesis thesis, not a commit or validation result.",
            "Use two paths: when a short revision-0 provisional seed exists, restate an evidence-enriched complete revision-1 plan after relevant site analysis; when site evidence comes first, the initial route_plan call records the complete revision-0 plan directly.",
            "Rachel listed and LLM-designed actions are evidence and peer candidates, not the plan; use them to support, falsify, enrich, or revise the thesis.",
            "Record the route paradigm as a hypothesis: late functionalization/FGI, scaffold assembly, electronic-state strategy, or a justified hybrid.",
            "Revise when a recorded substantive claim changes; do not revise for implementation-only changes within the same disconnection and precursor logic.",
            "Every revision restates the complete current plan because omitted fields are not merged from the previous revision.",
            "Keep the brief short; do not paste full route history into LLM context.",
        ],
    },
    "reaction_sites": {
        "primary_next": [
            "explore_site(site_id)",
            "route_plan(...) if site-map evidence now establishes an evidence-first complete revision-0 plan, enriches a provisional seed, or changes a recorded substantive plan claim",
        ],
        "support": ["context(compact)", "status"],
        "guardrails": [
            "Choose a real site_id first; do not sandbox directly from the first-layer menu.",
            "Do not use hidden legacy commands for normal decisions.",
        ],
    },
    "explore_site": {
        "primary_next": [
            "try_action(action_id)",
            "propose_action(...) for a complete different same-site reaction or unlisted disconnection; route_sketch is optional and is useful when the idea changes route strategy or spans multiple events",
        ],
        "support": ["propose_action(...) after route_sketch", "sandbox_list"],
        "guardrails": [
            "Compare same-site actions before committing.",
            "Use smart_cap/custom_cap only as expert ideation; convert useful output through propose_action(...) then try_action(custom_id).",
        ],
    },
    "route_sketch": {
        "primary_next": ["propose_action(...) for the next unlisted real step", "explore_site(site_id) if a listed site remains viable"],
        "support": ["accept(...) only when no actionable first mini-route event can be defined, using force_accept_without_rescue with rescue_not_actionable_reason"],
        "guardrails": [
            "A route sketch is an LLM strategic design checkpoint, not a validation gate.",
            "Use it to challenge weak or route-incoherent system actions and propose a strategy-driven next step.",
            "For advanced-terminal review, first ask how this molecule could be made as a target in 1-3 mechanistically selective steps.",
            "Convert only one next executable chemical event into an action before try_action.",
            "For a multi-step strategy, bind the first committed event to the precursor that should continue through strategy continuation.",
            "It cannot commit or bypass sandbox validation.",
        ],
    },
    "explore_reaction": {
        "primary_next": ["try_action(action_id)"],
        "support": ["explore_site(site_id)", "reaction_sites()"],
        "guardrails": [
            "This is an auxiliary diagnostic view; prefer explore_site(site_id) for normal same-site comparison.",
        ],
    },
    "propose_action": {
        "primary_next": ["try_action(custom_id)"],
        "support": ["explore_site(site_id)", "sandbox_list"],
        "guardrails": [
            "Registration is not validation; sandbox the returned custom action id before commit.",
            "Custom chemistry must be one real step with complete precursor SMILES; lead with the positive chemical case and record rejection rationale only for actions actually rejected.",
        ],
    },
    "try_action": {
        "primary_next": ["sandbox_list", "try_action(action_id) for another same-site competitor"],
        "support": ["sandbox_clear only if the visible comparison is polluted"],
        "guardrails": [
            "success=true is evidence only, not a commit decision.",
            "Do not commit blocked validation. For proof_required, add evidence or revise the action before considering an explicit validation_override.",
        ],
    },
    "sandbox_try": {
        "primary_next": ["sandbox_list"],
        "support": ["sandbox_clear only if the visible comparison is polluted"],
        "guardrails": [
            "Hidden legacy sandboxing is diagnostic; prefer try_action(action_id) in normal flow.",
        ],
    },
    "sandbox_list": {
        "primary_next": ["commit(idx=..., expected_action_id=..., reasoning=..., rejected=...)", "select(idx) then commit(...)"],
        "support": ["propose_action(...) for one more concrete rescue", "accept(..., force_accept_without_rescue=true) only with a no-actionable reason", "sandbox_clear"],
        "guardrails": [
            "select only marks the preferred attempt; commit still needs explicit reasoning.",
            "For terminal review, reject weak attempts explicitly before trying another concrete action or accepting with a no-actionable reason.",
            "sandbox_clear archives and clears the visible attempts, so use it only before a clean re-run.",
        ],
    },
    "commit": {
        "primary_next": ["next", "tree", "status"],
        "support": ["report after finalize"],
        "guardrails": [
            "Record selected action, rejected alternatives, sandbox evidence, and applied experience-card ids.",
        ],
    },
    "terminal": {
        "primary_next": ["route_sketch(..., terminal_review=True)", "accept(reason=...)"],
        "support": ["status", "tree"],
        "guardrails": [
            "Accept terminal only with explicit buyability, stability, or advanced-terminal rationale.",
            "For nontrivial advanced terminal, route_sketch comes before accept unless no credible mini-route exists.",
            "After route_sketch(..., terminal_review=True), accept is blocked until one route-sketch-derived custom action is sandboxed, unless force_accept_without_rescue and rescue_not_actionable_reason are supplied.",
            "skip marks the node terminal and should be reserved for blocked/no-viable-action cases.",
        ],
    },
}

REQUIRED_AUDIT_FIELDS = [
    "selected_action_id",
    "rejected_action_ids",
    "sandbox_evidence",
    "applied_experience_card_ids",
    "explicit_reasoning",
    "intended_deltas",
    "expected_ring_change",
    "changed_bonds",
    "preserved_anchors",
    "mechanistic_evidence",
    "validation_observations",
    "proof_obligations",
]


@lru_cache(maxsize=1)
def load_experience_cards() -> List[Dict[str, Any]]:
    with open(CARD_SOURCE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    cards = data.get("cards", [])
    if not isinstance(cards, list):
        return []
    return [card for card in cards if isinstance(card, dict) and card.get("id")]


def build_prompt_mount(
    stage: str,
    *,
    decision_context: Optional[Dict[str, Any]] = None,
    payload: Optional[Dict[str, Any]] = None,
    candidate: Optional[Dict[str, Any]] = None,
    attempt: Optional[Dict[str, Any]] = None,
    attempts: Optional[List[Dict[str, Any]]] = None,
    chemist_guidance: Optional[List[Dict[str, Any]]] = None,
    route_plan: Optional[Dict[str, Any]] = None,
    route_strategy: Optional[Dict[str, Any]] = None,
    max_cards: Optional[int] = None,
) -> Dict[str, Any]:
    """Return the short prompt mount for the current LLM interaction stage."""
    stage = _canonical_stage(stage)
    prompt_events = derive_prompt_events(
        stage,
        decision_context=decision_context,
        payload=payload,
        candidate=candidate,
        attempt=attempt,
        attempts=attempts,
        chemist_guidance=chemist_guidance,
        route_plan=route_plan,
        route_strategy=route_strategy,
    )
    event_tags = _tags_from_prompt_events(prompt_events)
    tags = _extract_tags(
        stage,
        decision_context=decision_context,
        payload=payload,
        candidate=candidate,
        attempt=attempt,
        attempts=attempts,
        chemist_guidance=chemist_guidance,
        route_plan=route_plan,
        route_strategy=route_strategy,
        prompt_events=prompt_events,
    )
    card_limit = _effective_max_cards(
        stage,
        prompt_events=prompt_events,
        tags=tags,
        explicit_max_cards=max_cards,
    )
    active_cards = _select_cards(
        tags,
        event_tags=event_tags,
        prompt_events=prompt_events,
        max_cards=card_limit,
    )
    self_prompt = list(STAGE_SELF_PROMPTS.get(stage, STAGE_SELF_PROMPTS["context_compact"]))
    if "action.intentional_attachment_placeholder" in prompt_events:
        self_prompt.insert(
            0,
            "A '*' dummy atom in a system precursor preview is an intentional attachment-site marker, not a real precursor or an incomplete-template verdict; complete the same disconnection with propose_action before validation.",
        )
    return {
        "stage": stage,
        "prompt_state": {
            "stage": stage,
            "events": prompt_events,
        },
        "policy_version": POLICY_VERSION,
        "card_source": CARD_SOURCE_NAME,
        "standing_rules": list(STANDING_RULES),
        "quality_guardrails": list(QUALITY_GUARDRAILS),
        "command_policy": _command_policy(stage),
        "active_experience_card_ids": [card["id"] for card in active_cards],
        "active_experience_cards": [_compact_card(card) for card in active_cards],
        "chemist_guidance": _compact_guidance_list(chemist_guidance),
        "route_plan_brief": _compact_route_plan(route_plan),
        "route_strategy_brief": _compact_route_strategy(route_strategy),
        "self_prompt": self_prompt,
        "required_audit_fields": list(REQUIRED_AUDIT_FIELDS),
        "matched_tags": sorted(tags),
    }


def build_prompt_brief(mount: Dict[str, Any]) -> Dict[str, Any]:
    """Project an internal prompt mount into the short LLM-facing payload.

    The full mount is useful for deterministic card selection and audit, but it
    repeats policy metadata that should not be read by the model at every step.
    This projection keeps only the stage, event state, next command hints, and
    the compact card text that the model can act on immediately.
    """
    prompt_state = mount.get("prompt_state") or {}
    command_policy = mount.get("command_policy") or {}
    cards = mount.get("active_experience_cards") or []
    stage = str(mount.get("stage", "") or "")
    events = list(prompt_state.get("events") or [])
    matched_tags = set(mount.get("matched_tags") or [])
    self_prompt = list(mount.get("self_prompt") or [])
    if stage not in DISCOVERY_STAGES:
        self_prompt = self_prompt[:2]
    brief = {
        "stage": stage,
        "events": events,
        "next_actions": list(command_policy.get("primary_next") or [])[:2],
        "quality_guardrails": _brief_quality_guardrails(stage, events, matched_tags),
        "active_experience_card_ids": list(mount.get("active_experience_card_ids") or []),
        "experience_prompts": [_compact_card(card) for card in cards],
        "chemist_guidance": list(mount.get("chemist_guidance") or [])[:2],
        "route_plan_brief": _brief_route_plan(mount.get("route_plan_brief") or {}, stage),
        "route_strategy_brief": _brief_route_strategy(
            mount.get("route_strategy_brief") or {},
            stage,
        ),
        "self_prompt": self_prompt,
    }
    audit_fields = _brief_required_audit_fields(stage, events, matched_tags)
    if audit_fields:
        brief["required_audit_fields"] = audit_fields
    return {key: value for key, value in brief.items() if value not in ("", [], {})}


def _brief_quality_guardrails(
    stage: str,
    events: List[str],
    tags: Set[str],
) -> List[str]:
    if stage in DISCOVERY_STAGES:
        return [
            QUALITY_GUARDRAILS[0],
            QUALITY_GUARDRAILS[1],
            QUALITY_GUARDRAILS[3],
            QUALITY_GUARDRAILS[4],
            QUALITY_GUARDRAILS[7],
            QUALITY_GUARDRAILS[2],
            QUALITY_GUARDRAILS[9],
        ]

    selected: List[str] = []
    active_events = set(events)
    if "validation.blocked" in active_events:
        selected.append(
            QUALITY_GUARDRAILS[18]
            if "system_error" in tags
            else QUALITY_GUARDRAILS[19]
        )
    elif "validation.proof_required" in active_events:
        selected.append(QUALITY_GUARDRAILS[17])
    elif "validation.inconclusive" in active_events:
        selected.append(QUALITY_GUARDRAILS[16])
    elif "validation.warning" in active_events:
        selected.append(QUALITY_GUARDRAILS[15])
    elif "validation.clear" in active_events:
        selected.append(QUALITY_GUARDRAILS[14])
    if _has_explicit_topology_signal(tags):
        selected.extend([QUALITY_GUARDRAILS[2], QUALITY_GUARDRAILS[11]])
    elif "custom_precursor" in tags:
        selected.append(QUALITY_GUARDRAILS[9])
    if {"atom_accounting", "atom_source", "multicomponent"} & tags:
        selected.append(QUALITY_GUARDRAILS[6])
    if {"protection", "compatibility"} & tags:
        selected.append(QUALITY_GUARDRAILS[7])
    if "strategy.route_mode_triage" in active_events or stage == "route_plan":
        selected.extend([QUALITY_GUARDRAILS[3], QUALITY_GUARDRAILS[4]])
    if stage == "terminal" or TERMINAL_RESCUE_EVENTS & active_events:
        selected.extend([QUALITY_GUARDRAILS[8], QUALITY_GUARDRAILS[12]])
    return list(dict.fromkeys(selected))[: 5 if stage == "terminal" else 4]


def _brief_route_plan(route_plan: Dict[str, Any], stage: str) -> Dict[str, Any]:
    if not route_plan:
        return {}
    brief = {
        key: route_plan.get(key)
        for key in ("id", "revision", "route_mode", "route_thesis")
        if route_plan.get(key) not in (None, "", [], {})
    }
    if stage in {"context_compact", "route_plan", "terminal"}:
        for key in ("key_disconnections", "protect_or_preserve", "strategic_risks"):
            values = list(route_plan.get(key, []) or [])[:2]
            if values:
                brief[key] = values
    if stage == "route_plan":
        values = list(route_plan.get("revision_triggers", []) or [])[:2]
        if values:
            brief["revision_triggers"] = values
    return brief


def _brief_route_strategy(route_strategy: Dict[str, Any], stage: str) -> Dict[str, Any]:
    if not route_strategy or stage not in {
        "context_compact",
        "reaction_sites",
        "route_sketch",
        "propose_action",
        "try_action",
        "sandbox_try",
        "sandbox_list",
        "commit",
        "terminal",
    }:
        return {}
    brief = {
        key: route_strategy.get(key)
        for key in ("id", "macro_strategy", "next_executable_step", "terminal_review")
        if route_strategy.get(key) not in (None, "", [], {}, False)
    }
    if stage in {"route_sketch", "terminal"} and route_strategy.get("problem"):
        brief["problem"] = route_strategy.get("problem")
    rescue_steps = []
    for step in list(route_strategy.get("rescue_steps") or [])[:2]:
        if not isinstance(step, dict):
            continue
        compact_step = {
            key: step.get(key)
            for key in (
                "step_idx",
                "reaction_name",
                "continuation_precursor",
                "status",
            )
            if step.get(key) not in (None, "", [], {})
        }
        if stage in {"route_sketch", "terminal"}:
            for key in ("target_smiles", "target_hint", "expected_precursors"):
                if step.get(key) not in (None, "", [], {}):
                    compact_step[key] = step.get(key)
        if compact_step:
            rescue_steps.append(compact_step)
    if rescue_steps:
        brief["rescue_steps"] = rescue_steps
    return brief


def _brief_required_audit_fields(
    stage: str,
    events: List[str],
    tags: Set[str],
) -> List[str]:
    active = set(events or [])
    fields: List[str] = []

    if stage in {"sandbox_list", "commit"}:
        fields.extend([
            "selected_action_id",
            "rejected_action_ids",
            "sandbox_evidence",
            "explicit_reasoning",
        ])
    if stage == "commit":
        fields.append("applied_experience_card_ids")

    if _has_explicit_topology_signal(tags):
        fields.extend([
            "intended_deltas",
            "expected_ring_change",
            "changed_bonds",
            "preserved_anchors",
            "mechanistic_evidence",
        ])

    if any(event.startswith("validation.") for event in active):
        fields.append("validation_observations")
    if {"validation.proof_required", "decision.commit_with_override"} & active:
        fields.append("proof_obligations")

    allowed = set(REQUIRED_AUDIT_FIELDS)
    return [field for field in dict.fromkeys(fields) if field in allowed]


def _command_policy(stage: str) -> Dict[str, List[str]]:
    stage = _canonical_stage(stage)
    policy = COMMAND_POLICIES.get(stage, DEFAULT_COMMAND_POLICY)
    return {key: list(value) for key, value in policy.items()}


def _canonical_stage(stage: str) -> str:
    return STAGE_ALIASES.get(stage, stage)


def _effective_max_cards(
    stage: str,
    *,
    prompt_events: List[str],
    tags: Set[str],
    explicit_max_cards: Optional[int],
) -> int:
    if explicit_max_cards is not None:
        return max(0, int(explicit_max_cards))
    active_events = set(prompt_events or [])
    if "strategy.advanced_terminal_rescue_requested" in active_events:
        return TERMINAL_RESCUE_MAX_EXPERIENCE_CARDS
    if {"decision.accept_terminal", "action.terminal_acceptance"} & active_events:
        return TERMINAL_RESCUE_MAX_EXPERIENCE_CARDS
    canonical_stage = _canonical_stage(stage)
    if canonical_stage == "terminal":
        return TERMINAL_MAX_EXPERIENCE_CARDS
    if canonical_stage in DISCOVERY_STAGES:
        return len(load_experience_cards())
    if _is_topology_audit_card_context(active_events, tags):
        return CUSTOM_TOPOLOGY_MAX_EXPERIENCE_CARDS
    return DEFAULT_MAX_EXPERIENCE_CARDS


def _compact_card(card: Dict[str, Any]) -> Dict[str, str]:
    return {
        "id": str(card.get("id", "")),
        "one_line": str(card.get("one_line", "")),
        "action_prompt": str(card.get("action_prompt", "")),
        "avoid": str(card.get("avoid", "")),
    }


def _compact_guidance_list(guidance: Optional[List[Dict[str, Any]]]) -> List[Dict[str, str]]:
    compact: List[Dict[str, str]] = []
    for item in guidance or []:
        if not isinstance(item, dict):
            continue
        guidance_id = str(item.get("id", "")).strip()
        summary = str(item.get("summary", "")).strip()
        if not guidance_id or not summary:
            continue
        compact.append({
            "id": guidance_id,
            "intent": str(item.get("intent", "") or "directive").strip()[:80],
            "summary": summary[:240],
        })
        if len(compact) >= 2:
            break
    return compact


def _compact_route_strategy(route_strategy: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(route_strategy, dict):
        return {}
    sketch_id = str(route_strategy.get("id", "") or route_strategy.get("route_sketch_id", "")).strip()
    macro = str(route_strategy.get("macro_strategy", "")).strip()
    next_step = str(route_strategy.get("next_executable_step", "")).strip()
    if not sketch_id or not macro:
        return {}
    brief = {
        "id": sketch_id,
        "macro_strategy": macro[:240],
    }
    if next_step:
        brief["next_executable_step"] = next_step[:120]
    problem = str(route_strategy.get("problem", "")).strip()
    if problem:
        brief["problem"] = problem[:160]
    if route_strategy.get("terminal_review"):
        brief["terminal_review"] = True
    rescue_steps = []
    for step in route_strategy.get("rescue_steps", []) or []:
        if not isinstance(step, dict):
            continue
        item = {"step_idx": step.get("step_idx", len(rescue_steps))}
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
        rescue_steps.append(item)
        if len(rescue_steps) >= 3:
            break
    if rescue_steps:
        brief["rescue_steps"] = rescue_steps
    return brief


def _compact_route_plan(route_plan: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(route_plan, dict):
        return {}
    plan_id = str(route_plan.get("id", "")).strip()
    thesis = str(route_plan.get("route_thesis", "")).strip()
    if not plan_id or not thesis:
        return {}
    brief: Dict[str, Any] = {
        "id": plan_id,
        "revision": int(route_plan.get("revision", 0) or 0),
        "route_thesis": thesis[:260],
    }
    route_mode = str(route_plan.get("route_mode", "")).strip()
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
            for item in route_plan.get(key, []) or []
            if str(item).strip()
        ][:limit]
        if items:
            brief[key] = items
    terminal_policy = str(route_plan.get("terminal_rescue_policy", "")).strip()
    if terminal_policy:
        brief["terminal_rescue_policy"] = terminal_policy[:180]
    reason = str(route_plan.get("last_revision_reason", "")).strip()
    if reason:
        brief["last_revision_reason"] = reason[:120]
    return brief


def derive_prompt_events(
    stage: str,
    *,
    decision_context: Optional[Dict[str, Any]] = None,
    payload: Optional[Dict[str, Any]] = None,
    candidate: Optional[Dict[str, Any]] = None,
    attempt: Optional[Dict[str, Any]] = None,
    attempts: Optional[List[Dict[str, Any]]] = None,
    chemist_guidance: Optional[List[Dict[str, Any]]] = None,
    route_plan: Optional[Dict[str, Any]] = None,
    route_strategy: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Derive compact prompt-state events from structured runtime payloads."""
    stage = _canonical_stage(stage)
    events: List[str] = []
    seen: Set[str] = set()

    _add_event(events, seen, f"stage.{_event_suffix(stage)}")
    if stage == "commit":
        _add_event(events, seen, "decision.commit_requested")

    _add_events_from_payload(events, seen, payload)
    _add_events_from_candidate(events, seen, candidate)
    _add_events_from_attempt(events, seen, attempt)
    if stage != "commit":
        for item in attempts or []:
            _add_events_from_attempt(events, seen, item)
    _add_events_from_chemist_guidance(events, seen, chemist_guidance)
    _add_events_from_route_plan(events, seen, route_plan, stage=stage)
    _add_events_from_route_strategy(events, seen, route_strategy)
    if stage != "commit":
        _add_events_from_attempt_set(events, seen, attempts)
    _add_events_from_decision_context(
        events,
        seen,
        decision_context,
        stage=stage,
        route_plan_active=bool(_compact_route_plan(route_plan)),
    )

    return events


def _select_cards(
    tags: Set[str],
    *,
    event_tags: Optional[Set[str]] = None,
    prompt_events: Optional[List[str]] = None,
    max_cards: int,
) -> List[Dict[str, Any]]:
    scored: List[tuple[int, int, Dict[str, Any]]] = []
    active_events = set(prompt_events or [])
    event_tag_set = event_tags or set()
    for order, card in enumerate(load_experience_cards()):
        card_id = str(card.get("id", ""))
        if not _card_activation_matches(card, tags, active_events):
            continue
        if card_id == "exp_forward_fail_requires_override" and not (
            "hard_fail" in tags
            or "validation.blocked" in active_events
        ):
            continue
        card_tags = {_normalize_tag(tag) for tag in card.get("tags", [])}
        if card_id == "exp_electron_poor_pyridine_electronic_state_strategy" and not (
            "electron_poor_pyridine" in tags or {"electron_poor", "pyridine"} <= tags
        ):
            continue
        if card_id == "exp_custom_topology_audit_gate" and not (
            "custom_precursor" in tags and _has_explicit_topology_signal(tags)
        ):
            continue
        if card_id == "exp_advanced_terminal_short_route_rescue" and not (
            TERMINAL_RESCUE_EVENTS & active_events
            or "advanced_terminal" in tags
            and {"stage.context_compact", "stage.terminal", "stage.route_sketch"} & active_events
        ):
            continue
        if card_id == "exp_route_mode_triage_before_first_plan" and not (
            "strategy.route_mode_triage" in active_events
            or "stage.route_plan" in active_events
        ):
            continue
        if card_id == "exp_global_route_plan_persistence" and not (
            "strategy.route_plan_active" in active_events
            and {
                "stage.context_compact",
                "stage.route_plan",
                "stage.reaction_sites",
                "stage.explore_site",
                "stage.route_sketch",
                "stage.propose_action",
                "stage.commit",
                "stage.terminal",
            }
            & active_events
        ):
            continue
        if card_id == "exp_route_plan_revision" and not (
            "strategy.route_plan_revised" in active_events
        ):
            continue
        if card_id == "exp_electron_poor_pyridine_electronic_state_strategy" and not (
            {
                "stage.context_compact",
                "stage.reaction_sites",
                "stage.route_plan",
                "stage.terminal",
            }
            & active_events
        ):
            continue
        overlap = card_tags & tags
        event_overlap = card_tags & event_tag_set
        trigger_overlap = {
            str(trigger)
            for trigger in card.get("triggers", []) or []
            if str(trigger) in active_events
        }
        if not overlap and not trigger_overlap:
            continue
        score = len(overlap) * 10 + len(event_overlap) * 5 + len(trigger_overlap) * 15
        # Cards tied to high-risk validation and custom flow should surface
        # when those exact tags are active.
        if card.get("id") == "exp_forward_fail_requires_override" and "hard_fail" in tags:
            score += 20
        if card.get("id") == "exp_custom_precursor_after_rejection" and "custom_precursor" in tags:
            score += 20
        if card.get("id") == "exp_custom_topology_audit_gate":
            if "custom_precursor" in tags and _has_explicit_topology_signal(tags):
                score += 40
            elif "route_sketch" in tags and _has_explicit_topology_signal(tags):
                score += 25
        if card.get("id") == "exp_paal_knorr_deep_ring_warning" and "paal-knorr" in tags:
            score += 20
        if card.get("id") == "exp_snar_electron_poor_heteroaryl" and "snar" in tags:
            score += 20
        if card.get("id") == "exp_route_mode_triage_before_first_plan":
            if "strategy.route_mode_triage" in active_events:
                score += 35
            elif {"stage.context_compact", "stage.route_plan"} & active_events:
                score += 20
            elif "route_mode" in tags:
                score += 15
        if card.get("id") == "exp_electron_poor_pyridine_electronic_state_strategy":
            if "electron_poor_pyridine" in tags:
                score += 35
            elif {"electron_poor", "pyridine"} <= tags:
                score += 25
            if "strategy.route_mode_triage" in active_events:
                score += 15
        if card.get("id") == "exp_advanced_terminal_short_route_rescue":
            if {
                "stage.terminal",
                "decision.accept_terminal",
                "action.terminal_acceptance",
                "strategy.advanced_terminal_rescue_requested",
            } & active_events:
                score += 30
            elif "stage.context_compact" in active_events and "advanced_terminal" in tags:
                score += 45
            elif "advanced_terminal" in tags:
                score += 15
        scored.append((score, -order, card))
    scored.sort(reverse=True)
    ranked = [card for _, _, card in scored]
    if _is_terminal_rescue_card_context(set(prompt_events or [])):
        return _select_terminal_rescue_cards(
            ranked,
            tags=tags,
            prompt_events=set(prompt_events or []),
            max_cards=max_cards,
        )
    if _is_topology_audit_card_context(active_events, tags):
        return _select_topology_audit_cards(
            ranked,
            tags=tags,
            prompt_events=active_events,
            max_cards=max_cards,
        )
    return ranked[:max_cards]


def _card_activation_matches(
    card: Dict[str, Any],
    tags: Set[str],
    active_events: Set[str],
) -> bool:
    activation = card.get("activation") or {}
    if not isinstance(activation, dict) or not activation:
        return True
    any_tags = {
        _normalize_tag(tag)
        for tag in activation.get("any_tags", []) or []
        if _normalize_tag(tag)
    }
    any_events = {
        str(event).strip().lower()
        for event in activation.get("any_events", []) or []
        if str(event).strip()
    }
    event_prefixes = [
        str(prefix).strip().lower()
        for prefix in activation.get("event_prefixes", []) or []
        if str(prefix).strip()
    ]
    if any_tags & tags or any_events & active_events:
        return True
    return any(
        event.startswith(prefix)
        for prefix in event_prefixes
        for event in active_events
    )


def _is_terminal_rescue_card_context(active_events: Set[str]) -> bool:
    return bool(TERMINAL_RESCUE_EVENTS & active_events)


def _is_topology_audit_card_context(active_events: Set[str], tags: Set[str]) -> bool:
    if not (
        {
            "stage.propose_action",
            "stage.try_action",
            "stage.sandbox_try",
            "stage.sandbox_list",
            "stage.commit",
        }
        & active_events
    ):
        return False
    custom_or_validation_active = (
        "action.custom_precursors" in active_events
        or "custom_precursor" in tags
        or bool({event for event in active_events if event.startswith("validation.")})
    )
    topology_active = _has_explicit_topology_signal(tags)
    return custom_or_validation_active and topology_active


def _has_explicit_topology_signal(tags: Set[str]) -> bool:
    return "topology_signal" in tags


def _select_topology_audit_cards(
    ranked: List[Dict[str, Any]],
    *,
    tags: Set[str],
    prompt_events: Set[str],
    max_cards: int,
) -> List[Dict[str, Any]]:
    if max_cards <= 0:
        return []
    by_id = {str(card.get("id", "")): card for card in ranked}
    selected: List[Dict[str, Any]] = []
    selected_ids: Set[str] = set()

    slot_ids = [
        "exp_custom_topology_audit_gate",
        "exp_template_pass_not_enough",
        "exp_custom_precursor_after_rejection",
    ]
    validation_events = {event for event in prompt_events if event.startswith("validation.")}
    if (
        "hard_fail" in tags
        or "validation.blocked" in validation_events
    ):
        slot_ids.insert(1, "exp_forward_fail_requires_override")
    if "strategy.route_plan_active" in prompt_events:
        slot_ids.append("exp_global_route_plan_persistence")
    if {"skeleton_imbalance", "multicomponent"} & tags:
        slot_ids.append("exp_multicomponent_complete_precursors")
    elif {"atom_accounting", "carbon_source"} & tags:
        slot_ids.append("exp_carbon_atom_accounting")

    for card_id in slot_ids:
        card = by_id.get(card_id)
        if card and card_id not in selected_ids:
            selected.append(card)
            selected_ids.add(card_id)
        if len(selected) >= max_cards:
            return selected[:max_cards]

    for card in ranked:
        card_id = str(card.get("id", ""))
        if card_id in selected_ids:
            continue
        selected.append(card)
        selected_ids.add(card_id)
        if len(selected) >= max_cards:
            break
    return selected


def _select_terminal_rescue_cards(
    ranked: List[Dict[str, Any]],
    *,
    tags: Set[str],
    prompt_events: Set[str],
    max_cards: int,
) -> List[Dict[str, Any]]:
    if max_cards <= 0:
        return []
    by_id = {str(card.get("id", "")): card for card in ranked}
    selected: List[Dict[str, Any]] = []
    selected_ids: Set[str] = set()

    for card_id in _terminal_rescue_slot_ids(tags, prompt_events):
        card = by_id.get(card_id)
        if card and card_id not in selected_ids:
            selected.append(card)
            selected_ids.add(card_id)
        if len(selected) >= max_cards:
            return selected[:max_cards]

    for card in ranked:
        card_id = str(card.get("id", ""))
        if card_id in selected_ids:
            continue
        selected.append(card)
        selected_ids.add(card_id)
        if len(selected) >= max_cards:
            break
    return selected


def _terminal_rescue_slot_ids(tags: Set[str], prompt_events: Set[str]) -> List[str]:
    slot_ids = [
        "exp_advanced_terminal_short_route_rescue",
        "exp_route_sketch_for_weak_action_space",
    ]
    custom_active = (
        "action.custom_precursors" in prompt_events
        or "stage.propose_action" in prompt_events
        or "custom_precursor" in tags
    )
    if custom_active:
        if HIGH_RISK_TOPOLOGY_CARD_TAGS & tags:
            slot_ids.append("exp_custom_topology_audit_gate")
        slot_ids.append("exp_custom_precursor_after_rejection")

    validation_events = {event for event in prompt_events if event.startswith("validation.")}
    if (
        "validation.blocked" in validation_events
        or "hard_fail" in tags
    ):
        slot_ids.append("exp_forward_fail_requires_override")
    elif validation_events or "forward_validation" in tags or "sandbox" in tags:
        slot_ids.append("exp_template_pass_not_enough")

    if "strategy.route_plan_active" in prompt_events:
        slot_ids.append("exp_global_route_plan_persistence")
    elif {"atom_accounting", "carbon_source", "amide", "oxidation"} & tags:
        slot_ids.append("exp_carbon_atom_accounting")
    elif {"skeleton_imbalance", "multicomponent"} & tags:
        slot_ids.append("exp_multicomponent_complete_precursors")
    elif {"protection", "deprotection", "free_amine"} & tags:
        slot_ids.append("exp_protection_is_tree_node")
    elif "stage.terminal" in prompt_events:
        slot_ids.append("exp_advanced_terminal_over_fake_deep")

    return slot_ids


def _extract_tags(
    stage: str,
    *,
    decision_context: Optional[Dict[str, Any]],
    payload: Optional[Dict[str, Any]],
    candidate: Optional[Dict[str, Any]],
    attempt: Optional[Dict[str, Any]],
    attempts: Optional[List[Dict[str, Any]]],
    chemist_guidance: Optional[List[Dict[str, Any]]] = None,
    route_plan: Optional[Dict[str, Any]] = None,
    route_strategy: Optional[Dict[str, Any]] = None,
    prompt_events: Optional[List[str]] = None,
) -> Set[str]:
    tags = {_normalize_tag(stage)}
    tags.update(_normalize_tag(tag) for tag in STAGE_TAGS.get(stage, []))
    tags.update(_tags_from_prompt_events(prompt_events or []))

    text_parts: List[str] = []
    text_parts.extend(_collect_molecule_context_text(decision_context))
    text_parts.extend(_collect_local_action_text(payload))
    text_parts.extend(_collect_local_action_text(candidate))
    text_parts.extend(_collect_local_action_text(attempt))
    text_parts.extend(_collect_text(_compact_guidance_list(chemist_guidance)))

    text = " ".join(text_parts).lower()
    tags.update(_derive_tags_from_text(text))

    if payload:
        tags.update(_derive_tags_from_payload(payload))
    if candidate:
        tags.update(_derive_tags_from_candidate(candidate))
    if attempt:
        tags.update(_derive_tags_from_attempt(attempt))
    if stage != "commit":
        for item in attempts or []:
            tags.update(_derive_tags_from_attempt(item))
    if _compact_route_plan(route_plan):
        tags.add("route_plan")
        route_mode = _normalize_tag(route_plan.get("route_mode", "")) if route_plan else ""
        if route_mode:
            tags.update({"route_mode", route_mode})
    if _compact_route_strategy(route_strategy):
        tags.update({"route_sketch", "strategic_rescue"})

    return {tag for tag in tags if tag}


def _tags_from_prompt_events(prompt_events: List[str]) -> Set[str]:
    tags: Set[str] = set()
    for event in prompt_events:
        tags.add(_normalize_tag(event))
        tags.add(_event_suffix(event))
        tags.update(_normalize_tag(tag) for tag in EVENT_TAGS.get(event, []))
    return {tag for tag in tags if tag}


def _add_events_from_chemist_guidance(
    events: List[str],
    seen: Set[str],
    guidance: Optional[List[Dict[str, Any]]],
) -> None:
    active = [item for item in (guidance or []) if isinstance(item, dict)]
    if not active:
        return
    _add_event(events, seen, "chemist.directive")
    for item in active:
        intent = str(item.get("intent", "")).lower()
        if item.get("site_hint"):
            _add_event(events, seen, "chemist.site_hint")
        if item.get("reaction_hint"):
            _add_event(events, seen, "chemist.reaction_hint")
        if item.get("precursors"):
            _add_event(events, seen, "chemist.precursor_hint")
        if item.get("terminal_hint") or "terminal" in intent:
            _add_event(events, seen, "chemist.terminal_hint")
        if "approval" in intent or "approve" in intent:
            _add_event(events, seen, "chemist.approval")


def _add_events_from_route_strategy(
    events: List[str],
    seen: Set[str],
    route_strategy: Optional[Dict[str, Any]],
) -> None:
    if not isinstance(route_strategy, dict) or not _compact_route_strategy(route_strategy):
        return
    _add_event(events, seen, "strategy.route_sketch_active")
    if route_strategy.get("terminal_review"):
        _add_event(events, seen, "strategy.advanced_terminal_rescue_requested")
    next_step = str(route_strategy.get("next_executable_step", "")).lower()
    if "propose" in next_step or "custom" in next_step:
        _add_event(events, seen, "strategy.route_sketch_requested")


def _add_events_from_route_plan(
    events: List[str],
    seen: Set[str],
    route_plan: Optional[Dict[str, Any]],
    *,
    stage: str,
) -> None:
    if not isinstance(route_plan, dict) or not _compact_route_plan(route_plan):
        return
    _add_event(events, seen, "strategy.route_plan_active")
    if stage == "route_plan" and str(route_plan.get("route_mode", "") or "").strip():
        _add_event(events, seen, "strategy.route_mode_triage")
    reason = str(route_plan.get("last_revision_reason", "")).lower()
    try:
        revision = int(route_plan.get("revision", 0) or 0)
    except (TypeError, ValueError):
        revision = 0
    if stage == "route_plan" and (revision > 0 or reason not in {"", "initial"}):
        _add_event(events, seen, "strategy.route_plan_revised")


def _add_events_from_attempt_set(
    events: List[str],
    seen: Set[str],
    attempts: Optional[List[Dict[str, Any]]],
) -> None:
    if not attempts:
        return
    weak_count = 0
    for attempt in attempts:
        validation = build_validation_contract(
            attempt.get("forward_validation") or {},
            validation_micro=attempt.get("validation_micro") or {},
            site_audit=attempt.get("site_audit") or {},
            execution_success=attempt.get("success"),
        )
        state = str((validation.get("decision_gate") or {}).get("state", ""))
        if attempt.get("success") is False or state in {"blocked", "proof_required"}:
            weak_count += 1
    if weak_count >= 2:
        _add_event(events, seen, "strategy.route_sketch_requested")


_LOCAL_ACTION_TEXT_KEYS = {
    "source",
    "source_label",
    "reaction_type",
    "reaction_name",
    "action_label",
    "candidate_label",
    "site_type",
    "site_hint",
    "risk_hint",
    "risk_tags",
    "role_pair",
    "bond_type",
    "bond_fg_context",
    "rationale_summary",
    "why_existing_actions_rejected",
    "why_existing_candidates_rejected",
    "intended_deltas",
    "expected_ring_change",
    "mechanistic_evidence",
    "reaction",
}


def _collect_local_action_text(value: Any) -> Iterable[str]:
    if not isinstance(value, dict):
        return []
    summary = value.get("action_summary") or value.get("candidate_summary") or {}
    source = summary if isinstance(summary, dict) and summary else value
    texts: List[str] = []
    for key in _LOCAL_ACTION_TEXT_KEYS:
        if key in source:
            texts.extend(_collect_text(source.get(key)))
    return texts


def _collect_molecule_context_text(value: Any) -> Iterable[str]:
    if not isinstance(value, dict):
        return []
    texts: List[str] = []
    for key in (
        "smiles",
        "molecule",
        "scaffold",
        "scaffold_tags",
        "functional_groups",
        "functional_group_brief",
        "fg_summary",
    ):
        if key in value:
            texts.extend(_collect_text(value.get(key)))
    return texts


def _collect_text(value: Any) -> Iterable[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        texts: List[str] = []
        for item in value.values():
            texts.extend(_collect_text(item))
        return texts
    if isinstance(value, list):
        texts = []
        for item in value:
            texts.extend(_collect_text(item))
        return texts
    return []


def _precursor_normalization_tags(raw: Any) -> Set[str]:
    if not isinstance(raw, dict):
        return set()
    if not raw.get("changed") and not raw.get("normalizations"):
        return set()
    return {
        "precursor_normalization",
        "organometallic_source_obligation",
        "organometallic",
        "metal_source",
    }


def _derive_tags_from_text(text: str) -> Set[str]:
    tags: Set[str] = set()
    if "electron-poor" in text or "electron_poor" in text or "electron poor" in text:
        tags.add("electron_poor")
    if "pyridine" in text or "pyridyl" in text or "nicotinate" in text or "pyridone" in text:
        tags.update({"pyridine", "heteroaryl"})
    if "pyridone" in text or "lactam" in text or "electronic-state" in text or "electronic state" in text:
        tags.update({"electronic_state_strategy", "scaffold_assembly", "route_mode"})
    if "scaffold assembly" in text or "ring construction" in text:
        tags.update({"scaffold_assembly", "route_mode"})
    if any(
        term in text
        for term in (
            "ring_closure",
            "ring closure",
            "ring opening",
            "ring_opening",
            "scaffold_edit",
            "scaffold edit",
            "new_fused_ring_system",
            "new_spiro_center",
            "new_bridged_system",
            "new_medium_ring",
            "new_macrocycle",
            "high_risk_topology_requires_independent_evidence",
        )
    ):
        tags.update({"topology", "ring_construction", "scaffold_edit"})
    if "fused" in text or "fused_ring" in text:
        tags.add("fused_scaffold")
        if any(term in text for term in ("heteroaryl", "pyridine", "aza", "indole")):
            tags.add("fused_heteroaryl")
    if "spiro" in text:
        tags.add("spiro_scaffold")
    if "bridged" in text:
        tags.add("bridged_scaffold")
    if "macrocycle" in text:
        tags.add("macrocycle_scaffold")
    if "late functionalization" in text or "late fgi" in text or "functional group interconversion" in text:
        tags.update({"late_functionalization", "route_mode"})
    if "terminal hides core" in text or "hidden core" in text or "core construction" in text:
        tags.update({"terminal_hides_core_problem", "advanced_terminal", "route_plan"})
    if "snar" in text or "n-nucleophile" in text:
        tags.update({"snar", "n_nucleophile", "heteroaryl"})
    if "paal" in text and "knorr" in text:
        tags.update({"paal-knorr", "ring_construction", "template_risk", "advanced_terminal", "deep_disconnection"})
    if "suzuki" in text:
        tags.update({"suzuki", "sp2_sp2", "convergent"})
    if "miyaura" in text or "borylation" in text:
        tags.update({"handle_timing", "suzuki"})
    if "halogenation" in text or "aryl_halide" in text or "fluoride" in text or "fluoro" in text:
        tags.update({"handle_timing", "halogenation"})
    if "heteroaryl_fluoride" in text or "heteroaryl fluoride" in text:
        tags.add("heteroaryl_fluoride")
    if (
        "pyridine" in tags
        and any(
            term in text
            for term in (
                "electron poor",
                "electron_poor",
                "chloro",
                "chloride",
                "nitro",
                "cyano",
                "ester",
                "difluoromethyl",
                "trifluoromethyl",
                "halogenation",
            )
        )
    ):
        tags.update({"electron_poor", "electron_poor_pyridine", "heteroaryl"})
    if "heteroaryl" in text or "azaindole" in text or "indole" in text or "pyrrole" in text:
        tags.update({"heteroaryl", "fused_heteroaryl"})
    if "amide" in text:
        tags.update({"amide", "atom_accounting", "convergent"})
    if "protection" in text or "boc" in text or "free amine" in text:
        tags.update({"protection", "compatibility", "free_amine"})
    if "skeleton_imbalance" in text:
        tags.update({"skeleton_imbalance", "multicomponent"})
    if (
        "custom_precursors" in text
        or "llm_proposed" in text
        or "propose_action" in text
        or "propose_candidate" in text
    ):
        tags.update({"custom_precursor", "llm_proposed", "action_rejection"})
    if "proof_required" in text or "proof obligation" in text or "proof_obligation" in text:
        tags.update({"forward_validation", "proof_required", "proof_obligation"})
    if (
        "precursor_normalization" in text
        or "organometallic_source_obligation" in text
        or "organometallic_precursor_normalized" in text
    ):
        tags.update({
            "precursor_normalization",
            "organometallic_source_obligation",
            "organometallic",
        })
    if "atom_mapping" in text:
        tags.update({"atom_mapping", "atom_source"})
    if "formed_bonds" in text:
        tags.update({"atom_mapping", "formed_bonds", "atom_source"})
    if "cleaved_bonds" in text:
        tags.update({"atom_mapping", "cleaved_bonds", "atom_source"})
    if "unmapped_product_atoms" in text:
        tags.update({"atom_mapping", "unmapped_product_atoms", "atom_source"})
    return tags


def _derive_tags_from_payload(payload: Dict[str, Any]) -> Set[str]:
    tags: Set[str] = set()
    for action in payload.get("actions", []) or []:
        if not isinstance(action, dict):
            continue
        local_text = " ".join(_collect_local_action_text(action)).lower()
        tags.update(_derive_tags_from_text(local_text))
        tags.update(_derive_tags_from_candidate(action))
    risk_tags = {
        _normalize_tag(tag)
        for tag in payload.get("risk_tags", []) or []
        if _normalize_tag(tag)
    }
    tags.update(risk_tags)
    if TOPOLOGY_SIGNAL_RISK_TAGS & risk_tags:
        tags.add("topology_signal")
    if payload.get("in_ring"):
        tags.update({"topology_signal", "topology", "ring_bond", "ring_construction"})
    if payload.get("terminal_review") is True:
        tags.update({"advanced_terminal", "terminal_rescue", "route_sketch"})
    return tags


def _derive_tags_from_candidate(candidate: Dict[str, Any]) -> Set[str]:
    tags: Set[str] = set()
    source = str(candidate.get("source", ""))
    if source == "custom_precursors":
        tags.update({"custom_precursor", "llm_proposed", "action_rejection", "audit"})
    if candidate.get("route_sketch_id") or candidate.get("route_strategy_brief"):
        tags.update({"route_sketch", "strategic_rescue"})
    if action_declares_topology_change(candidate):
        tags.update({"topology_signal", "topology", "ring_construction", "scaffold_edit"})
        expected = str(candidate.get("expected_ring_change", "") or "").lower()
        if "spiro" in expected:
            tags.add("spiro")
        if "fused" in expected:
            tags.add("fused_ring")
        if "bridged" in expected:
            tags.add("bridged")
        if "macro" in expected:
            tags.add("macrocycle")
        for delta in candidate.get("intended_deltas", []) or []:
            normalized = _normalize_tag(delta)
            if normalized:
                tags.add(normalized)
    tags.update(_precursor_normalization_tags(candidate.get("precursor_normalization")))
    risk_tags = {
        _normalize_tag(tag)
        for tag in candidate.get("risk_tags", []) or []
        if _normalize_tag(tag)
    }
    tags.update(risk_tags)
    if TOPOLOGY_SIGNAL_RISK_TAGS & risk_tags:
        tags.add("topology_signal")
    return tags


def _derive_tags_from_attempt(attempt: Dict[str, Any]) -> Set[str]:
    tags = {"sandbox"}
    validation = build_validation_contract(
        attempt.get("forward_validation") or {},
        validation_micro=attempt.get("validation_micro") or {},
        site_audit=attempt.get("site_audit") or {},
        execution_success=attempt.get("success"),
    )
    decision_gate = validation.get("decision_gate") or {}
    state = _normalize_tag(decision_gate.get("state", ""))
    if state and state != "unknown":
        tags.update({"forward_validation", state})
    if state == "blocked":
        tags.add("hard_fail")
    if state == "proof_required":
        tags.add("proof_obligation")
    for bucket_name, bucket_tag in (
        ("contradictions", "hard_fail"),
        ("proof_obligations", "proof_obligation"),
        ("evidence_gaps", "evidence_gap"),
        ("tool_limits", "tool_limit"),
        ("warnings", "warning"),
        ("system_errors", "system_error"),
    ):
        for item in validation.get(bucket_name, []) or []:
            code = _normalize_tag(item.get("code", ""))
            if code:
                tags.update({code, bucket_tag})
    summary = attempt.get("action_summary") or attempt.get("candidate_summary") or {}
    if summary.get("source") == "custom_precursors":
        tags.update({"custom_precursor", "llm_proposed", "action_rejection"})
    if isinstance(summary, dict):
        tags.update(_derive_tags_from_candidate(summary))
    tags.update(_precursor_normalization_tags(attempt.get("precursor_normalization")))
    tags.update(_precursor_normalization_tags(summary.get("precursor_normalization")))
    observations = validation.get("observations") or {}
    ring_deltas = list(observations.get("ring_deltas", []) or [])
    if ring_deltas:
        tags.update({"topology_signal", "topology", "ring_construction", "scaffold_edit"})
        tags.update(_normalize_tag(code) for code in ring_deltas if _normalize_tag(code))
    if observations.get("atom_mapping"):
        tags.update({"atom_mapping", "atom_source"})
    mechanism = validation.get("mechanism_interpretation") or {}
    if mechanism.get("label") and mechanism.get("state") != "unregistered_family":
        tags.update({"mechanism_interpretation", "reaction_topology"})
    return tags


def _add_event(events: List[str], seen: Set[str], event: str) -> None:
    event = event.strip().lower()
    if event and event not in seen:
        events.append(event)
        seen.add(event)


def _add_events_from_decision_context(
    events: List[str],
    seen: Set[str],
    decision_context: Optional[Dict[str, Any]],
    *,
    stage: str,
    route_plan_active: bool,
) -> None:
    if not decision_context:
        return
    text = " ".join(_collect_molecule_context_text(decision_context)).lower()
    if (
        stage in {"context_compact", "reaction_sites"}
        and not route_plan_active
        and
        any(term in text for term in ("pyridine", "pyridyl", "nicotinate"))
        and any(term in text for term in ("electron poor", "electron_poor", "chloro", "chloride", "ester", "nitro", "cyano", "difluoromethyl"))
    ):
        _add_event(events, seen, "strategy.route_mode_triage")
    if stage in {"reaction_sites", "explore_site"} and (
        "heteroaryl" in text or "azaindole" in text or "indole" in text
    ):
        _add_event(events, seen, "site.fused_heteroaryl_site_sensitive")
    action_count = 0
    for bond in decision_context.get("disconnectable_bonds", []) or []:
        action_count += len(bond.get("alternatives", []) or [])
        action_count += len(bond.get("smart_capping", []) or [])
    action_count += len(decision_context.get("fgi_options", []) or [])
    action_count += len(decision_context.get("custom_candidates", []) or [])
    complexity = decision_context.get("complexity") or {}
    try:
        cs_score = float(complexity.get("cs_score", 0) or 0)
    except (TypeError, ValueError):
        cs_score = 0.0
    if stage in {"context_compact", "reaction_sites"} and action_count <= 1 and cs_score >= CS_TRIVIAL:
        _add_event(events, seen, "strategy.action_space_weak")
        _add_event(events, seen, "strategy.route_sketch_requested")


def _add_events_from_payload(
    events: List[str],
    seen: Set[str],
    payload: Optional[Dict[str, Any]],
) -> None:
    if not payload:
        return
    if payload.get("validation_override"):
        _add_event(events, seen, "decision.commit_with_override")
    if payload.get("terminal_review"):
        _add_event(events, seen, "strategy.advanced_terminal_rescue_requested")
    if payload.get("site_audit"):
        _add_events_from_site_audit(events, seen, payload.get("site_audit") or {})
    site_map = payload.get("site_reaction_map") or []
    for site in site_map if isinstance(site_map, list) else []:
        if (site.get("reaction_count") or 0) > 1 or site.get("competition_hint"):
            _add_event(events, seen, "site.same_site_competition")
    if (payload.get("reaction_count") or 0) > 1 or payload.get("competition_hint"):
        _add_event(events, seen, "site.same_site_competition")
    if payload.get("in_ring"):
        _add_event(events, seen, "site.ring_bond_review")
    hint_text = " ".join(_collect_local_action_text(payload)).lower()
    if payload.get("same_core") or payload.get("site_retentive"):
        _add_event(events, seen, "site.same_core_custom_precursor")
    if payload.get("site_anchor_drift"):
        _add_event(events, seen, "site.site_anchor_drift")
    if payload.get("action_space_weak") or payload.get("route_incoherent"):
        _add_event(events, seen, "strategy.route_sketch_requested")
    if payload.get("open_action_requires_completion"):
        _add_event(events, seen, "action.intentional_attachment_placeholder")
        _add_event(events, seen, "strategy.route_sketch_requested")


def _add_events_from_candidate(
    events: List[str],
    seen: Set[str],
    candidate: Optional[Dict[str, Any]],
) -> None:
    if not candidate:
        return
    summary = candidate.get("action_summary") or candidate.get("candidate_summary") or {}
    source = str(candidate.get("source") or summary.get("source") or "")
    action_id = str(candidate.get("action_id") or candidate.get("candidate_id") or "")
    if source in {"bond", "fgi"}:
        _add_event(events, seen, "action.system_template")
    if source == "smart_capping":
        _add_event(events, seen, "action.smart_capping")
    if source == "terminal":
        _add_event(events, seen, "action.terminal_acceptance")
    if source == "custom_precursors" or action_id.startswith("custom:"):
        _add_event(events, seen, "action.custom_precursors")
    if _precursor_normalization_tags(candidate.get("precursor_normalization") or summary.get("precursor_normalization")):
        _add_event(events, seen, "action.precursor_normalization")
    if candidate.get("route_sketch_id") or summary.get("route_sketch_id"):
        _add_event(events, seen, "strategy.route_sketch_used_for_custom_action")
    risk_tags = {
        _normalize_tag(tag)
        for tag in candidate.get("risk_tags", []) or summary.get("risk_tags", []) or []
    }
    if "intentional_attachment_placeholder" in risk_tags:
        _add_event(events, seen, "action.intentional_attachment_placeholder")
    if (
        candidate.get("duplicate_of")
        or summary.get("duplicate_of")
        or "duplicates_existing_candidate" in risk_tags
        or "duplicates_existing_action" in risk_tags
    ):
        _add_event(events, seen, "action.duplicates_existing_action")


def _add_events_from_attempt(
    events: List[str],
    seen: Set[str],
    attempt: Optional[Dict[str, Any]],
) -> None:
    if not attempt:
        return
    if "success" in attempt:
        _add_event(
            events,
            seen,
            "sandbox.success" if attempt.get("success") else "sandbox.failure",
        )
    _add_events_from_candidate(
        events,
        seen,
        attempt.get("action_summary") or attempt.get("candidate_summary") or attempt,
    )
    if _precursor_normalization_tags(attempt.get("precursor_normalization")):
        _add_event(events, seen, "action.precursor_normalization")
    if attempt.get("site_audit"):
        _add_events_from_site_audit(events, seen, attempt.get("site_audit") or {})

    validation = build_validation_contract(
        attempt.get("forward_validation") or {},
        validation_micro=attempt.get("validation_micro") or {},
        site_audit=attempt.get("site_audit") or {},
        execution_success=attempt.get("success"),
    )
    state = _event_suffix((validation.get("decision_gate") or {}).get("state", ""))
    if state and state != "unknown":
        _add_event(events, seen, f"validation.{state}")
    for bucket_name in (
        "contradictions",
        "proof_obligations",
        "evidence_gaps",
        "tool_limits",
        "warnings",
        "system_errors",
    ):
        for item in validation.get(bucket_name, []) or []:
            code = _event_suffix(item.get("code", ""))
            if code:
                _add_event(events, seen, f"validation.{code}")


def _add_events_from_site_audit(
    events: List[str],
    seen: Set[str],
    site_audit: Dict[str, Any],
) -> None:
    summary = str(site_audit.get("summary", "") or "").lower()
    if "drift" in summary or site_audit.get("site_anchor_drift"):
        _add_event(events, seen, "site.site_anchor_drift")
    if "missing" in summary or site_audit.get("missing_evidence"):
        _add_event(events, seen, "site.site_retention_missing_evidence")


def _event_suffix(value: Any) -> str:
    text = _normalize_tag(value)
    return text.replace("_", "_")


def _normalize_tag(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = text.replace("-", "_")
    text = re.sub(r"[^a-z0-9_]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    if text == "paal_knorr":
        return "paal-knorr"
    return text
