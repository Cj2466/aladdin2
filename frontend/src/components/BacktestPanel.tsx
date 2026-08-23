import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { isAxiosError } from "axios";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { registerForwardValidation, runPairsBacktest } from "../api/client";
import type { ApiErrorBody, PairsBacktestResponse } from "../api/client";
import { formatPercent, formatPercentValue } from "../lib/format";

const DEFAULT_METHODOLOGY_NOTE =
  "Research tool, not a trading signal. Each day's position is decided from a rolling " +
  "Ornstein-Uhlenbeck/AR(1) fit on prior data only. A 'strong' fit-quality score measures how " +
  "well the spread fits an AR(1) model — it is not a cointegration test and does not by itself " +
  "distinguish a genuine relationship from two unrelated tickers that happened to look " +
  "mean-reverting over this window. Only the walk-forward, out-of-sample Sharpe ratio below " +
  "carries evidentiary weight. Historical performance is no guarantee of future performance.";

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs" style={{ color: "var(--text-muted)" }}>
        {label}
      </div>
      <div className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
        {value}
      </div>
    </div>
  );
}

function formatSharpe(value: number | null): string {
  return value === null ? "N/A" : value.toFixed(2);
}

function formatCount(value: number | null): string {
  return value === null ? "N/A" : String(value);
}

