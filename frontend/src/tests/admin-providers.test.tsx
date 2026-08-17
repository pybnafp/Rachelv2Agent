import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import AdminProvidersPage from "../pages/AdminProvidersPage";
import { useAuthStore } from "../stores/auth";

const PROVIDERS = [
  {
    id: 1,
    name: "deepseek",
    base_url: "https://api.deepseek.com/v1",
    model: "deepseek-chat",
    temperature: 0.2,
    max_output: 4096,
    is_active: true,
  },
  {
    id: 2,
    name: "openai-compat",
    base_url: "https://llm.example.com/very/long/path/that/should/be/truncated/in/ui",
    model: "gpt-x",
    temperature: null,
    max_output: null,
    is_active: false,
  },
  {
    id: 3,
    name: "mock",
    base_url: "http://localhost",
    model: "mock",
    temperature: null,
    max_output: null,
    is_active: false,
  },
];

const jsonResp = (body: unknown, ok = true, status = 200) =>
  Promise.resolve({ ok, status, json: () => Promise.resolve(body) });

function renderPage(role = "admin") {
  const fetchMock = vi.fn((path: string, init?: RequestInit) => {
    if (path === "/api/auth/me") return jsonResp({ id: 1, username: "a", role });
    if (path === "/api/admin/llm-providers" && (!init || init.method === undefined))
      return jsonResp(PROVIDERS);
    if (path === "/api/admin/llm-providers" && init?.method === "PUT")
      return jsonResp({ id: 9, ...JSON.parse(String(init.body)) });
    return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({ error: "nf" }) });
  });
  vi.stubGlobal("fetch", fetchMock);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const utils = render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <AdminProvidersPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
  return { fetchMock, ...utils };
}

let user: ReturnType<typeof userEvent.setup>;

beforeEach(() => {
  user = userEvent.setup();
  useAuthStore.setState({ token: "t", role: "admin" });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AdminProvidersPage", () => {
  it("renders provider cards with active badge on the current provider", async () => {
    renderPage();
    expect(await screen.findByText("deepseek")).toBeInTheDocument();
    expect(screen.getByText("openai-compat")).toBeInTheDocument();
    expect(screen.getAllByText("mock").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("当前使用")).toBeInTheDocument();
    expect(screen.getAllByText("当前使用")).toHaveLength(1);
  });

  it("设为当前 sends PUT with is_active true and refreshes list", async () => {
    const { fetchMock } = renderPage();
    const buttons = await screen.findAllByRole("button", { name: "设为当前" });
    await user.click(buttons[0]); // first non-active provider = openai-compat
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/admin/llm-providers",
        expect.objectContaining({ method: "PUT" })
      )
    );
    const putCall = fetchMock.mock.calls.find(
      (c) => c[0] === "/api/admin/llm-providers" && (c[1] as any)?.method === "PUT"
    );
    expect(JSON.parse(String((putCall![1] as any).body))).toMatchObject({
      name: "openai-compat",
      is_active: true,
    });
  });

  it("form: submit disabled when required fields (model) empty", async () => {
    renderPage();
    await screen.findByText("deepseek");
    await user.click(screen.getByRole("button", { name: "新增供应商" }));
    const submit = screen.getByRole("button", { name: "保存" });
    expect(submit).toBeDisabled();
    await user.type(screen.getByLabelText("名称"), "p1");
    await user.type(screen.getByLabelText("Base URL"), "https://x.example.com");
    expect(submit).toBeDisabled();
    await user.type(screen.getByLabelText("模型"), "m1");
    expect(submit).toBeEnabled();
  });

  it("api_key plaintext never appears in DOM", async () => {
    renderPage();
    await screen.findByText("deepseek");
    // 打开编辑表单并交互后仍无明文 key
    await user.click(screen.getAllByRole("button", { name: "编辑" })[0]);
    expect(document.body.textContent).not.toContain("sk-");
    const keyInput = screen.getByLabelText("API Key") as HTMLInputElement;
    await user.type(keyInput, "sk-typed-secret");
    expect(document.body.textContent).not.toContain("sk-typed-secret");
  });

  it("non-admin direct access shows 无权限 card", async () => {
    renderPage("user");
    expect(await screen.findByText("无权限")).toBeInTheDocument();
    expect(screen.queryByText("deepseek")).not.toBeInTheDocument();
  });

  it("edit form prefills fields except api_key", async () => {
    renderPage();
    await screen.findByText("deepseek");
    await user.click(screen.getAllByRole("button", { name: "编辑" })[0]);
    expect((screen.getByLabelText("名称") as HTMLInputElement).value).toBe("deepseek");
    expect((screen.getByLabelText("模型") as HTMLInputElement).value).toBe("deepseek-chat");
    expect((screen.getByLabelText("API Key") as HTMLInputElement).value).toBe("");
  });

  it("submit error shows red banner", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const fetchMock = vi.fn((path: string, init?: RequestInit) => {
      if (path === "/api/auth/me") return jsonResp({ id: 1, username: "a", role: "admin" });
      if (path === "/api/admin/llm-providers" && init?.method === "PUT")
        return jsonResp({ error: "invalid provider" }, false, 422);
      if (path === "/api/admin/llm-providers") return jsonResp(PROVIDERS);
      return jsonResp({ error: "nf" }, false, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <AdminProvidersPage />
        </MemoryRouter>
      </QueryClientProvider>
    );
    await screen.findByText("deepseek");
    await user.click(screen.getAllByRole("button", { name: "编辑" })[0]);
    await user.click(screen.getByRole("button", { name: "保存" }));
    expect(await screen.findByText(/invalid provider/)).toBeInTheDocument();
  });
});
