import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useAuthStore } from "../stores/auth";

vi.mock("../components/MoleculeView", () => ({
  MoleculeView: () => <span data-testid="mock-mol" />,
}));

import JobDetailPage from "../pages/JobDetailPage";

const jsonResp = (status: number, body: unknown) =>
  Promise.resolve({ ok: status >= 200 && status < 300, status, json: () => Promise.resolve(body) });

const mkJob = (over: Record<string, unknown>): any => ({
  id: "j1",
  smiles: "CC(=O)OC1=CC=CC=C1C(=O)O",
  name: "阿司匹林",
  status: "succeeded",
  error: "",
  stats: { steps: 10, tokens_in: 1000, tokens_out: 2000 },
  created_at: "2026-08-17T10:00:00Z",
  started_at: "2026-08-17T10:00:10Z",
  finished_at: "2026-08-17T10:20:00Z",
  ...over,
});

function LocationDisplay() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname + location.search}</div>;
}

function renderPage(jobFixture: any, resultFixture?: unknown) {
  const fetchMock = vi.fn((path: string) => {
    if (path === "/api/jobs/j1") return jsonResp(200, jobFixture);
    if (path === "/api/jobs/j1/result")
      return resultFixture ? jsonResp(200, resultFixture) : jsonResp(200, { job: jobFixture });
    return jsonResp(404, { error: "not found" });
  });
  vi.stubGlobal("fetch", fetchMock);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const utils = render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/jobs/j1"]}>
        <Routes>
          <Route path="/jobs/:id" element={<JobDetailPage />} />
          <Route path="*" element={<LocationDisplay />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
  return { fetchMock, ...utils };
}

let user: ReturnType<typeof userEvent.setup>;

beforeEach(() => {
  user = userEvent.setup();
  useAuthStore.setState({ token: "t", role: "user" });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("JobDetailPage", () => {
  it("running job shows running hint and no tree tab", async () => {
    renderPage(mkJob({ status: "running", finished_at: null }));
    expect(await screen.findByTestId("running-hint")).toBeInTheDocument();
    expect(screen.getByTestId("status-running")).toBeInTheDocument();
    expect(screen.queryByTestId("tab-tree")).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "路线树" })).not.toBeInTheDocument();
  });

  it("succeeded job shows tabs and metrics from result", async () => {
    renderPage(mkJob({}), { job: mkJob({}), metrics: { n_nodes: 28, n_edges: 27, n_terminals: 6 } });
    expect(await screen.findByTestId("tab-tree")).toBeInTheDocument();
    expect(screen.getByTestId("tab-report")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "文件" }));
    await waitFor(() => expect(screen.getByText("28")).toBeInTheDocument());
    expect(screen.getByText("27")).toBeInTheDocument();
    expect(screen.getByText("6")).toBeInTheDocument();
  });

  it("report tab embeds synthesis report iframe with token query", async () => {
    renderPage(mkJob({}), { job: mkJob({}), metrics: { n_nodes: 1, n_edges: 1, n_terminals: 1 } });
    await screen.findByTestId("tab-report");
    await user.click(screen.getByRole("tab", { name: "报告" }));
    const iframe = screen.getByTestId("report-iframe");
    expect(iframe).toHaveAttribute("src", "/api/jobs/j1/files/export/SYNTHESIS_REPORT.html?token=t");
    const open = screen.getByTestId("report-open");
    expect(open).toHaveAttribute("href", "/api/jobs/j1/files/export/SYNTHESIS_REPORT.html?token=t");
    expect(open).toHaveAttribute("target", "_blank");
  });

  it("files tab lists download links with token query", async () => {
    renderPage(mkJob({}), { job: mkJob({}), metrics: { n_nodes: 1, n_edges: 1, n_terminals: 1 } });
    await screen.findByTestId("tab-files");
    await user.click(screen.getByRole("tab", { name: "文件" }));
    const links = screen.getAllByTestId(/^dl-/);
    expect(links.length).toBeGreaterThanOrEqual(7);
    for (const a of links) {
      expect(a.getAttribute("href")).toContain("?token=t");
      expect(a).toHaveAttribute("download");
    }
    expect(screen.getByTestId("dl-report.txt").getAttribute("href")).toBe(
      "/api/jobs/j1/files/export/report.txt?token=t"
    );
  });

  it("failed job shows error block with message", async () => {
    renderPage(mkJob({ status: "failed", error: "llm exploded" }));
    expect(await screen.findByTestId("job-error")).toHaveTextContent("llm exploded");
    expect(screen.queryByTestId("tab-tree")).not.toBeInTheDocument();
  });

  it("cancelled job offers resubmit link containing smiles", async () => {
    renderPage(mkJob({ status: "cancelled" }));
    const btn = await screen.findByRole("button", { name: "重新提交" });
    await user.click(btn);
    await waitFor(() =>
      expect(screen.getByTestId("location").textContent).toBe(
        `/?smiles=${encodeURIComponent("CC(=O)OC1=CC=CC=C1C(=O)O")}`
      )
    );
  });
});
