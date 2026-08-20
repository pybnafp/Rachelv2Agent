import { useEffect, useRef, useState } from "react";
import { useJobEvents } from "../api/hooks";
import { aggregateSteps } from "../lib/traceStats";
import { STAGES, stageOf } from "../lib/stages";
import { Badge } from "./ui/Badge";
import { Card } from "./ui/Card";
import type { TraceStep } from "../types";

const MODE_BADGE: Record<string, { label: string; color: "sky" | "amber" | "zinc" }> = {
  sse: { label: "实时", color: "sky" },
  polling: { label: "轮询降级", color: "amber" },
  closed: { label: "已结束", color: "zinc" },
};

function StageBar({ current }: { current: string }) {
  const curIdx = STAGES.findIndex((s) => s.key === current);
  return (
    <ol data-testid="stage-bar" className="flex flex-wrap items-center gap-1">
      {STAGES.map((s, i) => {
        const isCurrent = i === curIdx;
        const isPast = curIdx >= 0 && i < curIdx;
        return (
          <li key={s.key} className="flex items-center gap-1">
            {i > 0 && <span className="text-xs text-slate-300">→</span>}
            <span
              data-testid={`stage-${s.key}`}
              data-state={isCurrent ? "current" : isPast ? "done" : "later"}
              className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${
                isCurrent
                  ? "bg-sky-100 text-sky-700 ring-2 ring-sky-600"
                  : isPast
                    ? "bg-emerald-50 text-emerald-700"
                    : "bg-slate-100 text-slate-400"
              }`}
            >
              {isPast && <span aria-hidden>✓</span>}
              {s.label}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

export function ProgressPanel({ jobId, onTerminal }: { jobId: string; onTerminal?: () => void }) {
  const [steps, setSteps] = useState<TraceStep[]>([]);
  const [status, setStatus] = useState<string>("running");
  const doneRef = useRef(false);
  const { mode } = useJobEvents({
    id: jobId,
    onSteps: (incoming, replace) =>
      setSteps((prev) => (replace ? incoming : [...prev, ...incoming])),
    onStatus: (s) => setStatus(s.status),
    onDone: () => {
      if (!doneRef.current) {
        doneRef.current = true;
        onTerminal?.();
      }
    },
  });

  const streamRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const el = streamRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [steps.length]);

  const stats = aggregateSteps(steps);
  const stage = stageOf(steps.map((s) => s.command));
  const badge = MODE_BADGE[mode] ?? MODE_BADGE.closed;
  const recent = steps.slice(-30);

  return (
    <Card data-testid="progress-panel" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <StageBar current={stage} />
        <Badge color={badge.color} data-testid="conn-mode">
          {badge.label}
        </Badge>
      </div>

      <div
        ref={streamRef}
        data-testid="cmd-stream"
        className="max-h-72 overflow-y-auto rounded-md border border-slate-100 bg-surface-2 p-2"
      >
        {recent.length === 0 ? (
          <p className="py-6 text-center text-xs text-slate-400">等待第一批命令…</p>
        ) : (
          <ul className="space-y-1">
            {recent.map((s) => (
              <li
                key={s.seq}
                data-testid={`cmd-row-${s.seq}`}
                className="flex items-center gap-x-3 px-1 font-mono text-xs text-slate-600"
              >
                <span className="w-8 text-right text-slate-400">{s.seq}</span>
                <span className="min-w-24 text-slate-700">{s.command}</span>
                <span
                  title={s.status}
                  className={`inline-block h-2 w-2 rounded-full ${s.status === "error" ? "bg-red-500" : "bg-emerald-500"}`}
                />
                <span className="ml-auto text-slate-400">{s.duration_ms} ms</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="grid grid-cols-3 gap-3 text-center">
        <div data-testid="live-steps" className="rounded-md bg-slate-50 p-2">
          <p className="text-xs text-slate-500">步数</p>
          <p className="text-lg font-semibold text-slate-800">{stats.total}</p>
        </div>
        <div data-testid="live-tokens" className="rounded-md bg-slate-50 p-2">
          <p className="text-xs text-slate-500">tokens</p>
          <p className="text-lg font-semibold text-slate-800">{stats.tokens}</p>
        </div>
        <div data-testid="live-duration" className="rounded-md bg-slate-50 p-2">
          <p className="text-xs text-slate-500">耗时 (s)</p>
          <p className="text-lg font-semibold text-slate-800">{(stats.durationMs / 1000).toFixed(1)}</p>
        </div>
      </div>

      <p data-testid="running-hint" className="text-xs text-slate-500">
        任务执行中，预计 10-30 分钟。当前状态：{status}
      </p>
    </Card>
  );
}
