"""Preflight normalization for reactive precursor encodings.

This module handles cases where an LLM or template emits a reactive
organometallic as a precursor. The reagent belongs to the current reaction and
must remain in that precursor set. Rachel separately records its upstream
source obligation so route planning can trace it without changing the chemistry
being validated.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Sequence

from rdkit import Chem

from ._rdkit_utils import canonical, validate_smiles


_METAL_GROUP_RE = re.compile(
    r"(?:\[(?:F|Cl|Br|I)\]|F|Cl|Br|I)?"
    r"\[(Li|Mg|Zn|Cu)\]"
    r"(?:\[(?:F|Cl|Br|I)\]|F|Cl|Br|I)?"
)
_METAL_SOURCE_SMILES = {
    "Li": "[Li]Br",
    "Mg": "[Mg]",
    "Zn": "[Zn]",
    "Cu": "[Cu]I",
}


def _dedupe_precursors(items: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for item in items:
        smi = str(item or "").strip()
        if not smi or smi in seen:
            continue
        seen.add(smi)
        out.append(smi)
    return out


def _looks_like_carbon_metal_reagent(smiles: str) -> bool:
    if not _METAL_GROUP_RE.search(smiles or ""):
        return False
    mol = Chem.MolFromSmiles(smiles)
    if mol is not None:
        metals = {3, 12, 29, 30}
        return any(
            atom.GetAtomicNum() in metals
            and any(neighbor.GetAtomicNum() == 6 for neighbor in atom.GetNeighbors())
            for atom in mol.GetAtoms()
        )
    # Invalid template outputs still need a conservative fallback. Match carbon
    # atom tokens, not the leading "C" in element symbols such as Cl or Cu.
    return bool(re.search(r"\[(?:\d+)?C[^]]*\]|(?<![A-Za-z])C(?![a-z])|c", smiles))


def _canonical_sources(metals: Iterable[str]) -> List[str]:
    sources: List[str] = []
    for metal in dict.fromkeys(metals):
        source = _METAL_SOURCE_SMILES.get(metal)
        if source:
            sources.append(canonical(source) or source)
    return _dedupe_precursors(sources)


def normalize_reactive_metal_precursor(smiles: str) -> Dict[str, Any]:
    """Return a source-obligation record for a C-metal reagent precursor."""
    raw = str(smiles or "").strip()
    if not raw or not _looks_like_carbon_metal_reagent(raw):
        return {"status": "not_applicable", "smiles": raw}

    metals = [match.group(1) for match in _METAL_GROUP_RE.finditer(raw)]
    parent_raw = _METAL_GROUP_RE.sub("Br", raw)
    parent_can = canonical(parent_raw)
    if not parent_can:
        ok, reason = validate_smiles(parent_raw)
        return {
            "status": "normalization_failed",
            "smiles": raw,
            "detected_metals": list(dict.fromkeys(metals)),
            "attempted_parent": parent_raw,
            "failure_reason": reason or ("parent parsed unexpectedly invalid" if not ok else ""),
            "required_action": (
                "Replace the reactive C-metal reagent by an explicit organic "
                "halide/metal-source precursor step; the organic skeleton still "
                "needs a valid SMILES."
            ),
        }

    reagent_can = canonical(raw)
    if not reagent_can:
        ok, reason = validate_smiles(raw)
        return {
            "status": "normalization_failed",
            "smiles": raw,
            "detected_metals": list(dict.fromkeys(metals)),
            "attempted_parent": parent_raw,
            "upstream_source_precursors": _dedupe_precursors(
                [parent_can] + _canonical_sources(metals)
            ),
            "failure_reason": reason or ("metalated reagent parsed unexpectedly invalid" if not ok else ""),
            "required_action": (
                "Provide a valid organometallic reagent SMILES for the current "
                "reaction; its organic halide and metal source belong to a "
                "separate upstream source step."
            ),
        }

    upstream_sources = _dedupe_precursors([parent_can] + _canonical_sources(metals))
    return {
        "status": "source_obligation",
        "smiles": raw,
        "current_reagent": reagent_can,
        "normalized_parent": parent_can,
        "upstream_source_precursors": upstream_sources,
        "detected_metals": list(dict.fromkeys(metals)),
        "source_policy": "reactive_organometallic_reagent_requires_upstream_source_step",
        "required_action": (
            "Keep the organometallic in the current reaction. Trace its organic "
            "halide and metal source as a separate upstream step when route value requires it."
        ),
    }


def normalize_precursor_set(precursors: Sequence[str]) -> Dict[str, Any]:
    """Canonicalize precursors and record organometallic source obligations.

    Returns a dict with:
      - ``precursors``: canonical, RDKit-parseable precursor list when possible;
      - ``normalizations``: records for any detected metal reagent handling;
      - ``invalid``: inputs that remain invalid after preflight.
    """
    normalized_precursors: List[str] = []
    normalizations: List[Dict[str, Any]] = []
    invalid: List[Dict[str, Any]] = []

    for raw in precursors:
        smi = str(raw or "").strip()
        if not smi:
            continue

        metal_record = normalize_reactive_metal_precursor(smi)
        if metal_record.get("status") == "source_obligation":
            normalizations.append(metal_record)
            normalized_precursors.append(metal_record["current_reagent"])
            continue
        if metal_record.get("status") == "normalization_failed":
            normalizations.append(metal_record)

        can = canonical(smi)
        if can:
            normalized_precursors.append(can)
            continue

        ok, reason = validate_smiles(smi)
        invalid.append({
            "smiles": smi,
            "reason": reason or ("invalid SMILES" if not ok else ""),
            "normalization_status": metal_record.get("status", "not_applicable"),
        })

    return {
        "precursors": normalized_precursors,
        "normalizations": normalizations,
        "invalid": invalid,
        "changed": any(
            item.get("status") == "source_obligation"
            and item.get("current_reagent") != item.get("smiles")
            for item in normalizations
        ),
    }


def normalize_reagent_set(reagents: Sequence[str]) -> Dict[str, Any]:
    """试剂/条件的宽松归一化。

    与前体不同，试剂常以催化剂/碱/溶剂/温度的名称或缩写给出
    (CuI、K2CO3、DMF、'heat'、1,10-phenanthroline)，这些本就不是 SMILES。
    可解析为分子的试剂 → 规范化 SMILES（参与 forward validation / 原子平衡）；
    其余 → 原样保留为 free-text 条件（仅审计，不参与分子计算）。

    绝不因试剂无法解析为 SMILES 而判定失败——返回 {"reagents": [...], "conditions": [...]}。
    """
    molecular: List[str] = []
    conditions: List[str] = []
    seen: set[str] = set()
    for raw in reagents or []:
        smi = str(raw or "").strip()
        if not smi or smi in seen:
            continue
        seen.add(smi)
        can = canonical(smi)
        if can:
            molecular.append(can)
        else:
            conditions.append(smi)
    return {"reagents": molecular, "conditions": conditions}
