export function formatDuration(started_at: string | null, finished_at: string | null): string {
  if (!started_at || !finished_at) return "—";
  const ms = new Date(finished_at).getTime() - new Date(started_at).getTime();
  if (ms < 0 || Number.isNaN(ms)) return "—";
  const total = Math.floor(ms / 1000);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const parts: string[] = [];
  if (h) parts.push(`${h}h`);
  if (m) parts.push(`${m}m`);
  parts.push(`${s}s`);
  return parts.join("");
}
