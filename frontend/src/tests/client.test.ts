import { describe, it, expect, vi, beforeEach } from "vitest";
import { api, ApiError } from "../api/client";
import { useAuthStore } from "../stores/auth";

const ok = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

beforeEach(() => {
  useAuthStore.setState({ token: null, role: null });
});

describe("api client", () => {
  it("no token: no Authorization header", async () => {
    const fetchMock = vi.fn().mockResolvedValue(ok({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);
    const data = await api<{ ok: boolean }>("/api/jobs");
    expect(data.ok).toBe(true);
    const headers = fetchMock.mock.calls[0][1].headers as Record<string, string>;
    expect(headers["Authorization"]).toBeUndefined();
  });

  it("with token: sends Bearer header", async () => {
    useAuthStore.setState({ token: "tok123" });
    const fetchMock = vi.fn().mockResolvedValue(ok({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);
    await api("/api/jobs");
    const headers = fetchMock.mock.calls[0][1].headers as Record<string, string>;
    expect(headers["Authorization"]).toBe("Bearer tok123");
  });

  it("non-2xx with body error: throws ApiError with body message", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation(async () => ok({ error: "x" }, 422)));
    await expect(api("/api/jobs")).rejects.toThrow(ApiError);
    await expect(api("/api/jobs")).rejects.toThrow("x");
  });

  it("401 on non-auth path: logs out and throws", async () => {
    useAuthStore.setState({ token: "tok123" });
    vi.stubGlobal("window", Object.assign(window, { location: { href: "" } }));
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(ok({ error: "unauthorized" }, 401)));
    await expect(api("/api/jobs")).rejects.toThrow("unauthorized");
    expect(useAuthStore.getState().token).toBeNull();
  });
});
