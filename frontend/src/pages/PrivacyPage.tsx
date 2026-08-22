import type { ReactNode } from "react";

interface LegalPageProps {
  onBack: () => void;
}

export function PrivacyPage({ onBack }: LegalPageProps) {
  return (
    <div className="min-h-screen px-4 py-10">
      <div
        className="max-w-2xl mx-auto rounded-lg p-6 sm:p-8 space-y-5"
        style={{ background: "var(--surface-1)", border: "1px solid var(--border)" }}
      >
        <div>
          <button
            type="button"
            onClick={onBack}
            className="text-sm mb-4"
            style={{ color: "var(--text-secondary)" }}
          >
            ← Back
          </button>
          <h1 className="text-2xl font-semibold" style={{ color: "var(--text-primary)" }}>
            Privacy Policy
          </h1>
          <p className="text-xs mt-2" style={{ color: "var(--text-muted)" }}>
            This is a template, written for a small project, not a substitute for professional
            legal review.
          </p>
        </div>

        <Section title="What's collected">
          Your email address and a hashed (not plaintext) password. Any portfolio names, tickers,
          and weights you enter, and any alert rules you create. That's the full extent of what
          this app stores about you.
        </Section>

        <Section title="What's not collected">
          No analytics or tracking cookies, no ad tracking, no third-party trackers embedded in
          the app. The only cookie this app sets is a session cookie needed to keep you signed in.
        </Section>

        <Section title="Third parties this app relies on">
          Market data: Yahoo Finance (via the unofficial <code>yfinance</code> library) and
          Finnhub — receives the ticker symbols you enter, not your identity. Email delivery
          (verification, password reset, alerts): Resend — receives your email address only when
          an email needs to be sent to you. Hosting: Render (backend), Cloudflare Pages (frontend),
          Neon (database) — all account and portfolio data is stored in Neon's Postgres database.
          None of these services are paid to use your data for anything beyond providing their
          service to this app.
        </Section>

        <Section title="How long data is kept">
          Your account and portfolio data is kept until you ask for it to be deleted. There's no
          self-service deletion yet — email the address you registered with to request it, and it
          will be removed manually.
        </Section>

        <Section title="Security">
          Passwords are hashed with Argon2id, never stored or logged in plaintext. Sessions use an
          httpOnly cookie that JavaScript can't read. Password-reset and email-verification links
          are single-use and expire quickly.
        </Section>

        <Section title="Changes">
          This policy may change as the app changes. Continuing to use the app after a change
          means you accept the update.
        </Section>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <h2 className="text-sm font-semibold mb-1.5" style={{ color: "var(--text-primary)" }}>
        {title}
      </h2>
      <p className="text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
        {children}
      </p>
    </div>
  );
}
