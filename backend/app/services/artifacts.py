import json
from pathlib import Path

def _load(p: Path):
    if not p.exists(): return None
    return json.loads(p.read_text(encoding="utf-8"))

def parse_export(export_dir: Path) -> dict:
    out: dict = {}
    vis = _load(export_dir / "visualization.json")
    terminals = _load(export_dir / "terminals.json")
    if vis is not None:
        out["visualization"] = vis
        out["metrics"] = {"n_nodes": len(vis.get("nodes", [])),
                          "n_edges": len(vis.get("edges", [])),
                          "n_terminals": sum(1 for n in vis.get("nodes", []) if n.get("role") == "terminal")}
    if terminals is not None:
        out["terminals"] = terminals
        out.setdefault("metrics", {})["n_terminals"] = len(terminals)
    ta = _load(export_dir / "terminal_audit.json")
    if ta is not None:
        out["terminal_audit"] = ta
    out["incomplete"] = not ("visualization" in out and "terminals" in out)
    return out
