import { AuthForm } from "../components/AuthForm";

export default function RegisterPage() {
  return (
    <div data-testid="page-register">
      <AuthForm mode="register" />
    </div>
  );
}
