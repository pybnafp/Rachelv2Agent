import json
from typing import Any


def _f(name: str, desc: str, props: dict, required: list[str] | None = None) -> dict:
    return {"type": "function", "function": {
        "name": name, "description": desc,
        "parameters": {"type": "object", "properties": props, "required": required or []}}}


TOOL_SCHEMAS: list[dict] = [
    _f("init", "Create a new retrosynthesis session for the target molecule.",
       {"target": {"type": "string", "description": "target SMILES"},
        "name": {"type": "string"}, "max_depth": {"type": "integer"},
        "max_steps": {"type": "integer"}, "terminal_cs_threshold": {"type": "number"}}, ["target"]),
    _f("next", "Get the next active molecule context (auto-passes trivial terminals).", {}),
    _f("context", "Get current context. detail: compact|structure|full|status|tree.",
       {"detail": {"type": "string", "enum": ["compact", "structure", "full", "status", "tree"]},
        "bond_offset": {"type": "integer"}, "bond_limit": {"type": "integer"},
        "fgi_offset": {"type": "integer"}, "fgi_limit": {"type": "integer"}}),
    _f("guide", "Record chemist natural-language guidance for the active node.",
       {"text": {"type": "string"}, "intent": {"type": "string"},
        "site_hint": {"type": "string"}, "reaction_hint": {"type": "string"},
        "precursors": {"type": "array", "items": {"type": "string"}},
        "constraints": {"type": "string"}, "terminal_hint": {"type": "string"},
        "summary": {"type": "string"}}, ["text"]),
    _f("route_plan", "Set or revise the persistent global route thesis.",
       {"route_thesis": {"type": "string"}, "route_mode": {"type": "string"},
        "key_disconnections": {"type": "array", "items": {"type": "string"}},
        "preferred_precursor_logic": {"type": "string"}, "protect_or_preserve": {"type": "string"},
        "mode_evidence": {"type": "string"}, "strategic_risks": {"type": "array", "items": {"type": "string"}},
        "revision_triggers": {"type": "array", "items": {"type": "string"}},
        "terminal_rescue_policy": {"type": "string"}, "revision_reason": {"type": "string"}},
       ["route_thesis"]),
    _f("route_sketch", "Record a short strategy sketch when the action-space is weak.",
       {"problem": {"type": "string"}, "macro_strategy": {"type": "string"},
        "key_disconnections": {"type": "array", "items": {"type": "string"}},
        "rejected_action_space_reason": {"type": "string"},
        "next_executable_step": {"type": "string"}, "terminal_review": {"type": "boolean"},
        "summary": {"type": "string"}, "continuation_steps": {"type": "array", "items": {"type": "object"}}},
       ["problem"]),
    _f("reaction_sites", "First-layer site-first grouped action menu for the active molecule.", {}),
    _f("explore_site", "Expand all candidate actions competing at one real reaction site.",
       {"site_id": {"type": "string"}}, ["site_id"]),
    _f("try_action", "Sandbox-validate one action-space entry by action_id.",
       {"action_id": {"type": "string"}}, ["action_id"]),
    _f("propose_action", "Register an LLM-proposed custom precursor action, then try_action it.",
       {"strategy_id": {"type": "string"}, "precursors": {"type": "array", "items": {"type": "string"}},
        "reagents": {"type": "array", "items": {"type": "string"}},
        "reaction_type": {"type": "string"}, "reaction_id": {"type": "string"},
        "reaction_name": {"type": "string"}, "action_label": {"type": "string"},
        "why_existing_actions_rejected": {"type": "string"}, "rationale_summary": {"type": "string"},
        "route_sketch_id": {"type": "string"}, "continuation_id": {"type": "string"},
        "risk_tags": {"type": "array", "items": {"type": "string"}},
        "intended_deltas": {"type": "array", "items": {}}, "expected_ring_change": {"type": "string"},
        "changed_bonds": {"type": "array", "items": {}}, "preserved_anchors": {"type": "array", "items": {}},
        "mechanistic_evidence": {"type": "array", "items": {"type": "string"}},
        "family_evidence": {"type": "object"}, "experience_card_hints": {"type": "array", "items": {}}},
       ["precursors"]),
    _f("sandbox_list", "List sandbox attempt history grouped by site/reaction.", {}),
    _f("sandbox_clear", "Clear all sandbox attempts.", {}),
    _f("select", "Select one sandbox attempt by index for commit.",
       {"idx": {"type": "integer"}}, ["idx"]),
    _f("commit", "Commit the selected sandbox attempt into the route tree with reasoning.",
       {"idx": {"type": "integer"}, "expected_action_id": {"type": "string"},
        "reasoning": {"type": "string"}, "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "rejected": {"type": "array", "items": {}}, "validation_override": {"type": "object"},
        "route_plan_alignment": {"type": "string"}, "route_plan_note": {"type": "string"}},
       ["idx", "reasoning"]),
    _f("accept", "Mark the active molecule as a terminal starting material with reason.",
       {"reason": {"type": "string"}, "rescue_not_actionable_reason": {"type": "string"},
        "force_accept_without_rescue": {"type": "boolean"}}, ["reason"]),
    _f("review_terminal", "Requeue an existing terminal leaf for normal review.",
       {"smiles": {"type": "string"}, "reason": {"type": "string"}, "additional_steps": {"type": "integer"}},
       ["smiles", "reason"]),
    _f("skip", "Skip the active molecule with reason.", {"reason": {"type": "string"}}, ["reason"]),
    _f("tree", "Print the current synthesis tree with terminal/pending counts.", {}),
    _f("status", "Show orchestrator status.", {}),
    _f("continuation_status", "Inspect active multi-step strategy continuations.", {}),
    _f("continuation_abort", "Close a pending continuation with an explicit reason.",
       {"continuation_id": {"type": "string"}, "reason": {"type": "string"}}, ["continuation_id"]),
    _f("finalize", "Finalize the route orchestration.", {"summary": {"type": "string"}}, ["summary"]),
    _f("report", "Generate the forward-synthesis report text.", {}),
    _f("export", "Export all artifacts (report/tree/visualization/terminals/session).",
       {"name": {"type": "string"}, "output_dir": {"type": "string"}}),
    _f("smart_cap", "Suggest template-free capping for a bond.",
       {"bond_idx": {"type": "integer"}, "smiles": {"type": "string"}, "bond": {"type": "array", "items": {"type": "integer"}},
        "max": {"type": "integer"}}),
    _f("custom_cap", "Apply LLM-defined caps to a bond.",
       {"cap_i": {"type": "string"}, "cap_j": {"type": "string"},
        "bond_idx": {"type": "integer"}, "smiles": {"type": "string"},
        "bond": {"type": "array", "items": {"type": "integer"}},
        "reaction_type": {"type": "string"}}, ["cap_i", "cap_j"]),
    _f("read_doc", "Read a section of workflow.md or experience_cards.md on demand.",
       {"doc": {"type": "string", "enum": ["workflow", "experience"]},
        "section": {"type": "string", "description": "optional section title filter"}}, ["doc"]),
    _f("finish", "Signal normal completion after export. Provide a short route summary.",
       {"summary": {"type": "string"}}, ["summary"]),
]


def truncate_result(obj: Any, limit: int = 8192) -> str:
    s = json.dumps(obj, ensure_ascii=False, default=str)
    if len(s) <= limit:
        return s
    return s[:limit] + f"\n...[TRUNCATED {len(s)-limit} chars; use finer-grained commands to re-fetch details]"


def execute_tool(retro, name: str, args: dict, doc_reader) -> dict:
    if name == "finish":
        return {"ok": True, "finished": True}
    if name == "read_doc":
        if doc_reader is None:
            return {"error": "doc reader not configured"}
        return doc_reader.read(args.get("doc", ""), args.get("section", ""))
    return retro.execute(name, args)
