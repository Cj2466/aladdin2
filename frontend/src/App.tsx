import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "./context/AuthContext";
import { useAuth } from "./hooks/useAuth";
import { AuthPage } from "./pages/AuthPage";
import { Dashboard } from "./pages/Dashboard";
import { PrivacyPage } from "./pages/PrivacyPage";
import { ResetPasswordPage } from "./pages/ResetPasswordPage";
import { TermsPage } from "./pages/TermsPage";
import { VerifyEmailPage } from "./pages/VerifyEmailPage";

const queryClient = new QueryClient();

function AuthGate() {
  const { user, isLoading } = useAuth();

  if (isLoading) {
    return null; // avoid a login-page flash while GET /api/auth/me resolves
  }

  return user ? <Dashboard /> : <AuthPage />;
}

function DeepLinkGate() {
  // Emailed password-reset/verification links carry a token in the query
  // string. Seeded once from the URL at mount, not re-read on every
  // render, so `clear()` can actually transition away from the token view
  // afterward — reading window.location.search directly on every render
  // would never change once the URL itself doesn't.
  const [resetToken, setResetToken] = useState(
    () => new URLSearchParams(window.location.search).get("reset_token"),
  );
  const [verifyToken, setVerifyToken] = useState(
    () => new URLSearchParams(window.location.search).get("verify_token"),
  );
  // Legal pages are plain pathnames, not deep-link tokens, but live in the
  // same "no router" pattern — checked before the token branches so a
  // stray query param on /terms or /privacy can't shadow them.
  const [pathname, setPathname] = useState(() => window.location.pathname);

  function clear() {
    // Strip the query param so a page refresh doesn't try to reuse an
    // already-consumed, single-use token.
    window.history.replaceState({}, "", "/");
    setResetToken(null);
    setVerifyToken(null);
  }

  function goHome() {
    window.history.replaceState({}, "", "/");
    setPathname("/");
  }

  if (pathname === "/terms") return <TermsPage onBack={goHome} />;
  if (pathname === "/privacy") return <PrivacyPage onBack={goHome} />;
  if (resetToken) return <ResetPasswordPage token={resetToken} onDone={clear} />;
  if (verifyToken) return <VerifyEmailPage token={verifyToken} onDone={clear} />;
  return <AuthGate />;
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <DeepLinkGate />
      </AuthProvider>
    </QueryClientProvider>
  );
}

export default App;
