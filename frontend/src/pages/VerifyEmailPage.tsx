import { useEffect, useRef, useState } from "react";
import { isAxiosError } from "axios";
import { useAuth } from "../hooks/useAuth";
import type { ApiErrorBody } from "../api/client";

interface VerifyEmailPageProps {
  token: string;
  onDone: () => void;
}

export function VerifyEmailPage({ token, onDone }: VerifyEmailPageProps) {
  const { verifyEmail } = useAuth();
  const [status, setStatus] = useState<"pending" | "success" | "error">("pending");
  const [errorMessage, setErrorMessage] = useState<string | undefined>();
  const attempted = useRef(false);

  useEffect(() => {
    if (attempted.current) return; // StrictMode double-invokes effects; a token is single-use
    attempted.current = true;

    verifyEmail(token)
      .then(() => setStatus("success"))
      .catch((error: unknown) => {
        const detail = isAxiosError<ApiErrorBody>(error) ? error.response?.data?.detail : undefined;
        setErrorMessage(detail ?? "Could not verify this email link.");
        setStatus("error");
      });
  }, [token, verifyEmail]);

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div
        className="w-full max-w-sm rounded-lg p-6 space-y-4 text-center"
        style={{ background: "var(--surface-1)", border: "1px solid var(--border)" }}
      >
        <h1 className="text-xl font-semibold" style={{ color: "var(--text-primary)" }}>
          Aladdin2
        </h1>

        {status === "pending" && (
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            Verifying your email…
          </p>
        )}

        {status === "success" && (
          <>
            <p className="text-sm" style={{ color: "var(--status-good)" }}>
              Email verified — you're signed in.
            </p>
            <button
              type="button"
              onClick={onDone}
              className="w-full rounded-md py-2 text-sm font-medium text-white"
              style={{ background: "var(--accent-blue)" }}
            >
              Continue
            </button>
          </>
        )}

        {status === "error" && (
          <>
            <p className="text-sm" style={{ color: "var(--status-critical)" }}>
              {errorMessage}
            </p>
            <button
              type="button"
              onClick={onDone}
              className="w-full rounded-md py-2 text-sm"
              style={{ border: "1px solid var(--border)", color: "var(--text-secondary)" }}
            >
              Back to sign in
            </button>
          </>
        )}
      </div>
    </div>
  );
}
