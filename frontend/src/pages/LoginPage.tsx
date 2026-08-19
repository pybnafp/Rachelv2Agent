import { useSearchParams } from "react-router-dom";
import { LoginForm } from "../components/AuthForm";

export default function LoginPage() {
  const [searchParams] = useSearchParams();
  const changed = searchParams.get("changed") === "1";
  return (
    <div data-testid="page-login">
      {changed && (
        <div
          data-testid="changed-banner"
          className="fixed inset-x-0 top-0 z-50 border border-green-200 bg-green-50 px-4 py-2 text-center text-sm text-green-700"
        >
          密码已修改，请用新密码重新登录
        </div>
      )}
      <div className="flex min-h-screen items-center justify-center bg-slate-50 p-4">
        <div className="w-full max-w-sm">
          <LoginForm />
        </div>
      </div>
    </div>
  );
}
