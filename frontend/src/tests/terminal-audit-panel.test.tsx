import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { TerminalAuditPanel } from "../components/TerminalAuditPanel";
import type { TerminalAudit, TerminalAuditResult } from "../types";

vi.mock("../components/MoleculeView", () => ({
  MoleculeView: () => <span data-testid="mock-mol" />,
}));

const availableResults: TerminalAuditResult[] = [
  {
    node_id: "mol_2",
    smiles: "c1ccc(O)cc1",
    cs_score: 3.456,
    rachel_classification: "commercial starting material",
    pubchem: { queried: true, best_cid: 704, best_cid_url: "https://pubchem.ncbi.nlm.nih.gov/compound/704" },
    pubchem_metrics: { pubchem_cid_closed: true, vendor_closed: true },
    allowlist: { hit: false },
    buyability_decision: { state: "buyable" },
  },
  {
    node_id: "mol_3",
    smiles: "CC(=O)OC1=CC=CC=C1C(=O)O",
    cs_score: 5.12,
    rachel_classification: "intermediate",
    pubchem: { queried: true, best_cid: null, best_cid_url: "" },
    pubchem_metrics: { pubchem_cid_closed: true, vendor_closed: false },
    allowlist: { hit: true },
    buyability_decision: {},
  },
  {
    node_id: "mol_5",
    smiles: "O=C(O)c1ccccc1",
    cs_score: 2.8,
    rachel_classification: "commercial starting material",
    pubchem: { queried: true, best_cid: null, best_cid_url: "" },
    pubchem_metrics: { pubchem_cid_closed: false, vendor_closed: false },
    allowlist: { hit: false },
    buyability_decision: {},
  },
];

const availableAudit: TerminalAudit = {
  available: true,
  offline: false,
  summary: {
    total_terminals: 3,
    pubchem_cid_closed: 2,
    vendor_closed: 1,
  },
  results: availableResults,
};

const unavailableAudit: TerminalAudit = {
  available: false,
  error: "FileNotFoundError: terminals.json",
};

const basicTerminals = availableResults.map((r) => ({
  node_id: r.node_id,
  smiles: r.smiles,
  cs_score: r.cs_score,
}));

function renderPanel(terminals: any, audit: TerminalAudit | null) {
  return render(<TerminalAuditPanel terminals={terminals} audit={audit} />);
}

describe("TerminalAuditPanel", () => {
  it("available: renders summary counts with closure fractions", () => {
    renderPanel(availableResults, availableAudit);
    expect(screen.getByTestId("audit-summary")).toHaveTextContent("2/3");
    expect(screen.getByTestId("audit-summary")).toHaveTextContent("1/3");
    expect(screen.getByTestId("audit-summary")).toHaveTextContent("CID");
    expect(screen.getByTestId("audit-summary")).toHaveTextContent("Vendor");
  });

  it("available: CID link points at pubchem url; others show dash", () => {
    renderPanel(availableResults, availableAudit);
    const link = screen.getByRole("link", { name: /CID 704/ });
    expect(link).toHaveAttribute("href", "https://pubchem.ncbi.nlm.nih.gov/compound/704");
    expect(link).toHaveAttribute("target", "_blank");
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(2);
  });

  it("available: closure badges match metrics (green when closed)", () => {
    renderPanel(availableResults, availableAudit);
    expect(screen.getByTestId("cid-badge-mol_2")).toHaveTextContent("CID✓");
    expect(screen.getByTestId("cid-badge-mol_5")).toHaveTextContent("CID✗");
    expect(screen.getByTestId("vendor-badge-mol_2")).toHaveTextContent("Vendor✓");
    expect(screen.getByTestId("vendor-badge-mol_3")).toHaveTextContent("Vendor✗");
  });

  it("available: allowlist hit row shows allowlist badge", () => {
    renderPanel(availableResults, availableAudit);
    expect(screen.getByTestId("allowlist-badge-mol_3")).toBeInTheDocument();
    expect(screen.queryByTestId("allowlist-badge-mol_2")).not.toBeInTheDocument();
  });

  it("available: three molecule rows keyed by node_id with CS score 2dp", () => {
    renderPanel(availableResults, availableAudit);
    for (const id of ["mol_2", "mol_3", "mol_5"]) {
      expect(screen.getByTestId(`terminal-row-${id}`)).toBeInTheDocument();
    }
    expect(screen.getByTestId("terminal-row-mol_2")).toHaveTextContent("3.46");
  });

  it("unavailable: shows amber banner and still renders basic table", () => {
    renderPanel(basicTerminals, unavailableAudit);
    expect(screen.getByTestId("audit-unavailable")).toBeInTheDocument();
    expect(screen.getByTestId("audit-unavailable")).toHaveTextContent("终点审计不可用");
    expect(screen.getByTestId("audit-unavailable")).toHaveTextContent("FileNotFoundError");
    for (const id of ["mol_2", "mol_3", "mol_5"]) {
      expect(screen.getByTestId(`terminal-row-${id}`)).toBeInTheDocument();
    }
    expect(screen.queryByTestId("cid-badge-mol_2")).not.toBeInTheDocument();
  });

  it("null audit: shows amber banner and basic table", () => {
    renderPanel(basicTerminals, null);
    expect(screen.getByTestId("audit-unavailable")).toBeInTheDocument();
    expect(screen.getByTestId("terminal-row-mol_2")).toBeInTheDocument();
  });
});
