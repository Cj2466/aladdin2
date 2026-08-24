import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import {
  deleteForwardValidationRegistration,
  listForwardValidationRegistrations,
} from "../api/client";
import type { ForwardValidationRegistrationOut } from "../api/client";
import { formatPercent } from "../lib/format";

function formatSharpe(value: number | null): string {
  return value === null ? "N/A — not enough forward days yet" : value.toFixed(2);
}

function isMomentum(strategyName: string): boolean {
  return strategyName === "momentum_v1";
}

function positionLabel(position: ForwardValidationRegistrationOut["open_position"]): string {
  if (position === "flat") return "Flat";
  if (position === "long_spread" || position === "long") return position === "long" ? "Long" : "Long spread";
  return position === "short" ? "Short" : "Short spread";
}

function RegistrationRow({ reg }: { reg: ForwardValidationRegistrationOut }) {
  const queryClient = useQueryClient();
  const deleteMutation = useMutation({
    mutationFn: () => deleteForwardValidationRegistration(reg.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["forwardValidationRegistrations"] });
    },
  });

  const progressPct = Math.min(100, (reg.n_forward_trading_days / reg.min_trading_days_threshold) * 100);
  const isGraduated = reg.status === "forward_validated";

  return (
    <div
      className="rounded-lg p-4 space-y-2"
      style={{ background: "var(--surface-1)", border: "1px solid var(--border)" }}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-medium" style={{ color: "var(--text-primary)" }}>
          {isMomentum(reg.strategy_name) ? reg.ticker_a : `${reg.ticker_a} / ${reg.ticker_b}`}
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
          <span
            className="text-xs px-1.5 py-0.5 rounded"
            style={{
              background: "var(--page-plane)",
              border: `1px solid ${isGraduated ? "var(--status-good)" : "var(--border)"}`,
              color: isGraduated ? "var(--status-good)" : "var(--text-muted)",
            }}
          >
            {isGraduated ? "forward-validated ✓" : "in progress"}
          </span>
          {!reg.is_system && (
            <button
              type="button"
              onClick={() => deleteMutation.mutate()}
              disabled={deleteMutation.isPending}
              className="text-xs"
              style={{ color: "var(--text-muted)" }}
            >
              remove
            </button>
          )}
        </div>
      </div>

      <div>
        <div className="flex items-center justify-between text-xs mb-1" style={{ color: "var(--text-muted)" }}>
          <span>
            {reg.n_forward_trading_days} / {reg.min_trading_days_threshold} trading days
          </span>
          <span>
            {formatPercent(reg.pct_days_mean_reverting_forward ?? 0, 0)}{" "}
            {isMomentum(reg.strategy_name) ? "trending so far" : "mean-reverting so far"}
          </span>
        </div>
        <div
          className="h-1.5 rounded-full overflow-hidden"
          style={{ background: "var(--page-plane)" }}
        >
          <div
            style={{
              width: `${progressPct}%`,
              height: "100%",
              background: isGraduated ? "var(--status-good)" : "var(--accent-blue)",
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
          <div style={{ color: "var(--text-muted)" }}>Position</div>
          <div style={{ color: "var(--text-primary)", fontWeight: 500 }}>
            {positionLabel(reg.open_position)}
          </div>
        </div>
        <div>
          <div style={{ color: "var(--text-muted)" }}>Started</div>
          <div style={{ color: "var(--text-primary)", fontWeight: 500 }}>{reg.started_at}</div>
        </div>
      </div>
    </div>
  );
}

export function ForwardValidationPanel() {
  const { data, isLoading } = useQuery({
    queryKey: ["forwardValidationRegistrations"],
    queryFn: listForwardValidationRegistrations,
    refetchInterval: 5 * 60_000,
  });

  if (isLoading || !data || data.length === 0) {
    return null; // nothing tracked yet — no empty-state clutter on a page most users won't use immediately
  }

  return (
    <div className="space-y-3">
      <div className="text-sm font-medium" style={{ color: "var(--text-secondary)" }}>
        Forward-validated signals
      </div>
      <div
        className="rounded-md p-3 text-xs"
        style={{
          background: "var(--page-plane)",
          border: "1px solid var(--status-warning)",
          color: "var(--text-secondary)",
        }}
      >
        ⚠ Each tracked signal advances one real trading day at a time — it can't be rushed. The
        minimum trading-day threshold is a floor, not a guarantee of spanning multiple market
        regimes.
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {data.map((reg) => (
          <RegistrationRow key={reg.id} reg={reg} />
        ))}
      </div>
    </div>
  );
}
