import type { HTMLAttributes } from "react";

type Color = "slate" | "sky" | "emerald" | "amber" | "red" | "zinc" | "blue";

const colors: Record<Color, string> = {
  slate: "bg-slate-100 text-slate-700",
  sky: "bg-sky-100 text-sky-700",
  emerald: "bg-emerald-100 text-emerald-700",
  amber: "bg-amber-100 text-amber-700",
  red: "bg-red-100 text-red-700",
  zinc: "bg-zinc-100 text-zinc-700",
  blue: "bg-blue-100 text-blue-700",
};

export function Badge({
  color = "slate",
  className = "",
  ...props
}: HTMLAttributes<HTMLSpanElement> & { color?: Color }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${colors[color]} ${className}`}
      {...props}
    />
  );
}
