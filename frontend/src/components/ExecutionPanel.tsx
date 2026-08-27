import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { isAxiosError } from "axios";
import {
  RESUME_CONFIRMATION,
  getExecutionStatus,
  haltExecution,
  listLiveOrders,
  listLivePositions,
  resumeExecution,
  resumeExecutionStrategy,
} from "../api/client";
import type {
  ApiErrorBody,
  ExecutionStatusOut,
  SlippageAggregateOut,
  StrategyExecutionStateOut,
} from "../api/client";

// A monitoring and control surface, not a feature page: no charts, no new
// visual system. The one thing it must do well is make the current state
// unmissable at a glance.

const REFRESH_MS = 15_000;

const inputStyle = {
  background: "var(--page-plane)",
  border: "1px solid var(--border)",
  color: "var(--text-primary)",
};

function errorMessage(error: unknown, fallback: string): string {
  if (isAxiosError<ApiErrorBody>(error)) return error.response?.data?.detail ?? fallback;
  return fallback;
}

function money(value: number): string {
  return value.toLocaleString(undefined, { style: "currency", currency: "USD" });
}

function pct(value: number): string {
  return `${(value * 100).toFixed(2)}%`;
}

function bps(value: number | null): string {
  return value === null ? "—" : `${value.toFixed(1)} bps`;
}

function timestamp(value: string | null): string {
  return value ? new Date(value).toLocaleString() : "—";
}

function StatusBanner({ status }: { status: ExecutionStatusOut }) {
  const { control } = status;
  const breached = control.daily_loss_breach_at !== null && control.resume_blocked_until_next_trading_day;

  // Three visually distinct states, because they call for three different
  // human responses: a loss-breach halt is not the same event as someone
  // clicking Halt, and neither is the same as trading actually being live.
  const { background, border, title, detail } = breached
    ? {
        background: "rgba(220, 38, 38, 0.16)",
        border: "1px solid rgba(220, 38, 38, 0.6)",
        title: "HALTED — daily-loss circuit breaker fired",
        detail:
          `Account P&L reached ${control.daily_loss_breach_pct !== null ? pct(control.daily_loss_breach_pct) : "the limit"}. ` +
          "Open orders were cancelled; existing positions were deliberately NOT liquidated. " +
          "Trading cannot be resumed until the next trading day.",
      }
    : control.trading_halted
      ? {
          background: "rgba(217, 119, 6, 0.16)",
          border: "1px solid rgba(217, 119, 6, 0.6)",
          title: "HALTED — no orders will be submitted",
          detail: control.halted_reason ?? "Trading is halted.",
        }
      : {
          background: "rgba(22, 163, 74, 0.14)",
          border: "1px solid rgba(22, 163, 74, 0.55)",
          title: `LIVE — ${status.settings.paper_trading ? "paper trading" : "REAL MONEY"}`,
          detail: `Checking every ${status.settings.check_interval_seconds}s against ${status.settings.broker_base_url}.`,
        };

  return (
    <div className="rounded p-4" style={{ background, border }}>
      <div className="font-semibold" style={{ color: "var(--text-primary)" }}>
        {title}
      </div>
      <div className="text-sm mt-1" style={{ color: "var(--text-secondary)" }}>
        {detail}
      </div>
      <div className="text-xs mt-2" style={{ color: "var(--text-muted)" }}>
        Last runner tick: {timestamp(control.last_tick_at)}
        {control.last_tick_status ? ` (${control.last_tick_status})` : ""}
      </div>
    </div>
  );
}

