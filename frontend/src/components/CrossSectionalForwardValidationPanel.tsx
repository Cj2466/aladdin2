import { useQuery } from "@tanstack/react-query";
import {
  listCrossSectionalForwardValidationRegistrations,
} from "../api/client";
import type { CrossSectionalForwardValidationRegistrationOut } from "../api/client";
import { formatPercent } from "../lib/format";
import { UnderperformanceAdvisoryBadge } from "./UnderperformanceAdvisoryBadge";

// Read-only dashboard for the cross-sectional family registrations
// (quality, short-interest, lazy-prices, crypto BAB, ...) — a SEPARATE
// table from ForwardValidationPanel's pairs/momentum registrations, with
// its own daily background runner. No register/delete controls here:
// changing a family's operational status is a CLAUDE.md rule-6 decision
// that needs the project owner's explicit sign-off, not a dashboard action.

function formatSharpe(value: number | null): string {
  return value === null ? "N/A — not enough forward days yet" : value.toFixed(2);
}

const STATUS_LABEL: Record<CrossSectionalForwardValidationRegistrationOut["status"], string> = {
  in_progress: "in progress",
  forward_validated: "forward-validated ✓",
  underperforming: "underperforming",
  spec_drift: "spec drift",
  retired: "retired",
};

function statusColor(status: CrossSectionalForwardValidationRegistrationOut["status"]): string {
  if (status === "forward_validated") return "var(--status-good)";
  if (status === "underperforming" || status === "spec_drift") return "var(--status-warning)";
  return "var(--border)"; // in_progress / retired — neutral, not alarming
}

function RegistrationRow({ reg }: { reg: CrossSectionalForwardValidationRegistrationOut }) {
  const progressPct = Math.min(100, (reg.n_forward_trading_days / reg.min_trading_days_threshold) * 100);
  const borderColor = statusColor(reg.status);

  return (
    <div
      className="rounded-lg p-4 space-y-2"
      style={{ background: "var(--surface-1)", border: "1px solid var(--border)" }}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-medium" style={{ color: "var(--text-primary)" }}>
          {reg.family_key}
          {reg.is_system && (
            <span
              className="text-xs px-1.5 py-0.5 rounded"
              style={{ background: "var(--page-plane)", border: "1px solid var(--border)", color: "var(--text-muted)" }}
            >
              Automatic daily run
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
        <UnderperformanceAdvisoryBadge advisory={reg.underperformance_advisory} />
        <span
          className="text-xs px-1.5 py-0.5 rounded"
          style={{
            background: "var(--page-plane)",
            border: `1px solid ${borderColor}`,
            color: borderColor === "var(--border)" ? "var(--text-muted)" : borderColor,
          }}
        >
          {STATUS_LABEL[reg.status]}
        </span>
        </div>
      </div>

      <div className="text-xs" style={{ color: "var(--text-muted)" }}>
        {reg.pattern_id}
      </div>

      <div>
        <div className="flex items-center justify-between text-xs mb-1" style={{ color: "var(--text-muted)" }}>
          <span>
            {reg.n_forward_trading_days} / {reg.min_trading_days_threshold} trading days
          </span>
          <span>{reg.n_long}L / {reg.n_short}S</span>
        </div>
        <div className="h-1.5 rounded-full overflow-hidden" style={{ background: "var(--page-plane)" }}>
          <div
            style={{
              width: `${progressPct}%`,
              height: "100%",
              background: reg.status === "forward_validated" ? "var(--status-good)" : "var(--accent-blue)",
            }}
          />
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3 text-xs">
        <div>
          <div style={{ color: "var(--text-muted)" }}>Sharpe (forward)</div>
          <div style={{ color: "var(--text-primary)", fontWeight: 500 }}>
            {formatSharpe(reg.sharpe_forward_so_far)}
          </div>
        </div>
        <div>
          <div style={{ color: "var(--text-muted)" }}>Equity</div>
          <div style={{ color: "var(--text-primary)", fontWeight: 500 }}>
            {formatPercent(reg.equity - 1, 1)}
          </div>
        </div>
        <div>
          <div style={{ color: "var(--text-muted)" }}>Started</div>
          <div style={{ color: "var(--text-primary)", fontWeight: 500 }}>{reg.started_at.slice(0, 10)}</div>
        </div>
      </div>
    </div>
  );
}

export function CrossSectionalForwardValidationPanel() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["crossSectionalForwardValidationRegistrations"],
    queryFn: listCrossSectionalForwardValidationRegistrations,
    refetchInterval: 5 * 60_000,
  });

  if (isLoading) {
    return null; // avoid a flash of empty-state before the first fetch resolves
  }

  if (isError) {
    return (
      <div
        className="rounded-md p-3 text-sm"
        style={{ background: "var(--page-plane)", border: "1px solid var(--status-warning)", color: "var(--text-secondary)" }}
      >
        Could not load cross-sectional forward-validation status. The backend may still be
        waking up from inactivity (this can take up to a minute on the free tier) — try
        refreshing shortly.
      </div>
    );
  }

  if (!data || data.length === 0) {
    return null; // nothing registered yet — no empty-state clutter
  }

  return (
    <div className="space-y-3">
      <div className="text-sm font-medium" style={{ color: "var(--text-secondary)" }}>
        Cross-sectional forward-validated families
      </div>
      <div
        className="rounded-md p-3 text-xs"
        style={{
          background: "var(--page-plane)",
          border: "1px solid var(--status-warning)",
          color: "var(--text-secondary)",
        }}
      >
        ⚠ Each family advances one real trading day at a time — it can't be rushed. "retired" and
        "spec drift" rows are historical/parked, not active recommendations.
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {data.map((reg) => (
          <RegistrationRow key={reg.id} reg={reg} />
        ))}
      </div>
    </div>
  );
}
