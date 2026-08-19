import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { useAuthStore } from "../stores/auth";
import { Button } from "./ui/Button";
import { Input } from "./ui/Input";

interface AuthResp {
  access_token: string;
  role: string;
}

/**
 * 验证码输入块：注册第 2 步与登录 403 内联验证共用。
 * verify 成功 → 存 token 并跳转 "/"。
 */
export function VerifyBlock({ email, initialCooldown = 60 }: { email: string; initialCooldown?: number }) {
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [countdown, setCountdown] = useState(initialCooldown);
  const navigate = useNavigate();
  const login = useAuthStore((s) => s.login);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (countdown <= 0) return;
    timer.current = setInterval(() => setCountdown((c) => Math.max(0, c - 1)), 1000);
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [countdown > 0]); // eslint-disable-line react-hooks/exhaustive-deps

  async function onVerify(e: FormEvent) {
    e.preventDefault();
    if (code.length !== 6 || busy) return;
    setError(null);
    setBusy(true);
    try {
      const resp = await api<AuthResp>("/api/auth/verify", { method: "POST", json: { email, code } });
      login(resp.access_token, resp.role);
      navigate("/");
    } catch (err) {
      setError(err instanceof ApiError && err.status === 400 ? "验证码错误或已过期" : "网络错误，请稍后再试");
    } finally {
      setBusy(false);
    }
  }

  async function onResend() {
    if (countdown > 0) return;
    setError(null);
    try {
      await api("/api/auth/resend", { method: "POST", json: { email } });
      setCountdown(60);
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) {
        setCountdown(60); // 冷却期内：重置倒计时
      } else {
        setError(err instanceof ApiError ? err.message : "网络错误，请稍后再试");
      }
    }
  }

  return (
    <div data-testid="verify-step" className="flex flex-col gap-3">
      <div className="text-sm text-slate-500">验证码已发送至 {email}</div>
      {error && (
        <div data-testid="auth-error" className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
          {error}
        </div>
      )}
      <form onSubmit={onVerify} className="flex flex-col gap-3">
        <Input
          label="验证码"
          value={code}
          inputMode="numeric"
          maxLength={6}
          placeholder="6 位数字验证码"
          onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
        />
        <Button type="submit" disabled={code.length !== 6 || busy}>
          {busy ? "提交中…" : "提交"}
        </Button>
      </form>
      <button
        data-testid="resend-btn"
        type="button"
        disabled={countdown > 0}
        onClick={() => void onResend()}
        className="text-xs text-sky-600 hover:underline disabled:text-slate-400 disabled:no-underline"
      >
        {countdown > 0 ? `重发验证码（${countdown}s）` : "重发验证码"}
      </button>
    </div>
  );
}