function Controls({ status }: { status: ExecutionStatusOut }) {
  const queryClient = useQueryClient();
  const [confirmation, setConfirmation] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  function invalidate() {
    void queryClient.invalidateQueries({ queryKey: ["execution"] });
  }

  const halt = useMutation({
    mutationFn: () => haltExecution(reason.trim() || "manual"),
    onSuccess: () => {
      setError(null);
      invalidate();
    },
    onError: (e) => setError(errorMessage(e, "Failed to halt trading.")),
  });

  const resume = useMutation({
    mutationFn: () => resumeExecution(confirmation),
    onSuccess: () => {
      setError(null);
      setConfirmation("");
      invalidate();
    },
    onError: (e) => setError(errorMessage(e, "Failed to resume trading.")),
  });

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="text"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Reason (optional)"
          className="rounded px-2 py-1 text-sm"
          style={inputStyle}
        />
        {/* No confirmation on halt, deliberately: the safe direction should
            never have friction, and it stays enabled even when already
            halted so it is always available in a hurry. */}
        <button
          type="button"
          onClick={() => halt.mutate()}
          disabled={halt.isPending}
          className="rounded px-3 py-1 text-sm font-semibold"
          style={{ background: "rgba(220, 38, 38, 0.85)", color: "white" }}
        >
          {halt.isPending ? "Halting…" : "Halt trading"}
        </button>
      </div>

      {status.control.trading_halted ? (
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="text"
            value={confirmation}
            onChange={(e) => setConfirmation(e.target.value)}
            placeholder={RESUME_CONFIRMATION}
            className="rounded px-2 py-1 text-sm font-mono"
            style={inputStyle}
          />
          <button
            type="button"
            onClick={() => resume.mutate()}
            disabled={
              resume.isPending ||
              confirmation !== RESUME_CONFIRMATION ||
              status.control.resume_blocked_until_next_trading_day
            }
            className="rounded px-3 py-1 text-sm"
            style={{ background: "var(--page-plane)", border: "1px solid var(--border)", color: "var(--text-primary)" }}
          >
            {resume.isPending ? "Resuming…" : "Resume trading"}
          </button>
          <span className="text-xs" style={{ color: "var(--text-muted)" }}>
            {status.control.resume_blocked_until_next_trading_day
              ? "Blocked until the next trading day — the breaker fired today."
              : `Type ${RESUME_CONFIRMATION} exactly to enable.`}
          </span>
        </div>
      ) : null}

      {error ? (
        <div className="text-sm" style={{ color: "var(--danger, #dc2626)" }}>
          {error}
        </div>
      ) : null}
    </div>
  );
}

function LimitsRow({ status }: { status: ExecutionStatusOut }) {
  const { settings, account } = status;
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
      <Stat label="Equity" value={account ? money(account.equity) : "—"} />
      <Stat
        label="P&L today"
        value={account ? pct(account.daily_pnl_pct) : "—"}
        hint={`limit ${pct(-settings.daily_loss_limit_pct)}`}
      />
      <Stat
        label="Capital fraction"
        value={pct(settings.capital_fraction)}
        hint="of account equity this system may deploy"
      />
      <Stat
        label="Caps"
        value={`${money(settings.max_position_notional)} / ${money(settings.max_total_notional)}`}
        hint="per ticker / total gross"
      />
    </div>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded p-2" style={{ background: "var(--page-plane)", border: "1px solid var(--border)" }}>
      <div className="text-xs" style={{ color: "var(--text-muted)" }}>
        {label}
      </div>
      <div className="font-medium" style={{ color: "var(--text-primary)" }}>
        {value}
      </div>
      {hint ? (
        <div className="text-xs" style={{ color: "var(--text-muted)" }}>
          {hint}
        </div>
      ) : null}
    </div>
  );
}

function StrategyRow({ strategy }: { strategy: StrategyExecutionStateOut }) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const resume = useMutation({
    mutationFn: () => resumeExecutionStrategy(strategy.forward_validation_registration_id, RESUME_CONFIRMATION),
    onSuccess: () => {
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["execution"] });
    },
    onError: (e) => setError(errorMessage(e, "Failed to resume this strategy.")),
  });

  const label =
    strategy.ticker_a === strategy.ticker_b
      ? strategy.ticker_a
      : `${strategy.ticker_a}/${strategy.ticker_b}`;

  return (
    <tr style={{ borderTop: "1px solid var(--border)" }}>
      <td className="py-1 pr-3">{label}</td>
      <td className="py-1 pr-3" style={{ color: "var(--text-muted)" }}>
        {strategy.strategy_name}
      </td>
      <td className="py-1 pr-3">
        {strategy.trailing_sharpe === null
          ? `— (${strategy.trailing_days}/${strategy.breaker_lookback_trading_days}d)`
          : strategy.trailing_sharpe.toFixed(2)}
      </td>
      <td className="py-1 pr-3">
        {strategy.halted_at ? (
          <span style={{ color: "rgb(217, 119, 6)" }}>
            pulled — trailing Sharpe {strategy.halted_trailing_sharpe?.toFixed(2) ?? "—"}
          </span>
        ) : (
          <span style={{ color: "var(--text-muted)" }}>trading</span>
        )}
      </td>
      <td className="py-1">
        {strategy.halted_at ? (
          <button
            type="button"
            onClick={() => resume.mutate()}
            disabled={resume.isPending}
            className="rounded px-2 py-0.5 text-xs"
            style={{ background: "var(--page-plane)", border: "1px solid var(--border)", color: "var(--text-primary)" }}
          >
            {resume.isPending ? "…" : "Resume"}
          </button>
        ) : null}
        {error ? (
          <span className="text-xs ml-2" style={{ color: "var(--danger, #dc2626)" }}>
            {error}
          </span>
        ) : null}
      </td>
    </tr>
  );
}

