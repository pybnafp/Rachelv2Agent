import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ProgressPanel } from "../components/ProgressPanel";
import { useAuthStore } from "../stores/auth";
import { FakeEventSource, resetEventSources } from "./fakes_eventsource";
import type { TraceStep } from "../types";

vi.stubGlobal("EventSource", FakeEventSource);

const jsonResp = (status: number, body: unknown) =>
  Promise.resolve({ ok: status >= 200 && status < 300, status, json: () => Promise.resolve(body) });

const mkStep = (over: Partial<TraceStep>): TraceStep => ({
  seq: 1,
  command: "next",
  args: {},
  result_summary: "",
  status: "ok",
  tokens: 10,
  duration_ms: 100,
  created_at: "2026-08-17T10:00:00Z",
  ...over,
});

beforeEach(() => {
  resetEventSources();
  useAuthStore.setState({ token: "t", role: "user" });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.stubGlobal("EventSource", FakeEventSource);
  vi.useRealTimers();
});

describe("ProgressPanel (SSE)", () => {
  it("snapshot renders rows, live stats and stage highlight; steps append; done closes", () => {
    const onTerminal = vi.fn();
    render(<ProgressPanel jobId="j1" onTerminal={onTerminal} />);
    const es = FakeEventSource.instances[0];
    expect(es).toBeDefined();
    expect(es.url).toBe("/api/jobs/j1/events?token=t");

    // snapshot：3 步（init / next / reaction_sites → planning）
    act(() => {
      es.trigger("snapshot", {
        status: "running",
        stats_live: { steps: 3, tokens: 30, duration_ms: 300, last_seq: 3 },
        steps: [
          mkStep({ seq: 1, command: "init" }),
          mkStep({ seq: 2, command: "next" }),
          mkStep({ seq: 3, command: "reaction_sites" }),
        ],
      });
    });
    expect(screen.getAllByTestId(/^cmd-row-/)).toHaveLength(3);
    expect(screen.getByTestId("live-steps")).toHaveTextContent("3");
    expect(screen.getByTestId("live-tokens")).toHaveTextContent("30");
    expect(screen.getByTestId("live-duration")).toHaveTextContent("0.3");
    expect(screen.getByTestId("stage-planning").getAttribute("data-state")).toBe("current");
    expect(screen.getByTestId("stage-init").getAttribute("data-state")).toBe("done");
    expect(screen.getByTestId("conn-mode")).toHaveTextContent("实时");

    // 增量 steps：+2
    act(() => {
      es.trigger("steps", {
        steps: [mkStep({ seq: 4, command: "route_plan" }), mkStep({ seq: 5, command: "guide" })],
      });
    });
    expect(screen.getAllByTestId(/^cmd-row-/)).toHaveLength(5);
    expect(screen.getByTestId("stage-strategy").getAttribute("data-state")).toBe("current");

    // done → 关闭 + onTerminal
    expect(onTerminal).not.toHaveBeenCalled();
    act(() => {
      es.trigger("done", { status: "succeeded" });
    });
    expect(screen.getByTestId("conn-mode")).toHaveTextContent("已结束");
    expect(onTerminal).toHaveBeenCalledTimes(1);
    expect(es.closed).toBe(true);
  });

  it("unmount closes the EventSource", () => {
    const { unmount } = render(<ProgressPanel jobId="j1" />);
    const es = FakeEventSource.instances[0];
    unmount();
    expect(es.closed).toBe(true);
  });
});

describe("ProgressPanel (polling fallback)", () => {
  it("falls back to polling on error, appends trace steps, terminates on terminal job", async () => {
    vi.useFakeTimers();
    let jobStatus = "running";
    const fetchMock = vi.fn((path: string) => {
      if (path === "/api/jobs/j1/trace?after=0") {
        // 首个 tick：1 步增量
        return jsonResp(200, { steps: [mkStep({ seq: 1, command: "init" })] });
      }
      if (path.startsWith("/api/jobs/j1/trace")) return jsonResp(200, { steps: [] });
      if (path === "/api/jobs/j1")
        return jsonResp(200, { id: "j1", status: jobStatus, stats: {} });
      return jsonResp(404, { error: "nf" });
    });
    vi.stubGlobal("fetch", fetchMock);

    const onTerminal = vi.fn();
    FakeEventSource.autoErrorNext = true;
    render(<ProgressPanel jobId="j1" onTerminal={onTerminal} />);

    // 让构造后的异步 onerror + 立即首轮 tick 跑完
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });
    expect(screen.getByTestId("conn-mode")).toHaveTextContent("轮询降级");
    expect(fetchMock.mock.calls.some((c) => c[0] === "/api/jobs/j1/trace?after=0")).toBe(true);
    expect(screen.getAllByTestId(/^cmd-row-/)).toHaveLength(1);

    // 下一轮：任务转终态 → 关闭 + onTerminal
    jobStatus = "succeeded";
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(screen.getByTestId("conn-mode")).toHaveTextContent("已结束");
    expect(onTerminal).toHaveBeenCalledTimes(1);
  });
});
