import type { ReactNode } from "react";

interface LegalPageProps {
  onBack: () => void;
}

export function TermsPage({ onBack }: LegalPageProps) {
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
            Terms of Service
          </h1>
          <p className="text-xs mt-2" style={{ color: "var(--text-muted)" }}>
            This is a template, written for a small project, not a substitute for professional
            legal review.
          </p>
        </div>

        <Section title="What this is">
          Aladdin2 is a personal portfolio risk analytics tool. It computes statistics (volatility,
          Value at Risk, correlation, factor exposure, and similar measures) from historical and
          live market data for portfolios you enter. It does not execute trades, hold assets, or
          manage money.
        </Section>

        <Section title="Not investment advice">
          Nothing in this app is investment, financial, legal, or tax advice. All analysis is for
          informational purposes only, is not guaranteed to be accurate or complete, and should
          not be the sole basis for any investment decision. Past performance and historical
          statistics do not predict future results.
        </Section>

        <Section title="Your account">
          You're responsible for keeping your password secure and for anything that happens under
          your account. You must provide a real email address you control — accounts require
          email verification before use.
        </Section>

        <Section title="Data sources">
          Market data comes from Yahoo Finance (via the unofficial{" "}
          <code>yfinance</code> library) and Finnhub. Alert emails, when configured, are sent via
          Resend. These are third-party services this app does not control; data from them may be
          delayed, incomplete, or occasionally incorrect.
        </Section>

        <Section title="No warranty">
          This app is provided "as is," without warranty of any kind. It's run as a personal
          project, not a commercial financial product, and comes with no uptime or accuracy
          guarantee.
        </Section>

        <Section title="Changes">
          These terms may change as the app changes. Continuing to use the app after a change
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
