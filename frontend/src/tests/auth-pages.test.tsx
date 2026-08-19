import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route, useLocation } from "react-router-dom";
import { useAuthStore } from "../stores/auth";
import LoginPage from "../pages/LoginPage";
import RegisterPage from "../pages/RegisterPage";

function LocationDisplay() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

function renderAt(initial: string) {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="*" element={<LocationDisplay />} />
      </Routes>
    </MemoryRouter>
  );
}

const jsonResp = (status: number, body: unknown) =>
  Promise.resolve({ ok: status >= 200 && status < 300, status, json: () => Promise.resolve(body) } as unknown as Response);

beforeEach(() => {
  useAuthStore.setState({ token: null, role: null });
  vi.unstubAllGlobals();
});

describe("auth pages", () => {
  it("login route renders page-login and register route renders page-register", () => {
    const { unmount } = renderAt("/login");
    expect(screen.getByTestId("page-login")).toBeInTheDocument();
    unmount();
    renderAt("/register");
    expect(screen.getByTestId("page-register")).toBeInTheDocument();
  });

  it("login: disables submit and skips fetch when password too short", async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    const user = userEvent.setup();
    renderAt("/login");
    await user.type(screen.getByLabelText(/邮箱/), "alice@t.local");
    await user.type(screen.getByLabelText("密码"), "12345");
    const btn = screen.getByRole("button", { name: /登录/ });
    expect(btn).toBeDisabled();
    expect(screen.getByTestId("form-hint")).toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("login happy path: stores token and navigates to /", async () => {
    const fetchSpy = vi.fn(() => jsonResp(200, { access_token: "t", role: "user" }));
    vi.stubGlobal("fetch", fetchSpy);
    const user = userEvent.setup();
    renderAt("/login");
    await user.type(screen.getByLabelText(/邮箱/), "alice@t.local");
    await user.type(screen.getByLabelText("密码"), "secret1");
    await user.click(screen.getByRole("button", { name: /登录/ }));
    await waitFor(() => expect(useAuthStore.getState().token).toBe("t"));
    expect(useAuthStore.getState().role).toBe("user");
    await waitFor(() => expect(screen.getByTestId("location").textContent).toBe("/"));
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/auth/login",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ email: "alice@t.local", password: "secret1" }) })
    );
  });

  it("login 401: shows error banner", async () => {
    vi.stubGlobal("fetch", vi.fn(() => jsonResp(401, { error: "邮箱或密码错误" })));
    const user = userEvent.setup();
    renderAt("/login");
    await user.type(screen.getByLabelText(/邮箱/), "alice@t.local");
    await user.type(screen.getByLabelText("密码"), "secret1");
    await user.click(screen.getByRole("button", { name: /登录/ }));
    await waitFor(() => expect(screen.getByTestId("auth-error")).toHaveTextContent("邮箱或密码错误"));
  });

  it("login 403: switches to inline verify block prefilled; verify success stores token and navigates", async () => {
    const fetchSpy = vi.fn((path: string) => {
      if (path === "/api/auth/login") return jsonResp(403, { error: "邮箱未验证，请查收验证码" });
      if (path === "/api/auth/verify") return jsonResp(200, { access_token: "tv", role: "user" });
      if (path === "/api/auth/resend") return jsonResp(200, { ok: true });
      return jsonResp(404, {});
    });
    vi.stubGlobal("fetch", fetchSpy as any);
    const user = userEvent.setup();
    renderAt("/login");
    await user.type(screen.getByLabelText(/邮箱/), "alice@t.local");
    await user.type(screen.getByLabelText("密码"), "secret1");
    await user.click(screen.getByRole("button", { name: /登录/ }));
    await waitFor(() => expect(screen.getByTestId("verify-step")).toBeInTheDocument());
    expect(screen.getByText(/alice@t\.local/)).toBeInTheDocument();
    await user.type(screen.getByLabelText(/验证码/), "123456");
    await user.click(screen.getByRole("button", { name: /提交/ }));
    await waitFor(() => expect(useAuthStore.getState().token).toBe("tv"));
    await waitFor(() => expect(screen.getByTestId("location").textContent).toBe("/"));
  });

  it("login 403 verify block: resend click posts resend; 429 resets countdown and disables button", async () => {
    const fetchSpy = vi.fn((path: string) => {
      if (path === "/api/auth/login") return jsonResp(403, { error: "邮箱未验证，请查收验证码" });
      if (path === "/api/auth/resend") return jsonResp(429, { error: "发送过于频繁" });
      return jsonResp(404, {});
    });
    vi.stubGlobal("fetch", fetchSpy as any);
    const user = userEvent.setup();
    renderAt("/login");
    await user.type(screen.getByLabelText(/邮箱/), "alice@t.local");
    await user.type(screen.getByLabelText("密码"), "secret1");
    await user.click(screen.getByRole("button", { name: /登录/ }));
    await waitFor(() => expect(screen.getByTestId("verify-step")).toBeInTheDocument());
    const resend = await screen.findByTestId("resend-btn");
    expect(resend).toBeEnabled();
    await user.click(resend);
    await waitFor(() =>
      expect(fetchSpy).toHaveBeenCalledWith("/api/auth/resend", expect.objectContaining({ method: "POST" }))
    );
    await waitFor(() => expect(screen.getByTestId("resend-btn")).toBeDisabled());
    expect(screen.getByTestId("resend-btn")).toHaveTextContent(/60/);
  });

  it("register happy path: 202 then verify 200 stores token and navigates", async () => {
    const fetchSpy = vi.fn((path: string) => {
      if (path === "/api/auth/register") return jsonResp(202, { ok: true, message: "验证码已发送至邮箱" });
      if (path === "/api/auth/verify") return jsonResp(200, { access_token: "t2", role: "user" });
      return jsonResp(404, {});
    });
    vi.stubGlobal("fetch", fetchSpy as any);
    const user = userEvent.setup();
    renderAt("/register");
    await user.type(screen.getByLabelText(/邮箱/), "bob@t.local");
    await user.type(screen.getByLabelText("密码"), "secret2");
    await user.type(screen.getByLabelText("确认密码"), "secret2");
    await user.click(screen.getByRole("button", { name: /注册/ }));
    await waitFor(() => expect(screen.getByTestId("verify-step")).toBeInTheDocument());
    expect(screen.getByText(/bob@t\.local/)).toBeInTheDocument();
    // resend 处于 60s 冷却
    expect(screen.getByTestId("resend-btn")).toBeDisabled();
    await user.type(screen.getByLabelText(/验证码/), "654321");
    await user.click(screen.getByRole("button", { name: /提交/ }));
    await waitFor(() => expect(useAuthStore.getState().token).toBe("t2"));
    await waitFor(() => expect(screen.getByTestId("location").textContent).toBe("/"));
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/auth/register",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ email: "bob@t.local", password: "secret2" }) })
    );
  });

  it("register 409: banner shown and stays on step 1", async () => {
    const fetchSpy = vi.fn(() => jsonResp(409, { error: "邮箱已注册" }));
    vi.stubGlobal("fetch", fetchSpy as any);
    const user = userEvent.setup();
    renderAt("/register");
    await user.type(screen.getByLabelText(/邮箱/), "bob@t.local");
    await user.type(screen.getByLabelText("密码"), "secret2");
    await user.type(screen.getByLabelText("确认密码"), "secret2");
    await user.click(screen.getByRole("button", { name: /注册/ }));
    await waitFor(() => expect(screen.getByTestId("auth-error")).toHaveTextContent("邮箱已注册，请直接登录"));
    expect(screen.queryByTestId("verify-step")).not.toBeInTheDocument();
  });

  it("register 429: shows cooldown banner but still advances to step 2", async () => {
    vi.stubGlobal("fetch", vi.fn(() => jsonResp(429, { error: "too soon" })) as any);
    const user = userEvent.setup();
    renderAt("/register");
    await user.type(screen.getByLabelText(/邮箱/), "bob@t.local");
    await user.type(screen.getByLabelText("密码"), "secret2");
    await user.type(screen.getByLabelText("确认密码"), "secret2");
    await user.click(screen.getByRole("button", { name: /注册/ }));
    await waitFor(() => expect(screen.getByTestId("auth-error")).toHaveTextContent("发送过于频繁，请稍后再试"));
    expect(screen.getByTestId("verify-step")).toBeInTheDocument();
  });

  it("register step 2 wrong code 400: banner shown, stays on step 2", async () => {
    const fetchSpy = vi.fn((path: string) => {
      if (path === "/api/auth/register") return jsonResp(202, { ok: true });
      if (path === "/api/auth/verify") return jsonResp(400, { error: "验证码错误或已过期" });
      return jsonResp(404, {});
    });
    vi.stubGlobal("fetch", fetchSpy as any);
    const user = userEvent.setup();
    renderAt("/register");
    await user.type(screen.getByLabelText(/邮箱/), "bob@t.local");
    await user.type(screen.getByLabelText("密码"), "secret2");
    await user.type(screen.getByLabelText("确认密码"), "secret2");
    await user.click(screen.getByRole("button", { name: /注册/ }));
    await waitFor(() => expect(screen.getByTestId("verify-step")).toBeInTheDocument());
    await user.type(screen.getByLabelText(/验证码/), "000000");
    await user.click(screen.getByRole("button", { name: /提交/ }));
    await waitFor(() => expect(screen.getByTestId("auth-error")).toHaveTextContent("验证码错误或已过期"));
    expect(screen.getByTestId("verify-step")).toBeInTheDocument();
    expect(useAuthStore.getState().token).toBeNull();
  });

  it("links between login and register", async () => {
    const user = userEvent.setup();
    renderAt("/login");
    await user.click(screen.getByRole("link", { name: /注册/ }));
    await waitFor(() => expect(screen.getByTestId("page-register")).toBeInTheDocument());
  });
});
