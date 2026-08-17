import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { useAuthStore } from "../stores/auth";
import { Button } from "./ui/Button";
import { Card } from "./ui/Card";
import { Input } from "./ui/Input";

interface AuthResp {
  access_token: string;
  role: string;
}

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const isLogin = mode === "login";
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const login = useAuthStore((s) => s.login);

  const valid = username.length >= 2 && password.length >= 6;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!valid || busy) return;
    setError(null);
    setBusy(true);
    try {
      const resp = await api<AuthResp>(`/api/auth/${mode}`, {
        method: "POST",
        json: { username, password },
      });
      login(resp.access_token, resp.role);
      navigate("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "网络错误，请稍后再试");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 p-4">
      <Card className="w-full max-w-sm" title={isLogin ? "登录" : "注册"}>
        {error && (
          <div
            data-testid="auth-error"
            className="mb-3 rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-600"
          >
            {error}
          </div>
        )}
        <form onSubmit={onSubmit} className="flex flex-col gap-3">
          <Input
            label="用户名"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
          />
          <Input
            label="密码"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={isLogin ? "current-password" : "new-password"}
          />
          <Button type="submit" disabled={!valid || busy}>
            {busy ? "提交中…" : isLogin ? "登录" : "注册"}
          </Button>
          {!valid && (
            <div data-testid="form-hint" className="text-xs text-slate-400">
              用户名至少 2 个字符，密码至少 6 个字符
            </div>
          )}
        </form>
        <div className="mt-4 text-center text-xs text-slate-500">
          {isLogin ? (
            <>没有账号？<Link className="text-sky-600 hover:underline" to="/register">注册</Link></>
          ) : (
            <>已有账号？<Link className="text-sky-600 hover:underline" to="/login">登录</Link></>
          )}
        </div>
      </Card>
    </div>
  );
}
