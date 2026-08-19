import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Layout from "../components/Layout";
import { useAuthStore } from "../stores/auth";

const jsonResp = (body: unknown, status = 200) =>
  Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) });

function renderLayout(meBody?: unknown) {
  if (meBody) {
    vi.stubGlobal(
      "fetch",
      vi.fn((path: string) => {
        if (path === "/api/auth/me") return jsonResp(meBody);
        return jsonResp({ error: "nf" }, 404);
      })
    );
  }
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/"]}>
        <Layout>
          <div data-testid="page-child" />
        </Layout>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  useAuthStore.setState({ token: null, role: null });
});

describe("Layout", () => {
  it("shows nav links and logout when token exists", () => {
    useAuthStore.setState({ token: "t", role: "user" });
    renderLayout();
    expect(screen.getByText("提交")).toBeInTheDocument();
    expect(screen.getByText("任务")).toBeInTheDocument();
    expect(screen.getByText("登出")).toBeInTheDocument();
    expect(screen.queryByText("登录")).not.toBeInTheDocument();
  });

  it("shows admin badge when role is admin", () => {
    useAuthStore.setState({ token: "t", role: "admin" });
    renderLayout();
    expect(screen.getByText("admin")).toBeInTheDocument();
  });

  it("shows login/register links when no token", () => {
    renderLayout();
    expect(screen.getByText("登录")).toBeInTheDocument();
    expect(screen.getByText("注册")).toBeInTheDocument();
    expect(screen.queryByText("登出")).not.toBeInTheDocument();
  });

  it("clears token on logout click", () => {
    useAuthStore.setState({ token: "t", role: "user" });
    renderLayout();
    fireEvent.click(screen.getByText("登出"));
    expect(useAuthStore.getState().token).toBeNull();
  });

  it("shows account name without admin badge for regular user", async () => {
    useAuthStore.setState({ token: "t", role: "user" });
    renderLayout({ id: 2, email: "123456@t.local", role: "user" });
    await waitFor(() => {
      expect(screen.getByTestId("account-name")).toHaveTextContent("123456");
    });
    expect(screen.queryByText("admin")).not.toBeInTheDocument();
    expect(screen.getByText("登出")).toBeInTheDocument();
  });

  it("shows account name and admin badge for admin", async () => {
    useAuthStore.setState({ token: "t", role: "admin" });
    renderLayout({ id: 1, email: "adm@t.local", role: "admin" });
    await waitFor(() => {
      expect(screen.getByTestId("account-name")).toHaveTextContent("adm");
    });
    expect(screen.getByText("admin")).toBeInTheDocument();
  });
});
