import { describe, expect, it } from "vitest";
import { aggregateSteps } from "../lib/traceStats";
import { STAGES, stageOf } from "../lib/stages";
import type { TraceStep } from "../types";

const step = (over: Partial<TraceStep>): TraceStep => ({
  seq: 1,
  command: "next",
  args: {},
  result_summary: "",
  status: "ok",
  tokens: 0,
  duration_ms: 0,
  created_at: "2026-08-17T10:00:00Z",
  ...over,
});

describe("aggregateSteps", () => {
  it("mixed ok/error steps count totals, errors, tokens, duration", () => {
    const steps = [
      step({ seq: 1, tokens: 100, duration_ms: 500 }),
      step({ seq: 2, status: "error", tokens: 50, duration_ms: 250 }),
      step({ seq: 3, command: "commit", tokens: 200, duration_ms: 1000 }),
    ];
    expect(aggregateSteps(steps)).toEqual({ total: 3, errors: 1, tokens: 350, durationMs: 1750 });
  });

  it("empty array gives zeros", () => {
    expect(aggregateSteps([])).toEqual({ total: 0, errors: 0, tokens: 0, durationMs: 0 });
  });

  it("missing tokens/duration treated as 0", () => {
    const s = step({ tokens: undefined as any, duration_ms: undefined as any });
    expect(aggregateSteps([s])).toEqual({ total: 1, errors: 0, tokens: 0, durationMs: 0 });
  });
});

describe("stageOf", () => {
  it("STAGES has 6 ordered keys with labels", () => {
    expect(STAGES.map((s) => s.key)).toEqual([
      "init",
      "planning",
      "strategy",
      "finalizing",
      "exporting",
      "done",
    ]);
    expect(STAGES.every((s) => s.label.length > 0)).toBe(true);
  });

  it("empty commands → init", () => {
    expect(stageOf([])).toBe("init");
  });

  it("init/next/reaction_sites → planning by last recognized command", () => {
    expect(stageOf(["init"])).toBe("init");
    expect(stageOf(["init", "next", "reaction_sites"])).toBe("planning");
    expect(stageOf(["init", "commit", "accept"])).toBe("planning");
    expect(stageOf(["next", "explore_site", "try_action", "propose_action"])).toBe("planning");
    expect(stageOf(["sandbox_list", "sandbox_clear", "select", "review_terminal", "skip"])).toBe(
      "planning"
    );
  });

  it("strategy / finalizing / exporting / done", () => {
    expect(stageOf(["next", "route_plan"])).toBe("strategy");
    expect(stageOf(["next", "route_sketch", "guide"])).toBe("strategy");
    expect(stageOf(["next", "route_plan", "finalize"])).toBe("finalizing");
    expect(stageOf(["finalize", "export"])).toBe("exporting");
    expect(stageOf(["export", "report"])).toBe("exporting");
    expect(stageOf(["report", "finish"])).toBe("done");
  });

  it("unknown commands ignored, falls back to last known", () => {
    expect(stageOf(["init", "wibble", "next", "frobnicate"])).toBe("planning");
    expect(stageOf(["finalize", "unknown_cmd"])).toBe("finalizing");
    expect(stageOf(["totally_unknown"])).toBe("init");
  });
});