function SlippageRow({ aggregate }: { aggregate: SlippageAggregateOut }) {
  const excess = aggregate.excess_vs_assumed_bps;
  return (
    <tr style={{ borderTop: "1px solid var(--border)" }}>
      <td className="py-1 pr-3">{aggregate.label}</td>
      <td className="py-1 pr-3">{aggregate.n_fills}</td>
      <td className="py-1 pr-3">{bps(aggregate.notional_weighted_mean_bps)}</td>
      <td className="py-1 pr-3">{bps(aggregate.assumed_cost_bps)}</td>
      <td
        className="py-1 pr-3"
        style={{ color: excess !== null && excess > 0 ? "rgb(217, 119, 6)" : "var(--text-secondary)" }}
      >
        {bps(excess)}
      </td>
      <td className="py-1" style={{ color: "var(--text-muted)" }}>
        {aggregate.meaningful_sample ? "" : "too few fills to read"}
      </td>
    </tr>
  );
}

export function ExecutionPanel() {
  const status = useQuery({
    queryKey: ["execution", "status"],
    queryFn: getExecutionStatus,
    refetchInterval: REFRESH_MS,
  });
  const positions = useQuery({
    queryKey: ["execution", "positions"],
    queryFn: listLivePositions,
    refetchInterval: REFRESH_MS,
    // The broker is unreachable in plenty of normal situations (no
    // credentials configured yet); a failed poll must not spam retries.
    retry: false,
  });
  const orders = useQuery({
    queryKey: ["execution", "orders"],
    queryFn: () => listLiveOrders(50),
    refetchInterval: REFRESH_MS,
  });

  if (status.isLoading) return null;
  if (status.isError || !status.data) {
    return (
      <div className="text-sm" style={{ color: "var(--text-muted)" }}>
        Could not load execution status.
      </div>
    );
  }

  const data = status.data;

  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold" style={{ color: "var(--text-primary)" }}>
          Execution
        </h2>
        <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
          Submits the live portfolio's forward-validated signals to the broker. Trading starts
          halted and stays halted until a human resumes it.
        </p>
      </div>

      <StatusBanner status={data} />

      {data.account_error ? (
        <div className="text-sm rounded p-2" style={{ background: "var(--page-plane)", border: "1px solid var(--border)", color: "var(--text-secondary)" }}>
          Broker not readable: {data.account_error}
        </div>
      ) : (
        <LimitsRow status={data} />
      )}

      <Controls status={data} />

      <div className="space-y-2">
        <div className="text-sm font-medium" style={{ color: "var(--text-secondary)" }}>
          Per-strategy circuit breaker — trailing {data.strategies[0]?.breaker_lookback_trading_days ?? 20}-day
          realized Sharpe, threshold {data.strategies[0]?.breaker_threshold?.toFixed(1) ?? "-1.0"}
        </div>
        {data.strategies.length === 0 ? (
          <div className="text-sm" style={{ color: "var(--text-muted)" }}>
            No strategy has traded yet.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead style={{ color: "var(--text-muted)" }}>
              <tr>
                <th className="text-left font-normal pb-1">Instrument</th>
                <th className="text-left font-normal pb-1">Strategy</th>
                <th className="text-left font-normal pb-1">Trailing Sharpe</th>
                <th className="text-left font-normal pb-1">State</th>
                <th className="text-left font-normal pb-1" />
              </tr>
            </thead>
            <tbody style={{ color: "var(--text-primary)" }}>
              {data.strategies.map((strategy) => (
                <StrategyRow key={strategy.forward_validation_registration_id} strategy={strategy} />
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="space-y-2">
        <div className="text-sm font-medium" style={{ color: "var(--text-secondary)" }}>
          Realized slippage vs. assumed cost
        </div>
        <table className="w-full text-sm">
          <thead style={{ color: "var(--text-muted)" }}>
            <tr>
              <th className="text-left font-normal pb-1">Scope</th>
              <th className="text-left font-normal pb-1">Fills</th>
              <th className="text-left font-normal pb-1">Realized</th>
              <th className="text-left font-normal pb-1">Assumed</th>
              <th className="text-left font-normal pb-1">Excess</th>
              <th className="text-left font-normal pb-1" />
            </tr>
          </thead>
          <tbody style={{ color: "var(--text-primary)" }}>
            <SlippageRow aggregate={data.slippage.overall} />
            {data.slippage.per_strategy.map((aggregate) => (
              <SlippageRow key={aggregate.label} aggregate={aggregate} />
            ))}
          </tbody>
        </table>
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>
          {data.slippage.methodology_note}
        </p>
      </div>

      <div className="space-y-2">
        <div className="text-sm font-medium" style={{ color: "var(--text-secondary)" }}>
          Broker positions (uncached — the same source of truth the runner diffs against)
        </div>
        {positions.isError ? (
          <div className="text-sm" style={{ color: "var(--text-muted)" }}>
            Positions unavailable.
          </div>
        ) : positions.data && positions.data.length > 0 ? (
          <table className="w-full text-sm">
            <thead style={{ color: "var(--text-muted)" }}>
              <tr>
                <th className="text-left font-normal pb-1">Ticker</th>
                <th className="text-left font-normal pb-1">Qty</th>
                <th className="text-left font-normal pb-1">Exposure</th>
                <th className="text-left font-normal pb-1">Unrealized</th>
              </tr>
            </thead>
            <tbody style={{ color: "var(--text-primary)" }}>
              {positions.data.map((position) => (
                <tr key={position.ticker} style={{ borderTop: "1px solid var(--border)" }}>
                  <td className="py-1 pr-3">{position.ticker}</td>
                  <td className="py-1 pr-3">{position.qty}</td>
                  <td className="py-1 pr-3">{money(position.signed_market_value)}</td>
                  <td className="py-1">{position.unrealized_pl === null ? "—" : money(position.unrealized_pl)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="text-sm" style={{ color: "var(--text-muted)" }}>
            Flat.
          </div>
        )}
      </div>

      <div className="space-y-2">
        <div className="text-sm font-medium" style={{ color: "var(--text-secondary)" }}>
          Recent orders
        </div>
        {orders.data && orders.data.length > 0 ? (
          <table className="w-full text-sm">
            <thead style={{ color: "var(--text-muted)" }}>
              <tr>
                <th className="text-left font-normal pb-1">Submitted</th>
                <th className="text-left font-normal pb-1">Ticker</th>
                <th className="text-left font-normal pb-1">Side</th>
                <th className="text-left font-normal pb-1">Size</th>
                <th className="text-left font-normal pb-1">Status</th>
                <th className="text-left font-normal pb-1">Slippage</th>
              </tr>
            </thead>
            <tbody style={{ color: "var(--text-primary)" }}>
              {orders.data.map((order) => (
                <tr key={order.id} style={{ borderTop: "1px solid var(--border)" }}>
                  <td className="py-1 pr-3">{timestamp(order.submitted_at)}</td>
                  <td className="py-1 pr-3">{order.ticker}</td>
                  <td className="py-1 pr-3">{order.side}</td>
                  <td className="py-1 pr-3">
                    {order.notional_requested !== null
                      ? money(order.notional_requested)
                      : `${order.qty_requested ?? 0} sh`}
                  </td>
                  <td className="py-1 pr-3">
                    {order.status}
                    {order.error_message ? ` — ${order.error_message}` : ""}
                  </td>
                  <td className="py-1">{bps(order.realized_slippage_bps)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="text-sm" style={{ color: "var(--text-muted)" }}>
            No orders yet.
          </div>
        )}
      </div>
    </section>
  );
}
