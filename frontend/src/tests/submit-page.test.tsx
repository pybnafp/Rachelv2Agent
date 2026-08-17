import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useAuthStore } from "../stores/auth";

vi.mock("../components/MoleculeView", () => ({
  MoleculeView: () => <span data-testid="mock-mol" />,
}));

const isValid = vi.fn(() => true);
const molDelete = vi.fn();
vi.mock("../rdkit", () => ({
  getRDKit: () => Promise.resolve({ get_mol: () => ({ is_valid: () => isValid(), delete: molDelete }) }),
}));

import SubmitPage from "../pages/SubmitPage";

const ASPIRIN = "CC(=O)OC1=CC=CC=C1C(=O)O";

function LocationDisplay() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<SubmitPage />} />
          <Route path="*" element={<LocationDisplay />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

const jsonResp = (status: number, body: unknown) =>
  Promise.resolve({ ok: status >= 200 && status < 300, status, json: () => Promise.resolve(body) });

let user: ReturnType<typeof userEvent.setup>;
let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
  useAuthStore.setState({ token: "t", role: "user" });
  isValid.mockReturnValue(true);
  isValid.mockClear();
  molDelete.mockClear();
  fetchMock = vi.fn(() => jsonResp(200, { username: "u", role: "user" }));
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("SubmitPage", () => {
  it("example button fills textarea and validity turns green", async () => {
    renderPage();
    await user.click(screen.getByRole("button", { name: "阿司匹林" }));
    const ta = screen.getByRole("textbox", { name: /SMILES/ }) as HTMLTextAreaElement;
    expect(ta.value).toBe(ASPIRIN);
    await waitFor(() => expect(screen.getByTestId("validity").textContent).toContain("有效"));
    expect(screen.getByTestId("validity").className).toContain("text-emerald");
    expect(molDelete).toHaveBeenCalled();
  });

  it("shows invalid in red when rdkit says invalid", async () => {
    isValid.mockReturnValue(false);
    renderPage();
    await user.click(screen.getByRole("button", { name: "苯" }));
    await waitFor(() => expect(screen.getByTestId("validity").textContent).toContain("无效"));
    expect(screen.getByTestId("validity").className).toContain("text-red");
  });

  it("submits job with correct body and navigates to /jobs/:id", async () => {
    fetchMock.mockImplementation((path: string) =>
      path === "/api/jobs" ? jsonResp(200, { id: "j1" }) : jsonResp(200, { username: "u", role: "user" })
    );
    renderPage();
    await user.type(screen.getByLabelText(/任务名/), "my job");
    await user.click(screen.getByRole("button", { name: "阿司匹林" }));
    await user.click(screen.getByRole("button", { name: /提交/ }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/jobs",
        expect.objectContaining({ method: "POST", body: JSON.stringify({ smiles: ASPIRIN, name: "my job" }) })
      )
    );
    await waitFor(() => expect(screen.getByTestId("location").textContent).toBe("/jobs/j1"));
  });

  it("shows error banner on 400", async () => {
    fetchMock.mockImplementation((path: string) =>
      path === "/api/jobs" ? jsonResp(400, { error: "invalid SMILES: x" }) : jsonResp(200, { username: "u", role: "user" })
    );
    renderPage();
    await user.click(screen.getByRole("button", { name: "阿司匹林" }));
    await user.click(screen.getByRole("button", { name: /提交/ }));
    await waitFor(() => expect(screen.getByTestId("submit-error")).toHaveTextContent("invalid SMILES: x"));
  });

  it("hides admin LLM provider section for non-admin", async () => {
    renderPage();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/auth/me", expect.anything()));
    expect(screen.queryByText(/LLM/)).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalledWith("/api/admin/llm-providers", expect.anything());
  });

  it("shows read-only LLM providers for admin", async () => {
    useAuthStore.setState({ token: "t", role: "admin" });
    fetchMock.mockImplementation((path: string) => {
      if (path === "/api/admin/llm-providers")
        return jsonResp(200, [{ name: "openai", model: "gpt-4", is_active: true }]);
      return jsonResp(200, { username: "admin", role: "admin" });
    });
    renderPage();
    await waitFor(() => expect(screen.getByTestId("llm-providers")).toBeInTheDocument());
    expect(screen.getByText("openai")).toBeInTheDocument();
    expect(screen.getByText("gpt-4")).toBeInTheDocument();
  });
});
