import { useAuthStore } from "../stores/auth";
export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}
export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, ...rest } = init;
  const headers: Record<string, string> = { ...(rest.headers as any) };
  const token = useAuthStore.getState().token;
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (json !== undefined) headers["Content-Type"] = "application/json";
  const resp = await fetch(path, { ...rest, headers, body: json !== undefined ? JSON.stringify(json) : rest.body });
  if (resp.status === 401 && !path.startsWith("/api/auth/")) {
    useAuthStore.getState().logout();
    window.location.href = "/login";
    throw new ApiError(401, "unauthorized");
  }
  const body = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new ApiError(resp.status, (body as any).error ?? `HTTP ${resp.status}`);
  return body as T;
}
export const apiGet = <T>(path: string) => api<T>(path);
