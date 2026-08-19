import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Layout from "../components/Layout";
import LoginPage from "../pages/LoginPage";
import { useAuthStore } from "../stores/auth";

const jsonResp = (status: number, body: unknown) =>
  Promise.resolve({ ok: status >= 200 && status < 300, status, json: () => Promise.resolve(body) });

function LocationDisplay() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname + location.search}</div>;
}

function renderApp(initial = "/") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initial]}>
        <Routes>
          <Route path="/" element={<Layout><div data-testid="page-child" /></Layout>} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="*" element={<LocationDisplay />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function stubFetch(meBody: unknown, changeResp?: () => Response) {
  vi.stubGlobal(
    "fetch",
    vi.fn((path: string) => {
      if (path === "/api/auth/me") return jsonResp(200, meBody);
      if (path === "/api/auth/change-password") {
        return changeResp ? changeResp() : jsonResp(200, { ok: true });
      }
      return jsonResp(200, {});
    })
  );
}

async function openModal(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByTestId("account-menu-trigger"));
  expect(screen.getByTestId("account-menu")).toBeInTheDocument();
  await user.click(screen.getByText("修改密码"));
}

async function fillAndSubmit(user: ReturnType<typeof userEvent.setup>, oldPw = "secret1", newPw = "newpass1", confirm = newPw) {
  await user.type(screen.getByLabelText(/旧密码/), oldPw);
  await user.type(screen.getByLabelText("新密码"), newPw);
  await user.type(screen.getByLabelText("确认新密码"), confirm);
  await user.click(screen.getByRole("button", { name: /确认修改|修改密码|提交/ }));
}

beforeEach(() => {
  useAuthStore.setState({ token: null, role: null });
  vi.unstubAllGlobals();
});

describe("change password", () => {
  it("opens modal from account menu trigger", async () => {
    useAuthStore.setState({ token: "t", role: "user" });
    stubFetch({ id: 1, email: "alice@t.local", role: "user" });
    const user = userEvent.setup();
    renderApp();
    await waitFor(() => expect(screen.getByTestId("account-menu-trigger")).toHaveTextContent("alice"));
    await openModal(user);
    expect(screen.getByLabelText(/旧密码/)).toBeInTheDocument();
    expect(screen.getByLabelText("新密码")).toBeInTheDocument();
    expect(screen.getByLabelText("确认新密码")).toBeInTheDocument();
  });

  it("disables submit with hint when confirm mismatches", async () => {
    useAuthStore.setState({ token: "t", role: "user" });
    const fetchSpy = vi.fn((path: string) => jsonResp(200, path === "/api/auth/me" ? { id: 1, email: "alice@t.local", role: "user" } : {}));
    vi.stubGlobal("fetch", fetchSpy);
    const user = userEvent.setup();
    renderApp();
    await waitFor(() => expect(screen.getByTestId("account-menu-trigger")).toBeInTheDocument());
    await openModal(user);
    await user.type(screen.getByLabelText(/旧密码/), "secret1");
    await user.type(screen.getByLabelText("新密码"), "newpass1");
    await user.type(screen.getByLabelText("确认新密码"), "other12");
    expect(screen.getByRole("button", { name: /确认修改|修改密码|提交/ })).toBeDisabled();
    expect(screen.getByTestId("cpw-hint")).toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalledWith("/api/auth/change-password", expect.anything());
  });

  it("shows error banner on 400 旧密码不正确", async () => {
    useAuthStore.setState({ token: "t", role: "user" });
    stubFetch({ id: 1, email: "alice@t.local", role: "user" }, () => jsonResp(400, { error: "旧密码不正确" }) as unknown as Response);
    const user = userEvent.setup();
    renderApp();
    await waitFor(() => expect(screen.getByTestId("account-menu-trigger")).toBeInTheDocument());
    await openModal(user);
    await fillAndSubmit(user, "wrongpw");
    await waitFor(() => expect(screen.getByTestId("cpw-error")).toHaveTextContent("旧密码不正确"));
    expect(useAuthStore.getState().token).toBe("t");
  });

  it("on success logs out and navigates to /login?changed=1 with banner", async () => {
    useAuthStore.setState({ token: "t", role: "user" });
    let changed = false;
    const fetchSpy = vi.fn((path: string) => {
      if (path === "/api/auth/me") return jsonResp(200, changed ? null : { id: 1, email: "alice@t.local", role: "user" });
      return jsonResp(200, { ok: true });
    });
    vi.stubGlobal("fetch", fetchSpy);
    const user = userEvent.setup();
    renderApp();
    await waitFor(() => expect(screen.getByTestId("account-menu-trigger")).toBeInTheDocument());
    await openModal(user);
    await fillAndSubmit(user);
    await waitFor(() => {
      expect(useAuthStore.getState().token).toBeNull();
      // 路由已跳转到 /login?changed=1（横幅仅在 changed=1 时渲染）
      expect(screen.getByTestId("changed-banner")).toBeInTheDocument();
    });
    changed = true;
    // 在 /login?changed=1 渲染时显示绿色横幅（在独立容器中断言）
    renderApp("/login?changed=1");
    expect(within(document.body).getAllByTestId("changed-banner").length).toBeGreaterThan(0);
  });
});
