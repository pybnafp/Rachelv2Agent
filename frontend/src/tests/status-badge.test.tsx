import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusBadge } from "../components/StatusBadge";

const statuses = ["queued", "running", "succeeded", "partial", "failed", "cancelled"] as const;

describe("StatusBadge", () => {
  for (const s of statuses) {
    it(`renders ${s}`, () => {
      render(<StatusBadge status={s} />);
      expect(screen.getByTestId(`status-${s}`)).toBeTruthy();
      expect(screen.getByTestId(`status-${s}`).textContent).toContain(s);
    });
  }

  it("running dot pulses", () => {
    const { container } = render(<StatusBadge status="running" />);
    expect(container.querySelector(".animate-pulse")).toBeTruthy();
  });
});
