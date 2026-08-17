import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const fakeMol = {
  is_valid: () => true,
  get_svg: () => "<svg/>",
  delete: vi.fn(),
};
const invalidMol = {
  is_valid: () => false,
  get_svg: () => "<svg/>",
  delete: vi.fn(),
};

const getRDKit = vi.fn(() => Promise.resolve({ get_mol: () => fakeMol }));

vi.mock("../rdkit", () => ({ getRDKit: () => getRDKit() }));

import { MoleculeView } from "../components/MoleculeView";

describe("MoleculeView", () => {
  beforeEach(() => {
    getRDKit.mockReset();
    fakeMol.delete.mockClear();
    invalidMol.delete.mockClear();
  });

  it("renders svg for a valid molecule", async () => {
    getRDKit.mockImplementation(() => Promise.resolve({ get_mol: () => fakeMol }));
    render(<MoleculeView smiles="CCO" />);
    await waitFor(() => expect(screen.getByTestId("mol-svg")).toBeTruthy());
    expect(screen.getByTestId("mol-svg").querySelector("svg")).toBeTruthy();
    expect(fakeMol.delete).toHaveBeenCalled();
  });

  it("renders mol-invalid for invalid molecule", async () => {
    getRDKit.mockImplementation(() => Promise.resolve({ get_mol: () => invalidMol }));
    render(<MoleculeView smiles="not-a-smiles" />);
    await waitFor(() => expect(screen.getByTestId("mol-invalid")).toBeTruthy());
    expect(invalidMol.delete).toHaveBeenCalled();
  });

  it("renders mol-invalid when getRDKit rejects", async () => {
    getRDKit.mockImplementation(() => Promise.reject(new Error("wasm fail")));
    render(<MoleculeView smiles="CCO" />);
    await waitFor(() => expect(screen.getByTestId("mol-invalid")).toBeTruthy());
  });

  it("shows loading placeholder first", async () => {
    getRDKit.mockImplementation(() => new Promise(() => {}));
    render(<MoleculeView smiles="CCO" />);
    expect(screen.getByTestId("mol-loading")).toBeTruthy();
  });
});
