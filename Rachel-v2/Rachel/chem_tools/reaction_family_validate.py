"""Reaction-family proof obligations for topology-changing steps.

This module translates a proposed reaction family into validation obligations.
It does not prove synthetic feasibility by itself. Registered family names are
optional hints; declared atom-source, tether, and anchor evidence must remain
visible even when the name is unregistered.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from .validation_findings import make_finding
from .topology_intent import action_declares_topology_change


def _family_category(reaction_category: Optional[str]) -> str:
    return (reaction_category or "").lower().replace("-", "_").replace(" ", "_")


def _has_any(text: str, needles: Iterable[str]) -> bool:
    return any(needle in text for needle in needles)


def _has_action_token(text: str, tokens: Iterable[str]) -> bool:
    words = {word for word in text.split("_") if word}
    return bool(words & set(tokens))


def _has_complex_ring_delta(ring_topology: Dict[str, Any]) -> bool:
    delta_codes = set(ring_topology.get("delta_codes", []) or [])
    return bool(
        delta_codes
        & {
            "new_fused_ring_system",
            "new_spiro_center",
            "new_bridged_system",
            "new_macrocycle",
            "new_medium_ring",
            "ring_system_merge",
        }
    )


def _delta_codes(payload: Optional[Dict[str, Any]]) -> Set[str]:
    if not isinstance(payload, dict):
        return set()
    return {str(code) for code in (payload.get("delta_codes", []) or []) if str(code)}


def _compact_family_evidence(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    return {
        str(key): value
        for key, value in raw.items()
        if value not in (None, "", [], {})
    }


_EVIDENCE_KEY_ALIASES = {
    "dipole": ("dipole", "dipole_atom_source", "one_three_dipole"),
    "dipolarophile": (
        "dipolarophile",
        "dipolarophile_atom_source",
        "alkene_partner",
    ),
    "regiochemistry_rationale": (
        "regiochemistry_rationale",
        "regioselectivity_rationale",
        "regioselectivity",
    ),
    "stereochemistry_rationale": (
        "stereochemistry_rationale",
        "stereoselectivity_rationale",
        "stereochemistry",
    ),
}


def _family_evidence_summary(
    raw: Any,
    required_keys: Iterable[str],
) -> Dict[str, Any]:
    family_evidence = _compact_family_evidence(raw)
    required = list(dict.fromkeys(str(key) for key in required_keys if str(key)))
    if not required:
        provided_keys = list(family_evidence)
        return {
            "state": "provided_unprofiled" if provided_keys else "not_required",
            "provided_keys": provided_keys,
            "missing_keys": [],
            "provided": dict(family_evidence),
            "required_keys": [],
            "missing_evidence_codes": [],
        }

    provided_keys: List[str] = []
    missing_keys: List[str] = []
    provided: Dict[str, Any] = {}
    for key in required:
        aliases = _EVIDENCE_KEY_ALIASES.get(key, (key,))
        matched = next((alias for alias in aliases if alias in family_evidence), "")
        if matched:
            provided_keys.append(matched)
            provided[matched] = family_evidence[matched]
        else:
            missing_keys.append(key)
    if missing_keys and provided_keys:
        state = "partial"
    elif missing_keys:
        state = "missing"
    else:
        state = "provided"
    return {
        "state": state,
        "provided_keys": provided_keys,
        "missing_keys": missing_keys,
        "provided": provided,
        "required_keys": required,
        "missing_evidence_codes": ["family_evidence_missing"] if missing_keys else [],
    }


_PRESERVE_CODES = [
    "skeleton_imbalance",
    "severe_imbalance",
    "olefination_lacks_intramolecular_tether_proof",
    "olefination_ring_closure_template_miss",
    "rcm_requires_single_diene_precursor",
    "new_fused_medium_ring_requires_evidence",
    "new_fused_ring_requires_evidence",
    "new_spiro_center_requires_evidence",
    "new_bridged_system_requires_evidence",
    "new_macrocycle_requires_evidence",
    "apparent_scaffold_jump",
]


def _profile(
    *,
    family_key: str,
    family_class: str,
    allowed_deltas: Iterable[str],
    required_evidence: Iterable[str],
    evidence_keys: Iterable[str] = (),
    forbidden_deltas: Iterable[str] = (),
    risk_level: str = "medium",
) -> Dict[str, Any]:
    return {
        "family_key": family_key,
        "family_class": family_class,
        "allowed_deltas": set(allowed_deltas),
        "forbidden_deltas": set(forbidden_deltas),
        "required_evidence": list(required_evidence),
        "evidence_keys": list(evidence_keys),
        "risk_level": risk_level,
    }


def _family_profile(
    cat: str,
    action_context: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Return broad family interpretation rules.

    These profiles are not executable reaction templates. They only describe
    which graph/ring/FG deltas a named family can plausibly explain and what
    proof the LLM should provide before treating that explanation as adequate.
    """
    cat = _family_category(cat)
    action_context = action_context or {}
    family_evidence = _compact_family_evidence(action_context.get("family_evidence"))
    evidence_keys = set(family_evidence)
    common_fg = {
        "fg_count_change",
        "mapped_bond_order_change",
        "protecting_group_added",
        "protecting_group_removed",
        "halogen_added",
        "halogen_removed",
        "nitro_to_amine",
        "carbonyl_to_alcohol",
        "alcohol_to_carbonyl",
        "alcohol_to_halide",
        "halide_to_alcohol",
    }
    closure = {
        "ring_count_increase",
        "ring_system_merge",
        "mapped_heavy_bond_formation",
        "mapped_topological_distance_change",
        "ring_bond_edit",
    }
    opening = {
        "ring_count_decrease",
        "mapped_heavy_bond_cleavage",
        "mapped_topological_distance_change",
        "ring_bond_edit",
    }
    high_risk = {
        "new_fused_ring_system",
        "new_spiro_center",
        "new_bridged_system",
        "new_medium_ring",
        "new_macrocycle",
    }

    if _has_any(cat, ("epoxidation", "aziridination", "cyclopropanation")):
        return _profile(
            family_key="small_ring_formation",
            family_class="small_ring_formation",
            allowed_deltas={
                "fragment_merge",
                "ring_count_increase",
                "ring_system_merge",
                "new_strained_small_ring",
                "mapped_heavy_bond_formation",
                "mapped_bond_order_change",
                "ring_bond_edit",
                "fg_count_change",
            },
            forbidden_deltas=high_risk - {"new_strained_small_ring"},
            required_evidence=[
                "alkene or equivalent small-ring precursor motif",
                "atom-source proof for both new small-ring bonds",
            ],
            evidence_keys=[
                "precursor_motif",
                "atom_source",
            ],
            risk_level="medium",
        )

    if _has_any(cat, ("opening", "hydrolysis")) and _has_any(cat, ("epoxide", "lactone", "lactam", "ring")):
        return _profile(
            family_key="ring_opening",
            family_class="ring_opening",
            allowed_deltas=opening | common_fg,
            required_evidence=[
                "strained or activated ring-opening motif",
                "nucleophile/hydrolysis or cleavage-site rationale",
            ],
            evidence_keys=[
                "activated_ring",
                "cleavage_site_rationale",
            ],
            risk_level="medium",
        )

    if _has_any(cat, ("lactonization", "lactamization", "intramolecular_sn2", "heterocycle_formation")):
        return _profile(
            family_key="intramolecular_ring_closure",
            family_class="intramolecular_ring_closure",
            allowed_deltas=closure | common_fg | {"halogen_removed", "new_medium_ring"},
            required_evidence=[
                "same-precursor tether proof",
                "new ring-bond atom-source proof",
                "leaving-group or activation rationale",
            ],
            evidence_keys=[
                "same_precursor_tether",
                "new_ring_bond_atom_source",
                "leaving_group_or_activation_rationale",
            ],
            risk_level="high",
        )

    if (
        "intramolecular" in cat
        and _has_any(
            cat,
            (
                "aryl_lithium",
                "aryllithium",
                "organolithium",
                "organometallic",
                "nucleophilic_addition",
                "carbonyl_addition",
                "aldehyde_addition",
                "addition_to_aldehyde",
                "addition_to_carbonyl",
            ),
        )
    ):
        return _profile(
            family_key="intramolecular_nucleophilic_addition_cyclization",
            family_class="intramolecular_ring_closure",
            allowed_deltas=closure
            | common_fg
            | high_risk
            | {
                "new_junction_atoms",
                "halogen_removed",
                "carbonyl_to_alcohol",
                "halide_to_alcohol",
            },
            required_evidence=[
                "same-precursor tether proof",
                "organometallic or nucleophile generation site",
                "carbonyl electrophile identity",
                "atom-source proof for the new C-C ring bond",
                "retained handle and substituent position proof",
            ],
            evidence_keys=[
                "same_precursor_tether",
                "organometallic_site",
                "carbonyl_electrophile",
                "new_ring_bond_atom_source",
                "preserved_anchor_positions",
            ],
            risk_level="high",
        )

    if "michael" in cat and "intramolecular" in cat:
        return _profile(
            family_key="intramolecular_michael_cyclization",
            family_class="intramolecular_ring_closure",
            allowed_deltas=closure | common_fg,
            required_evidence=[
                "same-precursor Michael donor/acceptor tether proof",
                "regioselectivity and enolate/source rationale",
            ],
            evidence_keys=[
                "michael_donor",
                "michael_acceptor",
                "same_precursor_tether",
                "regioselectivity_rationale",
            ],
            risk_level="high",
        )

    if "robinson" in cat:
        return _profile(
            family_key="robinson_annulation",
            family_class="annulation",
            allowed_deltas=closure | common_fg | {"fragment_merge"},
            required_evidence=[
                "Michael donor/acceptor role assignment",
                "aldol closure regioselectivity",
                "atom-source proof for the new cyclohexenone ring bond",
            ],
            evidence_keys=[
                "michael_donor",
                "michael_acceptor",
                "aldol_closure_regioselectivity",
                "new_ring_bond_atom_source",
            ],
            risk_level="high",
        )

    is_dipolar = bool(
        {"dipole", "dipolarophile"} & evidence_keys
        or _has_any(
            cat,
            (
                "1,3_dipolar",
                "1_3_dipolar",
                "one_three_dipolar",
                "nitrile_oxide",
                "dipolar_cycloaddition",
                "3+2",
                "[3+2]",
            ),
        )
    )
    if is_dipolar:
        return _profile(
            family_key="one_three_dipolar_cycloaddition",
            family_class="cycloaddition",
            allowed_deltas=closure | common_fg | {"fragment_merge"},
            required_evidence=[
                "1,3-dipole/dipolarophile role assignment",
                "two formed-bond atom-source map",
                "cycloaddition regioselectivity and, when applicable, stereochemistry rationale",
            ],
            evidence_keys=[
                "dipole",
                "dipolarophile",
                "new_ring_bond_atom_source",
                "regiochemistry_rationale",
            ],
            risk_level="high",
        )

    if "diels_alder" in cat:
        return _profile(
            family_key="diels_alder_cycloaddition",
            family_class="cycloaddition",
            allowed_deltas=closure | common_fg | {"fragment_merge"},
            required_evidence=[
                "diene/dienophile role assignment",
                "cycloaddition regiochemistry and stereochemistry rationale",
            ],
            evidence_keys=[
                "diene",
                "dienophile",
                "regiochemistry_rationale",
                "stereochemistry_rationale",
            ],
            risk_level="high",
        )

    if "cycloaddition" in cat:
        return _profile(
            family_key="generic_cycloaddition",
            family_class="cycloaddition",
            allowed_deltas=closure | common_fg | {"fragment_merge"},
            required_evidence=[
                "cycloaddition component-role assignment",
                "formed-bond atom-source map",
                "regiochemistry and stereochemistry rationale",
            ],
            evidence_keys=[
                "component_roles",
                "new_ring_bond_atom_source",
                "regiochemistry_rationale",
                "stereochemistry_rationale",
            ],
            risk_level="high",
        )

    if "electrocyclization" in cat:
        return _profile(
            family_key="electrocyclization",
            family_class="pericyclic",
            allowed_deltas=closure | common_fg | {"mapped_bond_order_change"},
            required_evidence=[
                "conjugated polyene electron-count rationale",
                "allowed thermal/photochemical mode rationale",
            ],
            evidence_keys=[
                "conjugated_polyene",
                "electron_count",
                "thermal_or_photochemical_mode",
            ],
            risk_level="high",
        )

    if "beckmann" in cat:
        return _profile(
            family_key="beckmann_rearrangement",
            family_class="ring_expansion",
            allowed_deltas=closure | opening | common_fg | {"new_medium_ring"},
            required_evidence=[
                "oxime or activated imine precursor motif",
                "migration center and migrating-bond proof",
            ],
            evidence_keys=[
                "oxime_or_activated_imine",
                "migration_center",
                "migrating_bond",
            ],
            risk_level="high",
        )

    if _has_any(cat, ("baeyer_villiger", "baeyer", "villiger")):
        return _profile(
            family_key="baeyer_villiger_oxidation",
            family_class="ring_expansion",
            allowed_deltas=closure | opening | common_fg | {"fragment_merge", "new_medium_ring"},
            required_evidence=[
                "ketone/peracid or oxygen-insertion motif",
                "migratory aptitude and insertion-site proof",
            ],
            evidence_keys=[
                "ketone_or_peracid_motif",
                "oxygen_insertion_site",
                "migratory_aptitude",
            ],
            risk_level="high",
        )

    if _has_any(cat, ("rcm", "ring_closing_metathesis", "metathesis")):
        return _profile(
            family_key="ring_closing_metathesis",
            family_class="metathesis",
            allowed_deltas=closure | common_fg | {"new_medium_ring", "mapped_bond_order_change"},
            required_evidence=[
                "single tethered diene precursor",
                "mapped alkene termini in the same precursor",
            ],
            evidence_keys=[
                "single_tethered_diene",
                "alkene_termini",
            ],
            risk_level="high",
        )

    if _has_any(cat, ("hwe", "horner", "wadsworth", "emmons", "wittig", "julia", "peterson")):
        return _profile(
            family_key="olefination",
            family_class="olefination",
            allowed_deltas={"fragment_merge", "mapped_bond_order_change"} | common_fg,
            forbidden_deltas=high_risk | {"ring_system_merge"},
            required_evidence=[
                "carbonyl/ylide or phosphonate partner role assignment",
                "alkene-formation atom-source proof",
            ],
            evidence_keys=[
                "carbonyl_partner",
                "olefination_reagent",
                "alkene_atom_source",
            ],
            risk_level="medium",
        )

    if _has_any(cat, ("claisen", "cope", "wagner", "pinacol", "curtius", "rearrangement")):
        return _profile(
            family_key="rearrangement",
            family_class="rearrangement",
            allowed_deltas={
                "mapped_heavy_bond_formation",
                "mapped_heavy_bond_cleavage",
                "mapped_topological_distance_change",
                "mapped_bond_order_change",
            } | common_fg,
            required_evidence=[
                "migrating bond or sigma-bond shift proof",
                "family-specific rearrangement motif",
            ],
            evidence_keys=[
                "migration_center",
                "migrating_bond",
                "rearrangement_motif",
            ],
            risk_level="high",
        )

    if _has_action_token(cat, ("protect", "protection", "deprotect", "deprotection")):
        return _profile(
            family_key="protection_deprotection",
            family_class="functional_group_edit",
            allowed_deltas=common_fg | {"fragment_merge"},
            required_evidence=[
                "protected/unprotected functional-group identity",
                "orthogonality or condition rationale",
            ],
            evidence_keys=[
                "protecting_group",
                "deprotected_functional_group",
                "condition_rationale",
            ],
            risk_level="low",
        )

    if _has_any(cat, ("oxidation", "reduction", "hydrogenation", "halogenation", "dehalogenation", "fgi")):
        return _profile(
            family_key="functional_group_interconversion",
            family_class="functional_group_edit",
            allowed_deltas=common_fg | {"mapped_bond_order_change"},
            required_evidence=[
                "functional-group before/after identity",
                "chemoselectivity rationale for retained handles",
            ],
            evidence_keys=[
                "before_functional_group",
                "after_functional_group",
                "chemoselectivity_rationale",
            ],
            risk_level="low",
        )

    declared_deltas = {
        str(item or "").strip().lower()
        for item in (action_context.get("intended_deltas") or [])
        if str(item or "").strip()
    }
    declared_high_risk = bool(
        declared_deltas & high_risk
        or evidence_keys
        & {"junction_source", "bridgehead_source", "high_risk_topology_proof"}
    )
    if action_declares_topology_change(action_context) and declared_high_risk:
        return _profile(
            family_key="high_risk_topology",
            family_class="high_risk_topology",
            allowed_deltas=closure | common_fg | high_risk,
            required_evidence=[
                "atom-mapped junction or bridgehead source proof",
                "mechanistic high-risk topology proof",
            ],
            evidence_keys=[],
            risk_level="critical",
        )

    return None


