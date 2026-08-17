"""Route-completion PubChem terminal audit; failures degrade, never raise."""
from __future__ import annotations
import json, traceback
from pathlib import Path
from typing import Any

from Rachel.tools.pubchem_terminal_audit import (
    PubChemClient, audit_record, load_terminal_records, summarize,
)

AUDIT_FILE = "terminal_audit.json"


def run_terminal_audit(export_dir: Path, offline: bool | None = None) -> dict:
    try:
        if offline is None:
            from app.core.config import get_settings
            offline = get_settings().pubchem_offline
        records, _src = load_terminal_records(export_dir)
        client = PubChemClient(cache_dir=export_dir / ".pubchem_cache", offline=offline)
        results = [audit_record(r, client, include_vendors=not offline, query_reagents=False)
                   for r in records]
        payload: dict[str, Any] = {
            "schema": "rachel-v2-terminal-buyability-audit-002",
            "offline": bool(offline), "available": True,
            "summary": summarize(results), "results": results,
        }
    except Exception as exc:
        payload = {"available": False, "error": f"{type(exc).__name__}: {exc}",
                   "detail": traceback.format_exc()[-2000:]}
    try:
        export_dir.mkdir(parents=True, exist_ok=True)
        (export_dir / AUDIT_FILE).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    return payload
