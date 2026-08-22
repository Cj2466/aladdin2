import { useState } from "react";
import type { FormEvent } from "react";
import { isAxiosError } from "axios";
import { resetPassword } from "../api/client";
import type { ApiErrorBody } from "../api/client";

interface ResetPasswordPageProps {
  token: string;
  onDone: () => void;
}

export function ResetPasswordPage({ token, onDone }: ResetPasswordPageProps) {
  const [newPassword, setNewPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | undefined>();
  const [succeeded, setSucceeded] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setErrorMessage(undefined);
    setIsSubmitting(true);
    try {
      await resetPassword(token, newPassword);
      setSucceeded(true);
    } catch (error) {
      const detail = isAxiosError<ApiErrorBody>(error) ? error.response?.data?.detail : undefined;
      setErrorMessage(detail ?? "This reset link is invalid or has expired.");
    } finally {
      setIsSubmitting(false);
    }
  }

  const inputStyle = {
    background: "var(--page-plane)",
    border: "1px solid var(--border)",
    color: "var(--text-primary)",
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div
        className="w-full max-w-sm rounded-lg p-6 space-y-4"
        style={{ background: "var(--surface-1)", border: "1px solid var(--border)" }}
      >
        <div>
          <h1 className="text-xl font-semibold" style={{ color: "var(--text-primary)" }}>
            Aladdin2
          </h1>
          <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
            Set a new password
          </p>
        </div>

        {succeeded ? (
          <>
            <p className="text-sm" style={{ color: "var(--status-good)" }}>
              Password updated. You've been signed out everywhere — sign in again with your new
              password.
            </p>
            <button
              type="button"
              onClick={onDone}
              className="w-full rounded-md py-2 text-sm font-medium text-white"
              style={{ background: "var(--accent-blue)" }}
            >
              Go to sign in
            </button>
          </>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <label
              className="flex flex-col gap-1 text-sm"
              style={{ color: "var(--text-secondary)" }}
            >
              New password
              <input
                type="password"
                required
                minLength={8}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="rounded-md px-3 py-2 text-sm"
                style={inputStyle}
              />
              <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                At least 8 characters.
              </span>
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
              {isSubmitting ? "Please wait…" : "Reset password"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
