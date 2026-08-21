import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "./context/AuthContext";
import { useAuth } from "./hooks/useAuth";
import { AuthPage } from "./pages/AuthPage";
import { Dashboard } from "./pages/Dashboard";

const queryClient = new QueryClient();

function AuthGate() {
  const { user, isLoading } = useAuth();

  if (isLoading) {
    return null; // avoid a login-page flash while GET /api/auth/me resolves
  }

  return user ? <Dashboard /> : <AuthPage />;
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <AuthGate />
      </AuthProvider>
    </QueryClientProvider>
  );
}

export default App;
