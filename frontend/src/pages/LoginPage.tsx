import { AuthForm } from "../components/AuthForm";

export default function LoginPage() {
  return (
    <div data-testid="page-login">
      <AuthForm mode="login" />
    </div>
  );
}