def _build_family_interpretation(
    *,
    cat: str,
    precursors: Sequence[str],
    ring_topology: Dict[str, Any],
    graph_delta: Optional[Dict[str, Any]],
    fg_delta: Optional[Dict[str, Any]],
    template_execution: Dict[str, Any],
    action_context: Dict[str, Any],
) -> Dict[str, Any]:
    graph_codes = _delta_codes(graph_delta)
    ring_codes = _delta_codes(ring_topology)
    fg_codes = _delta_codes(fg_delta)
    observed = graph_codes | ring_codes | fg_codes
    profile = _family_profile(cat, action_context=action_context)
    declared_family = _family_evidence_summary(action_context.get("family_evidence"), ())
    base_supporting_codes: List[str] = []
    if action_context.get("intended_deltas"):
        base_supporting_codes.append("declared_intended_deltas")
    if action_context.get("mechanistic_evidence"):
        base_supporting_codes.append("declared_mechanistic_evidence")
    if declared_family["provided_keys"]:
        base_supporting_codes.append("declared_family_evidence")
    if template_execution.get("target_in_products"):
        base_supporting_codes.append("forward_template_regenerated_target")

    base_required_evidence: List[str] = []
    if _has_complex_ring_delta(ring_topology) or any(
        code in ring_codes
        for code in ("ring_count_increase", "ring_count_decrease", "ring_bond_edit")
    ):
        base_required_evidence.append("mechanistic topology proof for observed ring changes")
    if action_context.get("preserved_anchors") in (None, "", [], {}):
        base_required_evidence.append("preserved scaffold anchors or handles")
    if action_context.get("changed_bonds") in (None, "", [], {}):
        base_required_evidence.append("declared changed-bond atoms")

    base: Dict[str, Any] = {
        "family_key": "",
        "family_class": "",
        "state": "no_family_interpretation",
        "explained_deltas": [],
        "unexplained_deltas": sorted(observed),
        "forbidden_delta_conflicts": [],
        "supporting_codes": sorted(set(base_supporting_codes)),
        "required_evidence": list(dict.fromkeys(base_required_evidence)),
        "family_evidence": declared_family,
        "policy_effect": {
            "downgrade_codes": [],
            "preserve_codes": list(_PRESERVE_CODES),
        },
        "observed_deltas": {
            "graph": sorted(graph_codes),
            "ring": sorted(ring_codes),
            "fg": sorted(fg_codes),
        },
    }
    if not cat:
        return base
    if profile is None:
        base["state"] = "unregistered_family"
        return base

    allowed = set(profile["allowed_deltas"])
    forbidden = set(profile["forbidden_deltas"])
    explained = observed & allowed
    forbidden_conflicts = observed & forbidden
    family_evidence = _family_evidence_summary(
        action_context.get("family_evidence"),
        profile.get("evidence_keys", []) or [],
    )

    contextual_conflicts: List[str] = []
    if profile["family_class"] == "olefination" and _has_complex_ring_delta(ring_topology):
        if len(precursors) != 1:
            contextual_conflicts.append("intermolecular_olefination_complex_ring_delta")
        elif template_execution and not bool(template_execution.get("target_in_products", False)):
            contextual_conflicts.append("olefination_complex_ring_template_miss")
    if profile["family_class"] == "metathesis" and _has_complex_ring_delta(ring_topology) and len(precursors) != 1:
        contextual_conflicts.append("fragmented_rcm_complex_ring_delta")
    if "apparent_scaffold_jump" in graph_codes:
        contextual_conflicts.append("apparent_scaffold_jump")
    if (
        profile["family_class"] == "small_ring_formation"
        and ring_codes
        & {
            "new_fused_ring_system",
            "new_spiro_center",
            "new_bridged_system",
            "new_medium_ring",
            "new_macrocycle",
        }
    ):
        contextual_conflicts.append("small_ring_family_with_high_risk_topology")

    required_evidence = list(profile["required_evidence"])
    if action_context.get("preserved_anchors") in (None, "", [], {}):
        required_evidence.append("preserved scaffold anchors or handles")
    if action_context.get("changed_bonds") in (None, "", [], {}):
        required_evidence.append("declared changed-bond atoms")

    supporting_codes = [f"family_expected_{profile['family_class']}"]
    if action_context.get("intended_deltas"):
        supporting_codes.append("declared_intended_deltas")
    if action_context.get("mechanistic_evidence"):
        supporting_codes.append("declared_mechanistic_evidence")
    if family_evidence["provided_keys"]:
        supporting_codes.append("declared_family_evidence")
    if template_execution.get("target_in_products"):
        supporting_codes.append("forward_template_regenerated_target")

    unexplained = observed - explained - forbidden_conflicts
    if contextual_conflicts or forbidden_conflicts:
        state = "family_delta_conflict"
    elif explained and unexplained:
        state = "partially_explains_delta_requires_evidence"
    elif explained:
        state = "explains_delta_requires_evidence"
    elif observed:
        state = "does_not_explain_observed_delta"
    else:
        state = "family_no_observed_delta"

    downgrade_codes: List[str] = []
    if (
        explained
        and not contextual_conflicts
        and not forbidden_conflicts
        and profile["family_class"] != "high_risk_topology"
    ):
        downgrade_codes.append("high_risk_topology_requires_independent_evidence")

    return {
        "family_key": profile["family_key"],
        "family_class": profile["family_class"],
        "state": state,
        "explained_deltas": sorted(explained),
        "unexplained_deltas": sorted(unexplained),
        "forbidden_delta_conflicts": sorted(forbidden_conflicts | set(contextual_conflicts)),
        "supporting_codes": sorted(set(supporting_codes)),
        "required_evidence": list(dict.fromkeys(required_evidence)),
        "family_evidence": family_evidence,
        "policy_effect": {
            "downgrade_codes": downgrade_codes,
            "preserve_codes": list(_PRESERVE_CODES),
        },
        "observed_deltas": base["observed_deltas"],
        "risk_level": profile["risk_level"],
    }


