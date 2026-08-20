import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { useAuthStore } from "../stores/auth";
import { Button } from "./ui/Button";

export function ChangePasswordModal({ onClose }: { onClose: () => void }) {
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const logout = useAuthStore((s) => s.logout);
  const navigate = useNavigate();

  const valid = oldPassword.length > 0 && newPassword.length >= 6 && confirm === newPassword;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!valid || busy) return;
    setError(null);
    setBusy(true);
    try {
      await api("/api/auth/change-password", {
        method: "POST",
        json: { old_password: oldPassword, new_password: newPassword },
      });
      logout();
      navigate("/login?changed=1");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "网络错误，请稍后再试");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div
        className="w-full max-w-sm rounded-2xl bg-surface p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="mb-4 text-base font-semibold text-slate-800">修改密码</h2>
        {error && (
          <div data-testid="cpw-error" className="mb-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
            {error}
          </div>
        )}
        <form onSubmit={onSubmit} className="flex flex-col gap-3">
          <label className="flex flex-col gap-1 text-sm text-slate-600">
            旧密码
            <input
              type="password"
              value={oldPassword}
              onChange={(e) => setOldPassword(e.target.value)}
              autoComplete="current-password"
              className="rounded-md border border-slate-300 px-3 py-1.5"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm text-slate-600">
            新密码
            <input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              autoComplete="new-password"
              className="rounded-md border border-slate-300 px-3 py-1.5"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm text-slate-600">
            确认新密码
            <input
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              autoComplete="new-password"
              className="rounded-md border border-slate-300 px-3 py-1.5"
            />
          </label>
          <Button type="submit" disabled={!valid || busy}>
            {busy ? "提交中…" : "确认修改"}
          </Button>
          {!valid && (
            <div data-testid="cpw-hint" className="text-xs text-slate-400">
              新密码至少 6 位，且两次输入需一致
            </div>
          )}
        </form>
      </div>
    </div>
  );
}
