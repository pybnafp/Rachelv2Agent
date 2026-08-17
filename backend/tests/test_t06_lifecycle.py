def test_lifecycle_success(client, db, auth_headers_user, monkeypatch, tmp_path):
    from app.worker import tasks
    class FakeDriverResult:
        status = "succeeded"; reason = ""; steps = 7
        tokens_in = 1000; tokens_out = 500; export_result = {"output_dir": str(tmp_path)}
    class FakeDriver:
        def __init__(self, *a, **kw): pass
        def run(self): return FakeDriverResult()
    monkeypatch.setattr(tasks, "_build_driver", lambda job, ws: FakeDriver())
    r = client.post("/api/jobs", headers=auth_headers_user, json={"smiles": "CC(=O)Nc1ccc(O)cc1"})
    out = client.get(f"/api/jobs/{r.json()['id']}", headers=auth_headers_user).json()
    assert out["status"] == "succeeded"
    assert out["stats"]["steps"] == 7 and out["stats"]["tokens_in"] == 1000
    assert "export_dir" in out["stats"]

def test_lifecycle_failure_marks_failed(client, db, auth_headers_user, monkeypatch):
    from app.worker import tasks
    def boom(job, ws): raise RuntimeError("llm exploded")
    monkeypatch.setattr(tasks, "_build_driver", boom)
    r = client.post("/api/jobs", headers=auth_headers_user, json={"smiles": "CC(=O)Nc1ccc(O)cc1"})
    out = client.get(f"/api/jobs/{r.json()['id']}", headers=auth_headers_user).json()
    assert out["status"] == "failed" and "llm exploded" in out["error"]
