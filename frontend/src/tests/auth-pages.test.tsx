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

function renderAt(path: string, initial: string) {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="*" element={<LocationDisplay />} />
      </Routes>
    </MemoryRouter>
  );
  void path;
}

const jsonResp = (status: number, body: unknown) =>
  Promise.resolve({ ok: status >= 200 && status < 300, status, json: () => Promise.resolve(body) });

beforeEach(() => {
  useAuthStore.setState({ token: null, role: null });
  vi.unstubAllGlobals();
});

describe("auth pages", () => {
  it("login route renders page-login and register route renders page-register", () => {
    const { unmount } = renderAt("", "/login");
    expect(screen.getByTestId("page-login")).toBeInTheDocument();
    unmount();
    renderAt("", "/register");
    expect(screen.getByTestId("page-register")).toBeInTheDocument();
  });

  it("disables submit and skips fetch when password too short", async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    const user = userEvent.setup();
    renderAt("", "/login");
    await user.type(screen.getByLabelText(/用户名/), "ab");
    await user.type(screen.getByLabelText(/密码/), "12345");
    const btn = screen.getByRole("button", { name: /登录/ });
    expect(btn).toBeDisabled();
    expect(screen.getByTestId("form-hint")).toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("logs in successfully: stores token and navigates to /", async () => {
    const fetchSpy = vi.fn(() => jsonResp(200, { access_token: "t", role: "user" }));
    vi.stubGlobal("fetch", fetchSpy);
    const user = userEvent.setup();
    renderAt("", "/login");
    await user.type(screen.getByLabelText(/用户名/), "alice");
    await user.type(screen.getByLabelText(/密码/), "secret1");
    await user.click(screen.getByRole("button", { name: /登录/ }));
    await waitFor(() => expect(useAuthStore.getState().token).toBe("t"));
    expect(useAuthStore.getState().role).toBe("user");
    await waitFor(() => expect(screen.getByTestId("location").textContent).toBe("/"));
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/auth/login",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ username: "alice", password: "secret1" }) })
    );
  });

  it("registers successfully and navigates to /", async () => {
    const fetchSpy = vi.fn(() => jsonResp(200, { access_token: "t2", role: "user" }));
    vi.stubGlobal("fetch", fetchSpy);
    const user = userEvent.setup();
    renderAt("", "/register");
    await user.type(screen.getByLabelText(/用户名/), "bob");
    await user.type(screen.getByLabelText(/密码/), "secret2");
    await user.click(screen.getByRole("button", { name: /注册/ }));
    await waitFor(() => expect(useAuthStore.getState().token).toBe("t2"));
    await waitFor(() => expect(screen.getByTestId("location").textContent).toBe("/"));
    expect(fetchSpy).toHaveBeenCalledWith("/api/auth/register", expect.anything());
  });

  it("shows error banner on 401", async () => {
    vi.stubGlobal("fetch", vi.fn(() => jsonResp(401, { error: "invalid credentials" })));
    const user = userEvent.setup();
    renderAt("", "/login");
    await user.type(screen.getByLabelText(/用户名/), "alice");
    await user.type(screen.getByLabelText(/密码/), "secret1");
    await user.click(screen.getByRole("button", { name: /登录/ }));
    await waitFor(() => expect(screen.getByTestId("auth-error")).toHaveTextContent("invalid credentials"));
  });

  it("links between login and register", async () => {
    const user = userEvent.setup();
    renderAt("", "/login");
    await user.click(screen.getByRole("link", { name: /注册/ }));
    await waitFor(() => expect(screen.getByTestId("page-register")).toBeInTheDocument());
  });
});
