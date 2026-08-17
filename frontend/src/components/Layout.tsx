import { NavLink, useNavigate } from "react-router-dom";
import { useAuthStore } from "../stores/auth";
import { Badge } from "./ui/Badge";
import { Button } from "./ui/Button";

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  `text-sm hover:text-sky-600 ${isActive ? "text-sky-600 font-medium" : "text-slate-600"}`;

export default function Layout({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token);
  const role = useAuthStore((s) => s.role);
  const logout = useAuthStore((s) => s.logout);
  const navigate = useNavigate();

  return (
    <div>
      <header className="sticky top-0 z-10 bg-white border-b border-slate-200">
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
                登出
              </Button>
            )}
          </div>
        </div>
      </header>
      <main className="max-w-7xl mx-auto px-4 py-6">{children}</main>
    </div>
  );
}
