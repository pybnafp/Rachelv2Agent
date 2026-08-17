import type { TraceStep } from "../types";

export interface TraceStats {
  total: number;
  errors: number;
  tokens: number;
  durationMs: number;
}

export function aggregateSteps(steps: TraceStep[]): TraceStats {
  return {
    total: steps.length,
    errors: steps.filter((s) => s.status === "error").length,
    tokens: steps.reduce((sum, s) => sum + (s.tokens || 0), 0),
    durationMs: steps.reduce((sum, s) => sum + (s.duration_ms || 0), 0),
  };
}
