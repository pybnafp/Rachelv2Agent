"""Real-RetroCmd smoke walkthrough (no LLM): init -> loop(next/sites/explore/try/commit|accept) -> finalize -> export.

Usage: D:/Anaconda/envs/rachel-v2/python.exe scripts/smoke_retro.py [SMILES]
Default target: paracetamol CC(=O)Nc1ccc(O)cc1

Verified response shapes (Rachel-v2, public protocol):
  reaction_sites -> {"site_reaction_map": [{"site_id": "bond:0", ...}, ...]}
  explore_site   -> {"actions": [{"action_id": "...", ...}, ...]}
  try_action     -> {"ok": bool, "validation": {"gate": "pass"|"soft_warn"|"hard_block"|...}}
  sandbox_list   -> {"n_attempts": int, "attempts": [{"idx": int, "action_id": ...}, ...]}
"""
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "Rachel-v2"))

from Rachel.main.retro_cmd import RetroCmd  # noqa: E402

PARACETAMOL = "CC(=O)Nc1ccc(O)cc1"


def first_site_id(sites: dict):
    for s in sites.get("site_reaction_map") or sites.get("sites") or []:
        if isinstance(s, dict) and s.get("site_id"):
            return s["site_id"]
    return None


def first_action_id(explore: dict):
    for a in explore.get("actions") or explore.get("candidates") or []:
        if isinstance(a, dict) and (a.get("action_id") or a.get("candidate_id")):
            return a.get("action_id") or a.get("candidate_id")
    return None


def gate_allows(try_result: dict) -> bool:
    v = try_result.get("validation") or {}
    gate = str(v.get("gate") or try_result.get("validation_gate") or "")
    return bool(try_result.get("ok", not try_result.get("error"))) and gate != "hard_block"


def main() -> int:
    target = sys.argv[1] if len(sys.argv) > 1 else PARACETAMOL
    out_root = ROOT / "output" / f"smoke_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    out_root.mkdir(parents=True, exist_ok=True)
    retro = RetroCmd(str(out_root / "session.json"))

    steps = 0

    def run(cmd: str, args: dict | None = None) -> dict:
        nonlocal steps
        steps += 1
        r = retro.execute(cmd, args or {})
        print(f"[{steps:03d}] {cmd} {' '.join(str(v) for v in (args or {}).values())[:60]}"
              f" -> {'ERROR: ' + str(r.get('error'))[:100] if r.get('error') else 'ok'}")
        return r

    r = run("init", {"target": target, "name": "smoke"})
    if r.get("error"):
        return 2

    for _ in range(60):
        r = run("next")
        if r.get("action") == "queue_empty" or r.get("error"):
            break
        sites = run("reaction_sites")
        sid = first_site_id(sites)
        committed = False
        if sid:
            explore = run("explore_site", {"site_id": sid})
            aid = first_action_id(explore)
            if aid:
                tr = run("try_action", {"action_id": aid})
                if not tr.get("error") and gate_allows(tr):
                    # try_action creates a sandbox attempt; commit the latest idx
                    # with the action_id we tried as expected_action_id.
                    lst = run("sandbox_list")
                    idx = (lst.get("n_attempts", 1) - 1) if isinstance(lst, dict) else 0
                    cr = run("commit", {"idx": max(idx, 0), "expected_action_id": aid,
                                        "reasoning": "smoke: first viable action at top site"})
                    committed = not cr.get("error")
        if not committed:
            ar = run("accept", {"reason": "smoke: no viable action accepted"})
            if ar.get("error"):
                run("skip", {"reason": "smoke skip"})

    run("finalize", {"summary": "smoke run"})
    ex = run("export", {"name": "smoke", "output_dir": str(out_root / "export")})
    if ex.get("error"):
        print("EXPORT FAILED:", ex["error"])
        return 3
    vis = out_root / "export" / "visualization.json"
    if not vis.exists():
        print("visualization.json missing")
        return 4
    n_nodes = len(json.loads(vis.read_text(encoding="utf-8")).get("nodes", []))
    print(f"SMOKE OK steps={steps} nodes={n_nodes} export={out_root / 'export'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
