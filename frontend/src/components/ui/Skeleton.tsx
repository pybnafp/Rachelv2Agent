/** 骨架屏（诊断书 P0-05）：加载态占位，替代“加载中…”纯文字。 */
export function Skeleton({ className = "" }: { className?: string }) {
  return <div aria-hidden className={`animate-pulse rounded-md bg-slate-200 ${className}`} />;
}

/** 任务列表加载骨架：3 行表位占位。 */
export function TableSkeleton({ rows = 3, cols = 5 }: { rows?: number; cols?: number }) {
  return (
    <div data-testid="table-skeleton" className="rounded-xl border border-slate-200 bg-surface p-4">
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex items-center gap-4 border-b border-slate-100 py-3 last:border-b-0">
          {Array.from({ length: cols }).map((_, c) => (
            <Skeleton
              key={c}
              className={`h-4 ${c === 0 ? "w-24" : c === 1 ? "h-10 w-20" : c === cols - 1 ? "ml-auto w-28" : "w-16"}`}
            />
          ))}
        </div>
      ))}
    </div>
  );
}
