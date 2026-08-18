import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useAuthStore } from "../stores/auth";
import { formatDuration } from "../lib/format";

vi.mock("../components/MoleculeView", () => ({
  MoleculeView: () => <span data-testid="mock-mol" />,
}));

import JobsPage from "../pages/JobsPage";

const RUNNING: any = {
  id: "j-run",
  smiles: "CC(=O)OC1=CC=CC=C1C(=O)O",
  name: "",
  status: "running",
  error: "",
  stats: { steps: 3 },
  created_at: "2026-08-17T10:00:00Z",
  started_at: "2026-08-17T10:00:10Z",
  finished_at: null,
};
const DONE: any = {
  id: "j-done",
  smiles: "c1ccccc1",
  name: "苯路线",
  status: "succeeded",
  error: "",
  stats: { steps: 12 },
  created_at: "2026-08-16T09:00:00Z",
  started_at: "2026-08-16T09:00:00Z",
  finished_at: "2026-08-16T09:12:30Z",
};

const jsonResp = (body: unknown) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });

let user: ReturnType<typeof userEvent.setup>;
let fetchMock: ReturnType<typeof vi.fn>;

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/jobs"]}>
        <JobsPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  user = userEvent.setup();
  useAuthStore.setState({ token: "t", role: "user" });
  fetchMock = vi.fn(() => jsonResp([RUNNING, DONE]));
  vi.stubGlobal("fetch", fetchMock);
  vi.spyOn(window, "confirm").mockReturnValue(true);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("JobsPage", () => {
  it("renders two rows with status badges, unnamed fallback and duration", async () => {
    renderPage();
    expect(await screen.findByTestId("status-running")).toBeInTheDocument();
    expect(screen.getByTestId("status-succeeded")).toBeInTheDocument();
    expect(screen.getByText("(未命名)")).toBeInTheDocument();
    expect(screen.getByText("苯路线")).toBeInTheDocument();
    expect(screen.getByText(/12 步/)).toBeInTheDocument();
    expect(screen.getByText(/12m30s/)).toBeInTheDocument();
    expect(screen.getByText(/3 步/)).toBeInTheDocument();
    expect(screen.getByText(/—/)).toBeInTheDocument();
  });

  it("shows cancel only for running rows and posts cancel on click", async () => {
    renderPage();
    await screen.findByTestId("status-running");
    const cancelBtns = screen.getAllByRole("button", { name: "取消" });
    expect(cancelBtns).toHaveLength(1);
    await user.click(cancelBtns[0]);
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith("/api/jobs/j-run/cancel", expect.objectContaining({ method: "POST" }))
    );
  });

  it("deletes a job and removes its row", async () => {
    renderPage();
    await screen.findByTestId("status-running");
    fetchMock.mockImplementation((path: string) =>
      path === "/api/jobs/j-run" ? jsonResp({}) : path.startsWith("/api/jobs?") ? jsonResp([DONE]) : jsonResp({})
    );
    await user.click(screen.getAllByRole("button", { name: "删除" })[0]);
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith("/api/jobs/j-run", expect.objectContaining({ method: "DELETE" }))
    );
    await waitFor(() => expect(screen.queryByTestId("status-running")).not.toBeInTheDocument());
    expect(screen.getByTestId("status-succeeded")).toBeInTheDocument();
  });

  it("shows delete error message when delete request fails", async () => {
    fetchMock.mockImplementation((path: string) =>
      path === "/api/jobs/j-run"
        ? Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({ error: "fk violation" }) })
        : jsonResp(path.startsWith("/api/jobs?") ? [RUNNING, DONE] : {})
    );
    renderPage();
    await screen.findByTestId("status-running");
    await user.click(screen.getAllByRole("button", { name: "删除" })[0]);
    expect(await screen.findByTestId("delete-error")).toHaveTextContent("fk violation");
  });

  it("shows empty state for empty list", async () => {
    fetchMock.mockImplementation(() => jsonResp([]));
    renderPage();
    expect(await screen.findByText("还没有任务")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "去提交" })).toBeInTheDocument();
  });
});

describe("formatDuration", () => {
  it("formats durations and returns dash for unfinished", () => {
    expect(formatDuration("2026-08-16T09:00:00Z", "2026-08-16T09:00:45Z")).toBe("45s");
    expect(formatDuration("2026-08-16T09:00:00Z", "2026-08-16T09:12:30Z")).toBe("12m30s");
    expect(formatDuration("2026-08-16T09:00:00Z", "2026-08-16T11:05:03Z")).toBe("2h5m3s");
    expect(formatDuration("2026-08-16T09:00:00Z", null)).toBe("—");
    expect(formatDuration(null, "2026-08-16T09:00:00Z")).toBe("—");
  });
});
