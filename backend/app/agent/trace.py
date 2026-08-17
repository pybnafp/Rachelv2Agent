from sqlalchemy.orm import Session, sessionmaker
from app.db.models import JobStep

def summarize_result(command: str, result: dict) -> str:
    if not isinstance(result, dict):
        return f"{command} → non-dict result"
    if result.get("error"):
        return f"{command} → error: {str(result['error'])[:160]}"
    parts = [command]
    for k in ("ok", "action", "n_attempts", "n_bonds", "terminal_count", "pending_count", "total_steps"):
        if k in result: parts.append(f"{k}={result[k]}")
    for k in ("sites", "actions", "terminals", "files", "starting_materials"):
        v = result.get(k)
        if isinstance(v, list): parts.append(f"n_{k}={len(v)}")
    return " ".join(parts)[:300]

class DbTraceSink:
    def __init__(self, session_factory: sessionmaker, job_id: str):
        self.factory = session_factory; self.job_id = job_id

    def record(self, seq: int, command: str, args: dict, result: dict,
               tokens: int, duration_ms: int) -> None:
        db: Session = self.factory()
        try:
            db.add(JobStep(job_id=self.job_id, seq=seq, command=command,
                           args=args or {}, result_summary=summarize_result(command, result),
                           status="error" if isinstance(result, dict) and result.get("error") else "ok",
                           tokens=tokens, duration_ms=duration_ms))
            db.commit()
        finally:
            db.close()
