import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import App from "../App";
import { useAuthStore } from "../stores/auth";

beforeEach(() => {
  useAuthStore.setState({ token: null, role: null });
  window.history.pushState({}, "", "/");
});

describe("router auth guard", () => {
  it("redirects to login when token is null", () => {
    render(<App />);
    expect(screen.queryByTestId("page-submit")).not.toBeInTheDocument();
    expect(screen.getByTestId("page-login")).toBeInTheDocument();
  });

  it("shows submit page when token is set", () => {
    useAuthStore.setState({ token: "t" });
    render(<App />);
    expect(screen.getByTestId("page-submit")).toBeInTheDocument();
  });
});
