import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuditTimeline } from "../components/AuditTimeline";
import stepsFixture from "./fixtures/trace_steps.json";
import type { TraceStep } from "../types";

const steps = stepsFixture as unknown as TraceStep[];

const jsonResp = (body: unknown) =>
  Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });

function renderTimeline(traceBody: unknown = { steps }) {
  const fetchMock = vi.fn((path: string) => {
    if (path === "/api/jobs/j1/trace") return jsonResp(traceBody);
    return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({ error: "nf" }) });
  });
  vi.stubGlobal("fetch", fetchMock);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const utils = render(
    <QueryClientProvider client={qc}>
      <AuditTimeline jobId="j1" />
    </QueryClientProvider>
  );
  return { fetchMock, ...utils };
}

let user: ReturnType<typeof userEvent.setup>;

beforeEach(() => {
  user = userEvent.setup();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AuditTimeline", () => {
  it("fetches trace and renders one row per step (12)", async () => {
    renderTimeline();
    const rows = await screen.findAllByTestId(/^trace-row-/);
    expect(rows).toHaveLength(12);
  });

  it("shows error status dot on the error step and ok dots elsewhere", async () => {
    renderTimeline();
    await screen.findByTestId("trace-row-6");
    expect(screen.getByTestId("trace-status-6")).toHaveAttribute("data-status", "error");
    expect(screen.getByTestId("trace-status-5")).toHaveAttribute("data-status", "ok");
  });

  it("stats card shows correct totals (steps/errors/tokens/duration)", async () => {
    renderTimeline();
    await screen.findByTestId("trace-row-12");
    const totalTokens = steps.reduce((s, x) => s + x.tokens, 0);
    const totalMs = steps.reduce((s, x) => s + x.duration_ms, 0);
    expect(screen.getByTestId("trace-stat-steps")).toHaveTextContent("12");
    expect(screen.getByTestId("trace-stat-errors")).toHaveTextContent("1");
    expect(screen.getByTestId("trace-stat-tokens")).toHaveTextContent(String(totalTokens));
    expect(screen.getByTestId("trace-stat-duration")).toHaveTextContent(
      (totalMs / 1000).toFixed(1)
    );
  });

  it("expanding a commit row reveals reasoning, confidence and rejected items", async () => {
    renderTimeline();
    await screen.findByTestId("trace-row-7");
    expect(screen.queryByTestId("trace-expand-7")).not.toBeInTheDocument();
    await user.click(screen.getByTestId("trace-row-7"));
    const expanded = screen.getByTestId("trace-expand-7");
    expect(expanded).toHaveTextContent("Salicylic acid route is shortest");
    expect(expanded).toHaveTextContent("high");
    expect(expanded).toHaveTextContent("a2");
    expect(expanded).toHaveTextContent("requires controlled substance precursor");
    // args pre + result summary also present
    expect(expanded).toHaveTextContent("committed route branch #0");
    expect(screen.getByTestId("trace-args-7").textContent).toContain("reasoning");
  });

  it("expanding an accept row reveals args.reason quote", async () => {
    renderTimeline();
    await screen.findByTestId("trace-row-8");
    await user.click(screen.getByTestId("trace-row-8"));
    expect(screen.getByTestId("trace-expand-8")).toHaveTextContent("commercial starting material");
  });

  it("refetch button refires trace request", async () => {
    const { fetchMock } = renderTimeline();
    await screen.findByTestId("trace-row-12");
    const before = fetchMock.mock.calls.length;
    await user.click(screen.getByRole("button", { name: "刷新" }));
    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThan(before));
  });

  it("empty steps shows empty state", async () => {
    renderTimeline({ steps: [] });
    expect(await screen.findByTestId("trace-empty")).toBeInTheDocument();
  });
});
