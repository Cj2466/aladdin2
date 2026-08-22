import { useState } from "react";
import type { FormEvent } from "react";
import { isAxiosError } from "axios";
import { useAuth } from "../hooks/useAuth";
import { forgotPassword } from "../api/client";
import type { ApiErrorBody } from "../api/client";

type Mode = "login" | "register" | "forgot-password";

const inputStyle = {
  background: "var(--page-plane)",
  border: "1px solid var(--border)",
  color: "var(--text-primary)",
};

export function AuthPage() {
  const { login, register } = useAuth();
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | undefined>();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [registeredEmail, setRegisteredEmail] = useState<string | undefined>();
  const [forgotPasswordSent, setForgotPasswordSent] = useState(false);
  const [acceptedTerms, setAcceptedTerms] = useState(false);

  function switchMode(next: Mode) {
    setMode(next);
    setErrorMessage(undefined);
    setRegisteredEmail(undefined);
    setForgotPasswordSent(false);
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setErrorMessage(undefined);
    setIsSubmitting(true);
    try {
      if (mode === "login") {
        await login(email, password);
      } else if (mode === "register") {
        await register(email, password, acceptedTerms);
        setRegisteredEmail(email);
      } else {
        await forgotPassword(email);
        setForgotPasswordSent(true);
      }
    } catch (error) {
      const detail = isAxiosError<ApiErrorBody>(error) ? error.response?.data?.detail : undefined;
      setErrorMessage(
        detail ??
          (mode === "login"
            ? "Invalid email or password."
            : mode === "register"
              ? "Could not create account."
              : "Could not send reset email."),
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  if (registeredEmail) {
    return (
      <div className="min-h-screen flex items-center justify-center px-4">
        <div
          className="w-full max-w-sm rounded-lg p-6 space-y-4 text-center"
          style={{ background: "var(--surface-1)", border: "1px solid var(--border)" }}
        >
          <h1 className="text-xl font-semibold" style={{ color: "var(--text-primary)" }}>
            Aladdin2
          </h1>
          <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
            Check <span style={{ color: "var(--text-primary)" }}>{registeredEmail}</span> for a
            verification link before signing in.
          </p>
          <button
            type="button"
            onClick={() => switchMode("login")}
            className="w-full rounded-md py-2 text-sm"
            style={{ border: "1px solid var(--border)", color: "var(--text-secondary)" }}
          >
            Back to sign in
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm rounded-lg p-6 space-y-4"
        style={{ background: "var(--surface-1)", border: "1px solid var(--border)" }}
      >
        <div>
          <h1 className="text-xl font-semibold" style={{ color: "var(--text-primary)" }}>
            Aladdin2
          </h1>
          <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
            {mode === "login"
              ? "Sign in to your account"
              : mode === "register"
                ? "Create an account"
                : "Reset your password"}
          </p>
        </div>

        <label className="flex flex-col gap-1 text-sm" style={{ color: "var(--text-secondary)" }}>
          Email
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="rounded-md px-3 py-2 text-sm"
            style={inputStyle}
          />
        </label>

        {mode !== "forgot-password" && (
          <label
            className="flex flex-col gap-1 text-sm"
            style={{ color: "var(--text-secondary)" }}
          >
            Password
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="rounded-md px-3 py-2 text-sm"
              style={inputStyle}
            />
            {mode === "register" && (
              <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                At least 8 characters.
              </span>
            )}
          </label>
        )}

        {mode === "login" && (
          <button
            type="button"
            onClick={() => switchMode("forgot-password")}
            className="text-xs text-left"
            style={{ color: "var(--text-muted)" }}
          >
            Forgot password?
          </button>
        )}

        {mode === "register" && (
          <label
            className="flex items-start gap-2 text-xs"
            style={{ color: "var(--text-secondary)" }}
          >
            <input
              type="checkbox"
              checked={acceptedTerms}
              onChange={(e) => setAcceptedTerms(e.target.checked)}
              className="mt-0.5"
            />
            <span>
              I agree to the{" "}
              <a href="/terms" style={{ color: "var(--text-primary)" }}>
                Terms of Service
              </a>{" "}
              and{" "}
              <a href="/privacy" style={{ color: "var(--text-primary)" }}>
                Privacy Policy
              </a>
              .
            </span>
          </label>
        )}

        {forgotPasswordSent ? (
          <div className="text-sm" style={{ color: "var(--status-good)" }}>
            If that email is registered, check your inbox for a reset link.
          </div>
        ) : (
          errorMessage && (
            <div className="text-sm" style={{ color: "var(--status-critical)" }}>
              {errorMessage}
            </div>
          )
        )}

        <button
          type="submit"
          disabled={isSubmitting || forgotPasswordSent || (mode === "register" && !acceptedTerms)}
          className="w-full rounded-md py-2 text-sm font-medium text-white disabled:opacity-50"
          style={{ background: "var(--accent-blue)" }}
        >
          {isSubmitting
            ? "Please wait…"
            : mode === "login"
              ? "Sign in"
              : mode === "register"
                ? "Create account"
                : "Send reset link"}
        </button>

        <button
          type="button"
          onClick={() => switchMode(mode === "login" ? "register" : "login")}
          className="w-full text-sm text-center"
          style={{ color: "var(--text-secondary)" }}
        >
          {mode === "register"
            ? "Already have an account? Sign in"
            : mode === "forgot-password"
              ? "Back to sign in"
              : "Need an account? Create one"}
        </button>

        <div className="flex justify-center gap-3 text-xs" style={{ color: "var(--text-muted)" }}>
          <a href="/terms">Terms</a>
          <span>·</span>
          <a href="/privacy">Privacy</a>
        </div>
      </form>
    </div>
  );
}
