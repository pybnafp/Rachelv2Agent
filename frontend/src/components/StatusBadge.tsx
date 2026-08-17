export type RunStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "partial"
  | "failed"
  | "cancelled";

const styles: Record<RunStatus, { dot: string; text: string; pulse?: boolean }> = {
  queued: { dot: "bg-slate-400", text: "text-slate-600" },
  running: { dot: "bg-sky-500", text: "text-sky-600", pulse: true },
  succeeded: { dot: "bg-emerald-500", text: "text-emerald-600" },
  partial: { dot: "bg-amber-500", text: "text-amber-600" },
  failed: { dot: "bg-red-500", text: "text-red-600" },
  cancelled: { dot: "bg-zinc-400", text: "text-zinc-600" },
};

export function StatusBadge({ status }: { status: RunStatus }) {
  const s = styles[status] ?? styles.queued;
  return (
    <span
      data-testid={`status-${status}`}
      className={`inline-flex items-center gap-1.5 text-xs font-medium ${s.text}`}
    >
      <span className={`inline-block h-2 w-2 rounded-full ${s.dot} ${s.pulse ? "animate-pulse" : ""}`} />
      {status}
    </span>
  );
}