def validate_reaction_family(
    precursors: Sequence[str],
    target: str,
    reaction_category: Optional[str] = None,
    ring_topology: Optional[Dict[str, Any]] = None,
    graph_delta: Optional[Dict[str, Any]] = None,
    fg_delta: Optional[Dict[str, Any]] = None,
    template_execution: Optional[Dict[str, Any]] = None,
    action_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Check reaction-family compatibility with topology deltas.

    ``graph_delta`` and ``fg_delta`` are accepted now so later graph/FG audit
    modules can plug into the same family registry without another public
    signature change.
    """
    del target

    cat = _family_category(reaction_category)
    ring_topology = ring_topology or {}
    template_execution = template_execution or {}
    action_context = action_context or {}
    family_interpretation = _build_family_interpretation(
        cat=cat,
        precursors=precursors,
        ring_topology=ring_topology,
        graph_delta=graph_delta,
        fg_delta=fg_delta,
        template_execution=template_execution,
        action_context=action_context,
    )
    if not cat:
        return {
            "pass": True,
            "has_hard_fail": False,
            "violations": [],
            "summary": "no reaction category, skipped",
            "family_interpretation": family_interpretation,
        }

    delta_codes = set(ring_topology.get("delta_codes", []) or [])
    complex_delta = _has_complex_ring_delta(ring_topology)
    violations: List[Dict[str, Any]] = []

    olefination_keys = {"hwe", "horner", "wadsworth", "emmons", "wittig", "julia", "peterson"}
    is_olefination = any(key in cat for key in olefination_keys)
    is_rcm = "rcm" in cat or "metathesis" in cat or "ring_closing_metathesis" in cat

    if is_olefination and complex_delta:
        if len(precursors) != 1:
            violations.append(make_finding(
                code="olefination_lacks_intramolecular_tether_proof",
                severity="requires_evidence",
                source="reaction_family",
                message=(
                    "olefination family cannot justify a new complex ring system from separate "
                    "intermolecular precursors without intramolecular tether proof"
                ),
                evidence={
                    "precursor_count": len(precursors),
                    "delta_codes": sorted(delta_codes),
                    "template_target_in_products": template_execution.get("target_in_products"),
                    "action_in_ring": action_context.get("in_ring"),
                },
                required_evidence=[
                    "single-precursor intramolecular tether proof",
                    "atom-mapped source of new ring junction atoms",
                ],
            ))
        elif template_execution and not bool(template_execution.get("target_in_products", False)):
            violations.append(make_finding(
                code="olefination_ring_closure_template_miss",
                severity="requires_evidence",
                source="reaction_family",
                message="olefination template did not regenerate the complex ring product",
                evidence={
                    "delta_codes": sorted(delta_codes),
                    "best_match": template_execution.get("best_match", ""),
                    "tanimoto_to_target": template_execution.get("tanimoto_to_target"),
                },
                required_evidence=[
                    "forward template target regeneration",
                    "independent atom-mapped ring-closure proof",
                ],
            ))

    if is_rcm and complex_delta:
        if len(precursors) != 1:
            violations.append(make_finding(
                code="rcm_requires_single_diene_precursor",
                severity="requires_evidence",
                source="reaction_family",
                message="RCM ring construction requires one tethered diene precursor, not disconnected fragments",
                evidence={
                    "precursor_count": len(precursors),
                    "delta_codes": sorted(delta_codes),
                },
                required_evidence=[
                    "single tethered diene precursor",
                    "mapped alkene termini in the same precursor",
                ],
            ))

    # Generic safeguard: a ring-bond template miss on a critical ring delta is
    # not enough by itself to hard-block every family, but it must require proof.
    if (
        action_context.get("in_ring")
        and ring_topology.get("risk_level") == "critical"
        and template_execution
        and not bool(template_execution.get("target_in_products", False))
        and not violations
    ):
        violations.append(make_finding(
            code="high_risk_topology_requires_independent_evidence",
            severity="requires_evidence",
            source="reaction_family",
            message="high-risk topology change requires independent mechanism and atom-source evidence",
            evidence={
                "delta_codes": sorted(delta_codes),
                "best_match": template_execution.get("best_match", ""),
                "tanimoto_to_target": template_execution.get("tanimoto_to_target"),
            },
            required_evidence=[
                "forward template target regeneration",
                "mechanistic topology proof",
            ],
        ))

    hard_fail = any(v.get("severity") == "hard_fail" for v in violations)
    return {
        "pass": not hard_fail,
        "has_hard_fail": hard_fail,
        "violations": violations,
        "summary": "ok" if not violations else f"{len(violations)} ring-family violation(s)",
        "family_interpretation": family_interpretation,
    }
