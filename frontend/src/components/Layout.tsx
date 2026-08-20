import { useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { ChevronDown, KeyRound, LogOut } from "lucide-react";
import { useAuthStore } from "../stores/auth";
import { useMe } from "../api/hooks";
import { Badge } from "./ui/Badge";
import { Button } from "./ui/Button";
import { ChangePasswordModal } from "./ChangePasswordModal";

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  `text-sm hover:text-sky-600 ${isActive ? "text-sky-600 font-medium" : "text-slate-600"}`;

export default function Layout({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token);
  const role = useAuthStore((s) => s.role);
  const logout = useAuthStore((s) => s.logout);
  const navigate = useNavigate();
  const { data: me } = useMe(!!token);
  const [menuOpen, setMenuOpen] = useState(false);
  const [changePwOpen, setChangePwOpen] = useState(false);

  return (
    <div>
      <header className="sticky top-0 z-10 bg-surface border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 h-14 flex items-center gap-6">
          <span className="font-semibold text-sky-600">Rachel-v2 Platform</span>
          <nav className="flex items-center gap-4">
            <NavLink to="/" end className={navLinkClass}>
              提交
            </NavLink>
            <NavLink to="/jobs" className={navLinkClass}>
              任务
            </NavLink>
            {role === "admin" && (
              <NavLink to="/admin/llm" className={navLinkClass}>
                供应商
              </NavLink>
            )}
          </nav>
          <div className="ml-auto flex items-center gap-3">
            {token !== null && me && (
              <div className="relative">
                {menuOpen && (
                  <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} />
                )}
                <button
                  data-testid="account-menu-trigger"
                  className="flex items-center gap-1 text-sm font-medium text-slate-700 hover:text-sky-600"
                  onClick={() => setMenuOpen((v) => !v)}
                >
                  <span data-testid="account-name">{me.email}</span>
                  <ChevronDown size={13} aria-hidden />
                </button>
                {menuOpen && (
                  <div
                    data-testid="account-menu"
                    className="absolute right-0 z-20 mt-1 w-32 rounded-md border border-slate-200 bg-surface py-1 shadow-lg"
                  >
                    <button
                      className="block w-full px-3 py-1.5 text-left text-sm text-slate-700 hover:bg-slate-50"
                      onClick={() => {
                        setMenuOpen(false);
                        setChangePwOpen(true);
                      }}
                    >
                      <span className="inline-flex items-center gap-1.5">
                        <KeyRound size={13} aria-hidden />
                        修改密码
                      </span>
                    </button>
                  </div>
                )}
              </div>
            )}
            {role === "admin" && <Badge color="sky">admin</Badge>}
            {token === null ? (
              <div className="flex items-center gap-3 text-sm">
                <NavLink to="/login" className="text-slate-600 hover:text-sky-600">
                  登录
                </NavLink>
                <NavLink to="/register" className="text-slate-600 hover:text-sky-600">
                  注册
                </NavLink>
              </div>
            ) : (
              <Button
                variant="ghost"
                size="sm"
                className="text-red-500 hover:bg-red-50"
                onClick={() => {
                  logout();
                  navigate("/login");
                }}
              >
                <span className="inline-flex items-center gap-1">
                  <LogOut size={13} aria-hidden />
                  登出
                </span>
              </Button>
            )}
          </div>
        </div>
      </header>
      <main className="max-w-7xl mx-auto px-4 py-6">{children}</main>
      {changePwOpen && <ChangePasswordModal onClose={() => setChangePwOpen(false)} />}
    </div>
  );
}
