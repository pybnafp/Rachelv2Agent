import type { HTMLAttributes } from "react";

export function Card({
  title,
  className = "",
  children,
  ...props
}: HTMLAttributes<HTMLDivElement> & { title?: string }) {
  return (
    <div className={`rounded-lg border border-slate-200 bg-white p-4 shadow-sm ${className}`} {...props}>
      {title != null && <h3 className="mb-3 text-sm font-semibold text-slate-800">{title}</h3>}
      {children}
    </div>
  );
}
