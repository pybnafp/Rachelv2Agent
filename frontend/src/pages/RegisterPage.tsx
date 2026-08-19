import { RegisterForm } from "../components/AuthForm";

export default function RegisterPage() {
  return (
    <div data-testid="page-register">
      <div className="flex min-h-screen items-center justify-center bg-slate-50 p-4">
        <div className="w-full max-w-sm">
          <RegisterForm />
        </div>
      </div>
    </div>
  );
}
