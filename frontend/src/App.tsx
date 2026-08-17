import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { useAuthStore } from "./stores/auth";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
const qc = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } } });
function Guard({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token);
  return token ? <>{children}</> : <Navigate to="/login" replace />;
}
export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/" element={<Guard><div data-testid="page-submit">submit</div></Guard>} />
          <Route path="/jobs" element={<Guard><div data-testid="page-jobs">jobs</div></Guard>} />
          <Route path="/jobs/:id" element={<Guard><div data-testid="page-job-detail">detail</div></Guard>} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
