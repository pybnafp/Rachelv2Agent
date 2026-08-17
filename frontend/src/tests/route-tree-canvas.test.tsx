import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { useAuthStore } from "../stores/auth";

vi.mock("../components/MoleculeView", () => ({
  MoleculeView: () => <span data-testid="mock-mol" />,
}));

import RouteTreeCanvas from "../components/RouteTreeCanvas";
import JobDetailPage from "../pages/JobDetailPage";
import visFixture from "./fixtures/visualization.json";
import type { Visualization } from "../types";

const vis = visFixture as unknown as Visualization;

// user-event assigns `view: null` on dispatched MouseEvents, which crashes
// d3-zoom/d3-drag (React Flow's pan layer). Native element.click() carries a
// proper view, so node-click interactions use it instead.
const click = (el: Element) => act(() => void el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true })));

beforeEach(() => {
  useAuthStore.setState({ token: "t", role: "user" });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("RouteTreeCanvas", () => {
  it("renders 17 molecule cards (one mock-mol each)", () => {
    render(<RouteTreeCanvas vis={vis} />);
    expect(screen.getAllByTestId("mock-mol")).toHaveLength(17);
  });

  it("renders a reaction pill containing 'Reductive amination'", () => {
    render(<RouteTreeCanvas vis={vis} />);
    const pill = screen.getByTestId("rxn-pill-rxn_1");
    // label is truncated to 18 chars per spec; full label in title attr
    expect(pill).toHaveTextContent("Reductive aminatio");
    expect(pill).toHaveAttribute("title", "Reductive amination");
  });

  it("clicking terminal molecule mol_2 opens drawer with its SMILES", async () => {
    render(<RouteTreeCanvas vis={vis} />);
    expect(screen.queryByTestId("node-drawer")).not.toBeInTheDocument();
    await click(screen.getByTestId("mol-card-mol_2"));
    expect(screen.getByTestId("node-drawer")).toBeInTheDocument();
    const mol2 = vis.nodes.find((n) => n.id === "mol_2") as { smiles: string };
    expect(screen.getByTestId("drawer-smiles")).toHaveTextContent(mol2.smiles);
    // closable
    await click(screen.getByTestId("drawer-close"));
    expect(screen.queryByTestId("node-drawer")).not.toBeInTheDocument();
  });

  // NOTE on edge-click interaction: React Flow renders edges as SVG paths inside
  // a d3-zoom viewport; reliable click simulation in jsdom is not feasible
  // (getBoundingClientRect returns zeros, path hit-areas don't register).
  // Edge info is therefore asserted indirectly via the reaction node, whose
  // drawer exposes the reaction_smiles that fully describes the edges it
  // participates in. onEdgeClick is wired in the component for real browsers.
  it("clicking reaction rxn_1 opens drawer with label and reaction_smiles", async () => {
    render(<RouteTreeCanvas vis={vis} />);
    await click(screen.getByTestId("rxn-pill-rxn_1"));
    const drawer = screen.getByTestId("node-drawer");
    expect(drawer).toHaveTextContent("Reductive amination");
    const rxn1 = vis.nodes.find((n) => n.id === "rxn_1") as { reaction_smiles?: string };
    const rs = rxn1.reaction_smiles ?? "";
    expect(screen.getByTestId("drawer-rxn-smiles")).toHaveTextContent(rs.slice(0, 30));
  });
});

describe("JobDetailPage integration (tree tab)", () => {
  const jsonResp = (status: number, body: unknown) =>
    Promise.resolve({ ok: status >= 200 && status < 300, status, json: () => Promise.resolve(body) });

  const job = {
    id: "j1",
    smiles: "CC(=O)CCO",
    name: "demo",
    status: "succeeded",
    error: "",
    stats: { steps: 11 },
    created_at: "2026-08-17T10:00:00Z",
    started_at: "2026-08-17T10:00:10Z",
    finished_at: "2026-08-17T10:20:00Z",
  };

  function renderPage(resultFixture: unknown) {
    const fetchMock = vi.fn((path: string) => {
      if (path === "/api/jobs/j1") return jsonResp(200, job);
      if (path === "/api/jobs/j1/result") return jsonResp(200, resultFixture);
      return jsonResp(404, { error: "not found" });
    });
    vi.stubGlobal("fetch", fetchMock);
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/jobs/j1"]}>
          <Routes>
            <Route path="/jobs/:id" element={<JobDetailPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );
  }

  it("succeeded job with visualization renders canvas instead of placeholder", async () => {
    renderPage({ job, visualization: vis });
    const tab = await screen.findByTestId("tab-tree");
    await waitFor(() =>
      expect(tab.querySelectorAll('[data-testid="mock-mol"]')).toHaveLength(17)
    );
    expect(tab).not.toHaveTextContent("路线树将在此渲染");
  });

  it("succeeded job with incomplete visualization shows 产物不完整 card", async () => {
    renderPage({ job });
    const tab = await screen.findByTestId("tab-tree");
    expect(tab).toHaveTextContent("产物不完整");
    expect(screen.queryByTestId("route-tree-canvas")).not.toBeInTheDocument();
  });
});
