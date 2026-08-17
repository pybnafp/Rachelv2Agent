"""Verify the extracted Rachel-v2-20260721_142758-codex-skill release."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_checksums() -> int:
    payload = json.loads((ROOT / "SHA256SUMS.json").read_text(encoding="utf-8"))
    for item in payload["files"]:
        path = ROOT / item["path"]
        if not path.is_file():
            raise SystemExit(f"checksum file missing: {item['path']}")
        if path.stat().st_size != item["bytes"]:
            raise SystemExit(f"size mismatch: {item['path']}")
        if sha256_file(path) != item["sha256"]:
            raise SystemExit(f"sha256 mismatch: {item['path']}")
    return len(payload["files"])


def main() -> None:
    checksum_count = verify_checksums()

    from Rachel.main import RetroCmd
    from Rachel.main.public_protocol import project_public_payload
    from Rachel.chem_tools.atom_mapping_audit import audit_atom_mapping
    from Rachel.chem_tools.fg_delta_audit import audit_fg_delta
    from Rachel.chem_tools.graph_delta_audit import audit_graph_delta
    from Rachel.chem_tools.reaction_family_validate import validate_reaction_family
    from Rachel.chem_tools.ring_topology_audit import audit_ring_topology
    from Rachel.chem_tools.topology_intent import action_declares_topology_change
    from Rachel.chem_tools.validation_contract import build_validation_contract
    from Rachel.chem_tools.validation_policy import build_validation_gate
    from Rachel.tools.atom_bond_map import build_atom_bond_map
    from Rachel.tools.audit_terminal_buyability_batch import build_arg_parser
    from Rachel.tools.pubchem_terminal_audit import load_terminal_allowlist

    validation_imports = [
        audit_atom_mapping,
        audit_fg_delta,
        audit_graph_delta,
        validate_reaction_family,
        audit_ring_topology,
        action_declares_topology_change,
        build_validation_contract,
        build_validation_gate,
        project_public_payload,
    ]
    if not all(callable(item) for item in validation_imports):
        raise SystemExit("validation dependency closure did not load")

    run = ROOT / "release_smoke"
    if run.exists():
        shutil.rmtree(run)
    run.mkdir()
    cmd = RetroCmd(str(run / "session.json"))

    init_result = cmd.execute("init", {
        "target": "CC(=O)NC",
        "name": "release_smoke_acetamide",
        "terminal_cs_threshold": 0.0,
        "max_depth": 4,
        "max_steps": 10,
    })
    if not init_result.get("ok"):
        raise SystemExit(f"init failed: {init_result}")

    next_result = cmd.execute("next", {})
    if "error" in next_result:
        raise SystemExit(f"next failed: {next_result}")

    structure_result = cmd.execute("context", {"detail": "structure"})
    structure_current = structure_result.get("current") or {}
    molecule_structure = structure_current.get("molecule_structure") or {}
    if len(molecule_structure.get("atoms", [])) <= 0:
        raise SystemExit(f"structure context missing atoms: {structure_result}")
    if len(molecule_structure.get("bonds", [])) <= 0:
        raise SystemExit(f"structure context missing bonds: {structure_result}")
    if "molecule_structure" in (next_result.get("current") or {}):
        raise SystemExit("compact context unexpectedly contains molecule_structure")

    atom_bond_map = build_atom_bond_map("CCO")
    if atom_bond_map.get("atom_count") != 3 or atom_bond_map.get("bond_count") != 2:
        raise SystemExit(f"atom_bond_map compatibility failed: {atom_bond_map}")

    plan_result = cmd.execute("route_plan", {
        "route_thesis": "Use a direct amide disconnection smoke strategy.",
        "route_mode": "late_fgi",
        "key_disconnections": ["amide C-N"],
        "mode_evidence": ["small amide smoke target"],
        "strategic_risks": ["smoke test only"],
        "revision_triggers": ["unexpected missing action-space"],
        "revision_reason": "release smoke",
    })
    if not plan_result.get("ok"):
        raise SystemExit(f"route_plan failed: {plan_result}")

    sites = cmd.execute("reaction_sites", {})
    if "error" in sites or int(sites.get("site_count", 0) or 0) <= 0:
        raise SystemExit(f"reaction_sites failed: {sites}")

    allowlist_count = len(load_terminal_allowlist())
    if allowlist_count <= 0:
        raise SystemExit("terminal allowlist did not load")
    args = build_arg_parser().parse_args(["--dataset", "n1", "--limit", "1"])
    if args.dataset != "n1" or args.limit != 1:
        raise SystemExit("terminal-audit parser verification failed")

    summary = {
        "ok": True,
        "release": "Rachel-v2-20260721_142758-codex-skill",
        "python": sys.executable,
        "checksum_files": checksum_count,
        "site_count": sites.get("site_count", 0),
        "structure_atoms": len(molecule_structure.get("atoms", [])),
        "structure_bonds": len(molecule_structure.get("bonds", [])),
        "atom_bond_map_atoms": atom_bond_map.get("atom_count", 0),
        "terminal_allowlist_entries": allowlist_count,
        "validation_modules": len(validation_imports),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
