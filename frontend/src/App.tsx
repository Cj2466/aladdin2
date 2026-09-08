import { lazy, Suspense, useEffect, useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "./context/AuthContext";
import { useAuth } from "./hooks/useAuth";
import { AuthPage } from "./pages/AuthPage";
import { PrivacyPage } from "./pages/PrivacyPage";
import { ResetPasswordPage } from "./pages/ResetPasswordPage";
import { TermsPage } from "./pages/TermsPage";
import { VerifyEmailPage } from "./pages/VerifyEmailPage";

const queryClient = new QueryClient();

// Dashboard pulls in recharts and everything it depends on — split out of
// the main bundle so a first-time visitor (who has never logged in) only
// downloads it once they actually reach the authenticated app.
const Dashboard = lazy(() =>
  import("./pages/Dashboard").then((module) => ({ default: module.Dashboard })),
);
const ResearchLabPage = lazy(() =>
  import("./pages/ResearchLabPage").then((module) => ({ default: module.ResearchLabPage })),
);

type AuthenticatedView = "dashboard" | "research-lab";

// Shown while the initial /api/auth/me check is in flight. Delays its own
// visible text so a normal (fast) load never flashes anything — only a
// cold-starting backend, where the wait is long enough to need one, sees it.
function LoadingGate() {
  const [showHint, setShowHint] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setShowHint(true), 2500);
    return () => clearTimeout(timer);
  }, []);

  if (!showHint) return null;

  return (
    <div
      className="flex items-center justify-center min-h-screen text-sm"
      style={{ color: "var(--text-muted)" }}
    >
      Waking up the server — this can take up to a minute after a period of inactivity.
    </div>
  );
}

function AuthGate({ initialView = "dashboard" }: { initialView?: AuthenticatedView }) {
  const { user, isLoading } = useAuth();
  // Lightweight view toggle, not a router — mirrors how DeepLinkGate itself
  // switches between top-level components, just one level down so the
  // Research Lab gets its own URL/back button without a routing library.
  const [view, setView] = useState<AuthenticatedView>(initialView);

  if (isLoading) {
    // Rendering nothing here used to mean a genuinely blank/black screen for
    // the full duration of GET /api/auth/me — normally a instant, but the
    // Render free-tier backend hibernates after inactivity and a cold start
    // can take 30-60+ seconds (see functions/api/[[path]].js's own retry
    // logic for this exact case). A short delay before showing anything
    // avoids a flash on the common fast path, while a long cold start still
    // gets a real, reassuring status instead of looking hung or broken.
    return <LoadingGate />;
  }

  if (!user) {
    return <AuthPage />;
  }

  function openResearchLab() {
    window.history.replaceState({}, "", "/research-lab");
    setView("research-lab");
  }

  function backToDashboard() {
    window.history.replaceState({}, "", "/");
    setView("dashboard");
  }

  return (
    <Suspense fallback={null}>
      {view === "research-lab" ? (
        <ResearchLabPage onBack={backToDashboard} />
      ) : (
        <Dashboard onOpenResearchLab={openResearchLab} />
      )}
    </Suspense>
  );
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
  // Auth-gated, unlike the public legal pages above — an unauthenticated
  // visit still lands on AuthPage via AuthGate's own user check.
  if (pathname === "/research-lab") return <AuthGate initialView="research-lab" />;
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