function EquityCurveChart({ result }: { result: PairsBacktestResponse }) {
  return (
    <ResponsiveContainer width="100%" height={180}>
      <LineChart data={result.equity_curve} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid stroke="var(--gridline)" vertical={false} />
        <XAxis
          dataKey="date"
          stroke="var(--baseline)"
          tick={{ fill: "var(--text-secondary)", fontSize: 10 }}
          interval="preserveStartEnd"
        />
        <YAxis
          tickFormatter={(v: number) => v.toFixed(2)}
          stroke="var(--baseline)"
          tick={{ fill: "var(--text-secondary)", fontSize: 12 }}
          width={44}
          domain={["auto", "auto"]}
        />
        <Tooltip
          contentStyle={{ background: "var(--surface-1)", border: "1px solid var(--border)" }}
          labelStyle={{ color: "var(--text-secondary)" }}
          formatter={(v: unknown) => (typeof v === "number" ? v.toFixed(4) : String(v))}
        />
        <ReferenceLine y={1.0} stroke="var(--baseline)" strokeDasharray="3 3" />
        <Line type="monotone" dataKey="equity" stroke="var(--series-1)" strokeWidth={2} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

function ZScoreChart({ result }: { result: PairsBacktestResponse }) {
  return (
    <ResponsiveContainer width="100%" height={140}>
      <LineChart data={result.equity_curve} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid stroke="var(--gridline)" vertical={false} />
        <XAxis
          dataKey="date"
          stroke="var(--baseline)"
          tick={{ fill: "var(--text-secondary)", fontSize: 10 }}
          interval="preserveStartEnd"
        />
        <YAxis
          stroke="var(--baseline)"
          tick={{ fill: "var(--text-secondary)", fontSize: 12 }}
          width={30}
          domain={["auto", "auto"]}
        />
        <Tooltip
          contentStyle={{ background: "var(--surface-1)", border: "1px solid var(--border)" }}
          labelStyle={{ color: "var(--text-secondary)" }}
          formatter={(v: unknown) => (typeof v === "number" ? v.toFixed(2) : "—")}
        />
        <ReferenceLine y={0} stroke="var(--baseline)" />
        <ReferenceLine y={result.entry_z} stroke="var(--status-warning)" strokeDasharray="3 3" />
        <ReferenceLine y={-result.entry_z} stroke="var(--status-warning)" strokeDasharray="3 3" />
        <Line
          type="monotone"
          dataKey="z_score"
          stroke="var(--series-2)"
          strokeWidth={1.5}
          dot={false}
          connectNulls={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

function TrackButton({ result }: { result: PairsBacktestResponse }) {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: () =>
      registerForwardValidation({
        ticker_a: result.ticker_a,
        ticker_b: result.ticker_b,
        fit_window_days: result.fit_window_days,
        entry_z: result.entry_z,
        exit_z: result.exit_z,
        cost_bps: result.cost_bps,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["forwardValidationRegistrations"] });
    },
  });

  let label = "Track this configuration";
  if (mutation.isPending) label = "Tracking…";
  else if (mutation.isSuccess) label = mutation.data.created ? "Now tracking" : "Already tracking";
  else if (mutation.isError) label = "Couldn't start tracking";

  return (
    <button
      type="button"
      onClick={() => mutation.mutate()}
      disabled={mutation.isPending || mutation.isSuccess}
      className="text-xs px-2.5 py-1 rounded-md disabled:opacity-70"
      style={{
        background: mutation.isSuccess ? "var(--status-good)" : "var(--page-plane)",
        border: "1px solid var(--border)",
        color: mutation.isSuccess ? "white" : "var(--text-secondary)",
      }}
    >
      {label}
    </button>
  );
}

function ResultView({ result }: { result: PairsBacktestResponse }) {
  if (result.status === "insufficient_history") {
    return (
      <div className="text-sm py-4" style={{ color: "var(--text-muted)" }}>
        Not enough overlapping history for this pair and window — try a longer lookback or a
        shorter fit window.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {result.status === "not_mean_reverting" && (
        <div
          className="rounded-md p-3 text-xs"
          style={{
            background: "var(--page-plane)",
            border: "1px solid var(--status-critical)",
            color: "var(--text-secondary)",
          }}
        >
          This pair's spread was not found to be mean-reverting over this window — no equilibrium
          level could be honestly fit. The real spread is still charted below; no z-score or trades
          were generated from it.
        </div>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Field label="Sharpe (net)" value={formatSharpe(result.sharpe_net)} />
        <Field label="Sharpe (gross)" value={formatSharpe(result.sharpe_gross)} />
        <Field
          label="Total return (net)"
          value={result.total_return_net !== null ? formatPercent(result.total_return_net, 1) : "N/A"}
        />
        <Field
          label="Max drawdown (net)"
          value={result.max_drawdown_net !== null ? formatPercent(result.max_drawdown_net, 1) : "N/A"}
        />
        <Field
          label="Win rate"
          value={result.win_rate !== null ? formatPercent(result.win_rate, 0) : "N/A"}
        />
        <Field label="# trades" value={formatCount(result.num_trades)} />
        <Field
          label="Exposure"
          value={result.exposure_pct !== null ? formatPercent(result.exposure_pct, 0) : "N/A"}
        />
        <Field
          label="% days mean-reverting"
          value={formatPercent(result.pct_days_mean_reverting, 0)}
        />
      </div>

      {result.equity_curve.length > 0 && (
        <div className="space-y-1">
          <div className="text-xs" style={{ color: "var(--text-muted)" }}>
            Equity curve (net of costs, starts at 1.00)
          </div>
          <EquityCurveChart result={result} />
        </div>
      )}

      {result.status === "ok" && result.equity_curve.length > 0 && (
        <div className="space-y-1">
          <div className="text-xs" style={{ color: "var(--text-muted)" }}>
            Spread z-score (dashed lines mark entry thresholds ±{result.entry_z})
          </div>
          <ZScoreChart result={result} />
        </div>
      )}

      {result.trade_log.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs" style={{ borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ color: "var(--text-muted)" }}>
                <th className="text-left py-1.5 pr-3">Entry</th>
                <th className="text-left py-1.5 pr-3">Exit</th>
                <th className="text-left py-1.5 pr-3">Direction</th>
                <th className="text-right py-1.5 pr-3">Days</th>
                <th className="text-right py-1.5">Return</th>
              </tr>
            </thead>
            <tbody>
              {result.trade_log.map((t) => (
                <tr key={`${t.entry_date}-${t.direction}`} style={{ borderTop: "1px solid var(--border)" }}>
                  <td className="py-1.5 pr-3" style={{ color: "var(--text-primary)" }}>
                    {t.entry_date}
                  </td>
                  <td className="py-1.5 pr-3" style={{ color: "var(--text-secondary)" }}>
                    {t.exit_date ?? (t.still_open ? "still open" : "—")}
                  </td>
                  <td className="py-1.5 pr-3" style={{ color: "var(--text-secondary)" }}>
                    {t.direction === "long_spread" ? "Long spread" : "Short spread"}
                  </td>
                  <td className="text-right py-1.5 pr-3" style={{ color: "var(--text-secondary)" }}>
                    {t.holding_days}
                  </td>
                  <td
                    className="text-right py-1.5"
                    style={{ color: t.trade_return >= 0 ? "var(--status-good)" : "var(--status-critical)" }}
                  >
                    {formatPercentValue(t.trade_return * 100, 2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="flex items-center justify-between text-xs" style={{ color: "var(--text-muted)" }}>
        <span className="italic">{result.search_context.note}</span>
        <div className="flex items-center gap-2">
          {result.status === "ok" && <TrackButton result={result} />}
          <span
            className="px-1.5 py-0.5 rounded"
            style={{
              background: "var(--page-plane)",
              border: "1px solid var(--border)",
              color: result.cached ? "var(--status-good)" : "var(--text-muted)",
            }}
          >
            {result.cached ? "cached" : "freshly computed"}
          </span>
        </div>
      </div>
    </div>
  );
}

export function BacktestPanel() {
  const [isExpanded, setIsExpanded] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [tickerA, setTickerA] = useState("");
  const [tickerB, setTickerB] = useState("");
  const [fitWindowDays, setFitWindowDays] = useState(252);
  const [entryZ, setEntryZ] = useState(2.0);
  const [exitZ, setExitZ] = useState(0.0);
  const [costBps, setCostBps] = useState(10.0);
  const [lookbackYears, setLookbackYears] = useState(5);

  const mutation = useMutation({
    mutationFn: () =>
      runPairsBacktest({
        ticker_a: tickerA,
        ticker_b: tickerB,
        fit_window_days: fitWindowDays,
        entry_z: entryZ,
        exit_z: exitZ,
        cost_bps: costBps,
        lookback_years: lookbackYears,
      }),
  });

  const errorMessage = mutation.error
    ? isAxiosError<ApiErrorBody>(mutation.error)
      ? (mutation.error.response?.data?.detail ?? "Backtest failed.")
      : "Something went wrong."
    : undefined;

  function handleRun() {
    if (!tickerA.trim() || !tickerB.trim()) return;
    mutation.mutate();
  }

  return (
    <div>
      <button
        type="button"
        onClick={() => setIsExpanded((v) => !v)}
        className="text-sm"
        style={{ color: "var(--text-secondary)" }}
      >
        Pairs trading backtest (OU / AR(1) mean reversion) — experimental {isExpanded ? "▾" : "▸"}
      </button>

      {isExpanded && (
        <div
          className="mt-3 rounded-lg p-4 space-y-3"
          style={{ background: "var(--surface-1)", border: "1px solid var(--border)" }}
        >
          <div
            className="rounded-md p-3 text-xs"
            style={{
              background: "var(--page-plane)",
              border: "1px solid var(--status-warning)",
              color: "var(--text-secondary)",
            }}
          >
            ⚠ {mutation.data?.methodology_note ?? DEFAULT_METHODOLOGY_NOTE}
          </div>

          <div className="flex flex-wrap items-end gap-2">
            <div>
              <div className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>
                Ticker A
              </div>
              <input
                type="text"
                value={tickerA}
                onChange={(e) => setTickerA(e.target.value)}
                placeholder="e.g. KO"
                className="text-sm px-3 py-1.5 rounded-md w-28"
                style={{
                  background: "var(--page-plane)",
                  border: "1px solid var(--border)",
                  color: "var(--text-primary)",
                }}
              />
            </div>
            <div>
              <div className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>
                Ticker B
              </div>
              <input
                type="text"
                value={tickerB}
                onChange={(e) => setTickerB(e.target.value)}
                placeholder="e.g. PEP"
                className="text-sm px-3 py-1.5 rounded-md w-28"
                style={{
                  background: "var(--page-plane)",
                  border: "1px solid var(--border)",
                  color: "var(--text-primary)",
                }}
              />
            </div>
            <button
              type="button"
              onClick={handleRun}
              disabled={mutation.isPending || !tickerA.trim() || !tickerB.trim()}
              className="text-sm px-3 py-1.5 rounded-md text-white disabled:opacity-50"
              style={{ background: "var(--accent-blue)" }}
            >
              {mutation.isPending ? "Running…" : "Run backtest"}
            </button>
          </div>

          <div>
            <button
              type="button"
              onClick={() => setShowAdvanced((v) => !v)}
              className="text-xs"
              style={{ color: "var(--text-muted)" }}
            >
              Advanced parameters {showAdvanced ? "▾" : "▸"}
            </button>
            {showAdvanced && (
              <div className="mt-2 grid grid-cols-2 sm:grid-cols-5 gap-2">
                <div>
                  <div className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>
                    Fit window (days)
                  </div>
                  <input
                    type="number"
                    value={fitWindowDays}
                    onChange={(e) => setFitWindowDays(Number(e.target.value))}
                    className="text-sm px-2 py-1 rounded-md w-full"
                    style={{ background: "var(--page-plane)", border: "1px solid var(--border)", color: "var(--text-primary)" }}
                  />
                </div>
                <div>
                  <div className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>
                    Entry z
                  </div>
                  <input
                    type="number"
                    step="0.1"
                    value={entryZ}
                    onChange={(e) => setEntryZ(Number(e.target.value))}
                    className="text-sm px-2 py-1 rounded-md w-full"
                    style={{ background: "var(--page-plane)", border: "1px solid var(--border)", color: "var(--text-primary)" }}
                  />
                </div>
                <div>
                  <div className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>
                    Exit z
                  </div>
                  <input
                    type="number"
                    step="0.1"
                    value={exitZ}
                    onChange={(e) => setExitZ(Number(e.target.value))}
                    className="text-sm px-2 py-1 rounded-md w-full"
                    style={{ background: "var(--page-plane)", border: "1px solid var(--border)", color: "var(--text-primary)" }}
                  />
                </div>
                <div>
                  <div className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>
                    Cost (bps)
                  </div>
                  <input
                    type="number"
                    step="1"
                    value={costBps}
                    onChange={(e) => setCostBps(Number(e.target.value))}
                    className="text-sm px-2 py-1 rounded-md w-full"
                    style={{ background: "var(--page-plane)", border: "1px solid var(--border)", color: "var(--text-primary)" }}
                  />
                </div>
                <div>
                  <div className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>
                    Lookback (years)
                  </div>
                  <input
                    type="number"
                    value={lookbackYears}
                    onChange={(e) => setLookbackYears(Number(e.target.value))}
                    className="text-sm px-2 py-1 rounded-md w-full"
                    style={{ background: "var(--page-plane)", border: "1px solid var(--border)", color: "var(--text-primary)" }}
                  />
                </div>
              </div>
            )}
          </div>

          {errorMessage && (
            <div className="text-sm" style={{ color: "var(--status-critical)" }}>
              {errorMessage}
            </div>
          )}

          {mutation.data && <ResultView result={mutation.data} />}
        </div>
      )}
    </div>
  );
}
