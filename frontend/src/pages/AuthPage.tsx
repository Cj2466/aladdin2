import { useState } from "react";
import type { FormEvent } from "react";
import { isAxiosError } from "axios";
import { useAuth } from "../hooks/useAuth";
import type { ApiErrorBody } from "../api/client";

export function AuthPage() {
  const { login, register } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | undefined>();
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setErrorMessage(undefined);
    setIsSubmitting(true);
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await register(email, password);
      }
    } catch (error) {
      const detail = isAxiosError<ApiErrorBody>(error) ? error.response?.data?.detail : undefined;
      setErrorMessage(
        detail ?? (mode === "login" ? "Invalid email or password." : "Could not create account."),
      );
    } finally {
      setIsSubmitting(false);
    }
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
            {mode === "login" ? "Sign in to your account" : "Create an account"}
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
            style={{
              background: "var(--page-plane)",
              border: "1px solid var(--border)",
              color: "var(--text-primary)",
            }}
          />
        </label>

        <label className="flex flex-col gap-1 text-sm" style={{ color: "var(--text-secondary)" }}>
          Password
          <input
            type="password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="rounded-md px-3 py-2 text-sm"
            style={{
              background: "var(--page-plane)",
              border: "1px solid var(--border)",
              color: "var(--text-primary)",
            }}
          />
          {mode === "register" && (
            <span className="text-xs" style={{ color: "var(--text-muted)" }}>
              At least 8 characters.
            </span>
          )}
        </label>

        {errorMessage && (
          <div className="text-sm" style={{ color: "var(--status-critical)" }}>
            {errorMessage}
          </div>
        )}

        <button
          type="submit"
          disabled={isSubmitting}
          className="w-full rounded-md py-2 text-sm font-medium text-white disabled:opacity-50"
          style={{ background: "var(--accent-blue)" }}
        >
          {isSubmitting ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
        </button>

        <button
          type="button"
          onClick={() => {
            setMode(mode === "login" ? "register" : "login");
            setErrorMessage(undefined);
          }}
          className="w-full text-sm text-center"
          style={{ color: "var(--text-secondary)" }}
        >
          {mode === "login" ? "Need an account? Create one" : "Already have an account? Sign in"}
        </button>
      </form>
    </div>
  );
}
