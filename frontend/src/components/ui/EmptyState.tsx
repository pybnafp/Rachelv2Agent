import type { ReactNode } from "react";
import { FlaskConical } from "lucide-react";

/** 空状态组件（诊断书 P0-05）：图标 + 文案 + 可选动作，替代纯文字空态。 */
export function EmptyState({
  icon,
  title,
  hint,
  action,
  testid,
}: {
  icon?: ReactNode;
  title: string;
  hint?: string;
  action?: ReactNode;
  testid?: string;
}) {
  return (
    <div
      data-testid={testid ?? "empty-state"}
      className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-slate-300 bg-surface px-6 py-14 text-center"
    >
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-sky-50 text-sky-500">
        {icon ?? <FlaskConical size={22} aria-hidden />}
      </div>
      <div>
        <p className="text-sm font-medium text-slate-700">{title}</p>
        {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
      </div>
      {action}
    </div>
  );
}
