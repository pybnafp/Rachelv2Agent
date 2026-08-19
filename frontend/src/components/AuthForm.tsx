import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { useAuthStore } from "../stores/auth";
import { Button } from "./ui/Button";
import { Card } from "./ui/Card";
import { Input } from "./ui/Input";
import { VerifyBlock } from "./VerifyBlock";

interface AuthResp {
  access_token: string;
  role: string;
}

export function LoginForm() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [verifyEmail, setVerifyEmail] = useState<string | null>(null);
  const navigate = useNavigate();
  const login = useAuthStore((s) => s.login);

  const valid = email.includes("@") && password.length >= 6;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!valid || busy) return;
    setError(null);
    setBusy(true);
    try {
      const resp = await api<AuthResp>("/api/auth/login", { method: "POST", json: { email, password } });
      login(resp.access_token, resp.role);
      navigate("/");
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setVerifyEmail(email); // 邮箱未验证：切换为内联验证
      } else {
        setError(err instanceof ApiError ? err.message : "网络错误，请稍后再试");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="登录">
      {error && (
        <div data-testid="auth-error" className="mb-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
          {error}
        </div>
      )}
      {verifyEmail !== null ? (
        <VerifyBlock email={verifyEmail} initialCooldown={0} />
      ) : (
        <form onSubmit={onSubmit} className="flex flex-col gap-3">
          <Input label="邮箱" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" />
          <Input
            label="密码"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
          <Button type="submit" disabled={!valid || busy}>
            {busy ? "提交中…" : "登录"}
          </Button>
          {!valid && (
            <div data-testid="form-hint" className="text-xs text-slate-400">
              请输入邮箱和至少 6 位的密码
            </div>
          )}
        </form>
      )}
      {verifyEmail === null && (
        <div className="mt-4 text-center text-xs text-slate-500">
          没有账号？<Link className="text-sky-600 hover:underline" to="/register">注册</Link>
        </div>
      )}
    </Card>
  );
}

export function RegisterForm() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState<1 | 2>(1);
  const [sentEmail, setSentEmail] = useState("");

  const valid = email.includes("@") && password.length >= 6 && confirm === password;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!valid || busy) return;
    setError(null);
    setBusy(true);
    try {
      await api("/api/auth/register", { method: "POST", json: { email, password } });
      advance();
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) {
        setError("发送过于频繁，请稍后再试");
        advance(); // 冷却中：视为已发送，进入第 2 步（重发倒计时同样生效）
      } else if (err instanceof ApiError && err.status === 409) {
        setError("邮箱已注册，请直接登录");
      } else {
        setError(err instanceof ApiError ? err.message : "网络错误，请稍后再试");
      }
    } finally {
      setBusy(false);
    }
  }

  function advance() {
    setSentEmail(email);
    setStep(2);
  }

  return (
    <Card title="注册">
      {error && (
        <div data-testid="auth-error" className="mb-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
          {error}
        </div>
      )}
      {step === 2 ? (
        <VerifyBlock email={sentEmail} />
      ) : (
        <form onSubmit={onSubmit} className="flex flex-col gap-3">
          <Input label="邮箱" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" />
          <Input
            label="密码"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
          />
          <Input
            label="确认密码"
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            autoComplete="new-password"
          />
          <Button type="submit" disabled={!valid || busy}>
            {busy ? "提交中…" : "注册"}
          </Button>
          {!valid && (
            <div data-testid="form-hint" className="text-xs text-slate-400">
              请输入邮箱、至少 6 位的密码，且两次输入一致
            </div>
          )}
        </form>
      )}
      {step === 1 && (
        <div className="mt-4 text-center text-xs text-slate-500">
          已有账号？<Link className="text-sky-600 hover:underline" to="/login">登录</Link>
        </div>
      )}
    </Card>
  );
}
