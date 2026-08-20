"""LLM 供应商逆合成对比 runner：同一目标分子，逐家驱动完整 Rachel-v2 逆合成流程。

复用生产组件（backend/app/agent/driver.py + Rachel-v2 RetroCmd），仅按供应商切换
OpenAI 兼容客户端；temperature=0.2 / max_output=8192 与生产一致。

用法:
  D:/Anaconda/envs/rachel-v2/python.exe scripts/llm_retro_compare.py --smoke            # 全部已配置供应商连通性测试
  D:/Anaconda/envs/rachel-v2/python.exe scripts/llm_retro_compare.py --smoke --only glm
  D:/Anaconda/envs/rachel-v2/python.exe scripts/llm_retro_compare.py --run --only glm   # 单家完整逆合成
配置来源: 仓库根 .env（GLM_/DEEPSEEK_/QWEN_/KIMI_ 前缀，API_KEY 为空则跳过该家）。
产物: output/llm_compare/<ts>_<provider>/{session.json, trace.jsonl, messages.jsonl, summary.json, export/}
"""
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "Rachel-v2"))

DEFAULT_TARGET = "COc1ncc(Cl)cc1Nc1nc(Cl)c(C)cc1[N+](=O)[O-]"
PROVIDERS = ["glm", "deepseek", "qwen", "kimi"]


def load_env(path: Path) -> dict:
    env = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip()
    return env


def provider_config(env: dict, name: str) -> dict | None:
    p = name.upper()
    key = env.get(f"{p}_API_KEY", "")
    if not key:
        return None
    return {"api_key": key, "base_url": env.get(f"{p}_BASE_URL", ""),
            "model": env.get(f"{p}_MODEL", "")}


class FileTraceSink:
    """与 DbTraceSink 同接口，落盘 trace.jsonl 并打印单行进度（供后台监控）。"""

    def __init__(self, path: Path, tag: str):
        self.path, self.tag = Path(path), tag

    def record(self, seq: int, command: str, args: dict, result: dict,
               tokens: int, duration_ms: int) -> None:
        err = isinstance(result, dict) and result.get("error")
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(
                {"seq": seq, "command": command,
                 "args": {k: args[k] for k in list(args)[:4]} if isinstance(args, dict) else args,
                 "ok": not err, "error": str(err)[:200] if err else None,
                 "tokens": tokens, "duration_ms": duration_ms},
                ensure_ascii=False, default=str) + "\n")
        arg_head = " ".join(str(v) for v in (args or {}).values())[:50] if isinstance(args, dict) else ""
        print(f"[{self.tag}] {seq:03d} {command} {arg_head} -> {'ERR: ' + str(err)[:80] if err else 'ok'}",
              flush=True)


def smoke(name: str, cfg: dict) -> bool:
    from openai import OpenAI
    print(f"[{name}] smoke: {cfg['base_url']} model={cfg['model']}", flush=True)
    try:
        cli = OpenAI(base_url=cfg["base_url"], api_key=cfg["api_key"])
        r = cli.chat.completions.create(
            model=cfg["model"],
            messages=[{"role": "user", "content": "Reply with exactly one word: pong"}],
            max_tokens=2048, temperature=0.2)
        msg = r.choices[0].message
        content = (msg.content or "").strip()[:80]
        finish = getattr(r.choices[0], "finish_reason", "")
        u = getattr(r, "usage", None)
        print(f"[{name}] smoke OK: finish={finish} content={content!r} "
              f"tokens={getattr(u, 'prompt_tokens', '?')}/{getattr(u, 'completion_tokens', '?')}", flush=True)
        return True
    except Exception as e:
        print(f"[{name}] smoke FAILED: {type(e).__name__}: {e}", flush=True)
        return False


def run_provider(name: str, cfg: dict, target: str, max_output: int = 8192) -> int:
    from Rachel.main.retro_cmd import RetroCmd
    from app.agent.driver import AgentDriver, DriverLimits
    from app.agent.llm_client import OpenAICompatClient
    from app.agent.prompts import build_task_prompt

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    ws = ROOT / "output" / "llm_compare" / f"{ts}_{name}"
    ws.mkdir(parents=True, exist_ok=True)
    print(f"[{name}] run start: target={target} max_output={max_output} workspace={ws}", flush=True)

    retro = RetroCmd(str(ws / "session.json"))
    llm = OpenAICompatClient(cfg["base_url"], cfg["api_key"], cfg["model"],
                             temperature=0.2, max_output=max_output)
    trace = FileTraceSink(ws / "trace.jsonl", name)
    driver = AgentDriver(retro=retro, llm=llm, trace=trace,
                         task_prompt=build_task_prompt(target, name),
                         name=name,
                         limits=DriverLimits(max_steps=300, wall_clock_sec=5400),
                         workspace=ws)
    t0 = time.monotonic()
    result = driver.run()
    dur = time.monotonic() - t0

    summary = {"provider": name, "model": cfg["model"], "target": target,
               "status": result.status, "reason": result.reason,
               "steps": result.steps, "tokens_in": result.tokens_in,
               "tokens_out": result.tokens_out, "duration_sec": round(dur, 1),
               "export_result": result.export_result,
               "workspace": str(ws), "finished_at": datetime.now().isoformat(timespec="seconds")}
    (ws / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
    print(f"[{name}] DONE status={result.status} steps={result.steps} "
          f"tokens={result.tokens_in}/{result.tokens_out} dur={dur:.0f}s "
          f"export={result.export_result.get('output_dir', '-')}", flush=True)
    return 0 if result.status == "succeeded" else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="connectivity test only")
    ap.add_argument("--run", action="store_true", help="full retrosynthesis run")
    ap.add_argument("--only", default="", help="comma list of providers (default: all configured)")
    ap.add_argument("--target", default=DEFAULT_TARGET)
    ap.add_argument("--max-output", type=int, default=8192,
                    help="LLM max output tokens (default 8192; deepseek retry uses 16384)")
    args = ap.parse_args()

    env = load_env(ROOT / ".env")
    names = [n.strip() for n in args.only.split(",") if n.strip()] if args.only else PROVIDERS
    cfgs = {}
    for n in names:
        c = provider_config(env, n)
        if c is None:
            print(f"[{n}] skipped: no API key in .env")
        else:
            cfgs[n] = c
    if not cfgs:
        print("no provider configured")
        return 2

    if args.smoke:
        ok = {n: smoke(n, c) for n, c in cfgs.items()}
        return 0 if all(ok.values()) else 1
    if args.run:
        rc = 0
        for n, c in cfgs.items():  # 单进程逐家执行；并行时每家独立调用本脚本
            rc = max(rc, run_provider(n, c, args.target, args.max_output))
        return rc
    print("specify --smoke or --run")
    return 2


if __name__ == "__main__":
    sys.exit(main())
