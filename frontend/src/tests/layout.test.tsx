import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Layout from "../components/Layout";
import { useAuthStore } from "../stores/auth";

function renderLayout() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <Layout>
        <div data-testid="page-child" />
      </Layout>
    </MemoryRouter>
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
});
