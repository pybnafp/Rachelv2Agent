import { useState } from "react";
import { useTrace } from "../api/hooks";
import { Badge } from "./ui/Badge";
import { Card } from "./ui/Card";
import type { TraceStep } from "../types";
import { aggregateSteps } from "../lib/traceStats";

const HIGHLIGHT_COMMANDS = new Set(["commit", "accept"]);
const TERMINAL_STATUSES = new Set(["succeeded", "partial", "failed", "cancelled"]);

function hhmmss(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "--:--:--";
  return [d.getUTCHours(), d.getUTCMinutes(), d.getUTCSeconds()]
    .map((n) => String(n).padStart(2, "0"))
    .join(":") + " UTC";
}

function StatsCard({ steps, onRefresh }: { steps: TraceStep[]; onRefresh: () => void }) {
  const { total, errors, tokens, durationMs: ms } = aggregateSteps(steps);
  return (
    <Card>
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
        <div data-testid="trace-stat-steps" className="text-sm text-slate-600">
          总步数 <span className="font-semibold text-slate-800">{total}</span>
        </div>
        <div data-testid="trace-stat-errors" className="text-sm text-slate-600">
          error 步数 <span className="font-semibold text-red-600">{errors}</span>
        </div>
        <div data-testid="trace-stat-tokens" className="text-sm text-slate-600">
          tokens 合计 <span className="font-semibold text-slate-800">{tokens}</span>
        </div>
        <div data-testid="trace-stat-duration" className="text-sm text-slate-600">
          累计耗时 <span className="font-semibold text-slate-800">{(ms / 1000).toFixed(1)}</span> s
        </div>
        <button
          type="button"
          onClick={onRefresh}
          className="ml-auto rounded-md border border-slate-300 px-2 py-1 text-xs text-slate-600 hover:bg-slate-50"
        >
          刷新
        </button>
      </div>
    </Card>
  );
}

interface RejectedItem {
  action_id?: string;
  reason?: string;
  [key: string]: any;
}

function ExpandedDetail({ step }: { step: TraceStep }) {
  const args = step.args ?? {};
  return (
    <div data-testid={`trace-expand-${step.seq}`} className="mt-2 space-y-2 border-t border-slate-100 pt-2">
      {step.command === "commit" && (
        <div className="space-y-2">
          {typeof args.reasoning === "string" && (
            <blockquote className="border-l-4 border-amber-400 bg-amber-50 px-3 py-2 text-xs text-slate-700">
              {args.reasoning}
            </blockquote>
          )}
          {args.confidence != null && <Badge color="sky">confidence: {String(args.confidence)}</Badge>}
          {Array.isArray(args.rejected) && (args.rejected as RejectedItem[]).length > 0 && (
            <div className="text-xs text-slate-600">
              <p className="mb-1 font-medium text-slate-500">rejected:</p>
              <ul className="list-disc space-y-1 pl-5">
                {(args.rejected as RejectedItem[]).map((item, i) => (
                  <li key={i} className="font-mono text-xs">
                    {JSON.stringify(item)}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
      {step.command === "accept" && typeof args.reason === "string" && (
        <blockquote className="border-l-4 border-sky-300 bg-sky-50 px-3 py-2 text-xs text-slate-700">
          {args.reason}
        </blockquote>
      )}
      <div>
        <p className="mb-1 text-xs font-medium text-slate-500">args</p>
        <pre
          data-testid={`trace-args-${step.seq}`}
          className="max-h-64 overflow-auto rounded bg-slate-50 p-2 font-mono text-xs text-slate-700"
        >
          {JSON.stringify(step.args ?? {}, null, 2)}
        </pre>
      </div>
      <blockquote className="rounded bg-slate-100 px-3 py-2 text-xs text-slate-600">
        {step.result_summary}
      </blockquote>
    </div>
  );
}

export function AuditTimeline({ jobId, jobStatus }: { jobId: string | undefined; jobStatus?: string }) {
  // 终态才拉取 trace：运行中由 ProgressPanel（SSE/轮询）负责实时步骤；
  // 未传 jobStatus 的调用方（测试/独立使用）保持原有行为
  const terminal = jobStatus == null || TERMINAL_STATUSES.has(jobStatus);
  const { data, refetch } = useTrace(jobId, terminal);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  const steps = data?.steps ?? [];

  const toggle = (seq: number) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(seq)) next.delete(seq);
      else next.add(seq);
      return next;
    });

  return (
    <div className="space-y-3" data-testid="audit-timeline">
      <StatsCard steps={steps} onRefresh={() => void refetch()} />
      {steps.length === 0 ? (
        <div data-testid="trace-empty" className="rounded-lg border border-dashed border-slate-300 p-8 text-center text-sm text-slate-400">
          暂无步骤记录
        </div>
      ) : (
        <Card>
          <ul className="divide-y divide-slate-100">
            {steps.map((step) => (
              <li key={step.seq}>
                <button
                  type="button"
                  data-testid={`trace-row-${step.seq}`}
                  onClick={() => toggle(step.seq)}
                  className="flex w-full flex-wrap items-center gap-x-3 gap-y-1 px-1 py-2 text-left hover:bg-slate-50"
                >
                  <span className="inline-flex h-6 min-w-6 items-center justify-center rounded-full bg-slate-100 px-1.5 font-mono text-xs font-semibold text-slate-600">
                    {step.seq}
                  </span>
                  <Badge color={HIGHLIGHT_COMMANDS.has(step.command) ? "sky" : "slate"}>{step.command}</Badge>
                  <span
                    data-testid={`trace-status-${step.seq}`}
                    data-status={step.status}
                    title={step.status}
                    className={`inline-block h-2 w-2 rounded-full ${step.status === "error" ? "bg-red-500" : "bg-emerald-500"}`}
                  />
                  <span className="text-xs text-slate-500">{step.tokens} tok</span>
                  <span className="text-xs text-slate-500">{step.duration_ms} ms</span>
                  <span className="ml-auto font-mono text-xs text-slate-400">{hhmmss(step.created_at)}</span>
                </button>
                {expanded.has(step.seq) && <ExpandedDetail step={step} />}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
