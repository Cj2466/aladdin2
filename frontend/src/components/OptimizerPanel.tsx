import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { HoldingInput, PortfolioOptimizeResponse } from "../api/client";
import { formatPercent } from "../lib/format";

interface OptimizerPanelProps {
  result?: PortfolioOptimizeResponse;
  isLoading: boolean;
  errorMessage?: string;
  onRun: () => void;
  onApply: (holdings: HoldingInput[]) => void;
  disabled?: boolean;
  /** Maps a weight's key to a display label, for callers whose "tickers"
   * aren't tickers (the strategy-portfolio panel keys weights by
   * experiment_run_id). Affects the bar chart's category labels ONLY —
   * onApply always hands back the untransformed keys, so nothing
   * round-trips through a display string. Omitting it leaves the existing
   * ticker-based Dashboard usage byte-identical. */
  labelFor?: (ticker: string) => string;
}

interface TooltipPayloadEntry {
  value: number;
}

function WeightsTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: TooltipPayloadEntry[];
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div
      className="rounded-md px-3 py-2 text-sm shadow-sm"
      style={{ background: "var(--surface-1)", border: "1px solid var(--border)" }}
    >
      <div style={{ color: "var(--text-secondary)" }}>{label}</div>
      <div className="font-semibold" style={{ color: "var(--text-primary)" }}>
        {formatPercent(payload[0].value, 1)}
      </div>
    </div>
  );
}

function StatColumn({ title, expectedReturn, volatility, sharpe }: {
  title: string;
  expectedReturn: number;
  volatility: number;
  sharpe: number;
}) {
  return (
    <div className="space-y-1">
      <div className="text-xs font-medium" style={{ color: "var(--text-secondary)" }}>
        {title}
      </div>
      <div className="text-xs" style={{ color: "var(--text-muted)" }}>
        Expected return:{" "}
        <span style={{ color: "var(--text-primary)" }}>{formatPercent(expectedReturn)}</span>
      </div>
      <div className="text-xs" style={{ color: "var(--text-muted)" }}>
        Volatility: <span style={{ color: "var(--text-primary)" }}>{formatPercent(volatility)}</span>
      </div>
      <div className="text-xs" style={{ color: "var(--text-muted)" }}>
        Sharpe ratio:{" "}
        <span style={{ color: "var(--text-primary)" }}>{sharpe.toFixed(2)}</span>
      </div>
    </div>
  );
}

export function OptimizerPanel({
  result,
  isLoading,
  errorMessage,
  onRun,
  onApply,
  disabled,
  labelFor,
}: OptimizerPanelProps) {
  const chartData = result?.optimized_weights.map((h) => ({
    ...h,
    label: labelFor ? labelFor(h.ticker) : h.ticker,
  }));

  return (
    <div
      className="rounded-lg p-4 space-y-3"
      style={{ background: "var(--surface-1)", border: "1px solid var(--border)" }}
    >
      <div className="flex items-center justify-between">
        <div className="text-sm font-medium" style={{ color: "var(--text-secondary)" }}>
          Portfolio optimizer — max Sharpe ratio
        </div>
        <button
          type="button"
          onClick={onRun}
          disabled={isLoading || disabled}
          className="text-sm px-3 py-1.5 rounded-md text-white disabled:opacity-50"
          style={{ background: "var(--accent-blue)" }}
        >
          {isLoading ? "Optimizing…" : "Run optimizer"}
        </button>
      </div>

      {errorMessage && (
        <div className="text-sm" style={{ color: "var(--status-critical)" }}>
          {errorMessage}
        </div>
      )}

      {result && (
        <div className="space-y-4">
          <div className="text-xs" style={{ color: "var(--text-muted)" }}>
            Long-only, capped at {formatPercent(result.max_weight_cap, 0)} per holding, using a{" "}
            {formatPercent(result.risk_free_rate, 1)} risk-free rate — as of {result.as_of}.
          </div>

          <div className="grid grid-cols-2 gap-4">
            <StatColumn
              title="Current"
              expectedReturn={result.current_expected_return}
              volatility={result.current_volatility}
              sharpe={result.current_sharpe}
            />
            <StatColumn
              title="Optimized"
              expectedReturn={result.optimized_expected_return}
              volatility={result.optimized_volatility}
              sharpe={result.optimized_sharpe}
            />
          </div>

          <div className="text-xs" style={{ color: "var(--text-secondary)" }}>
            Optimized weights by holding
          </div>
          <ResponsiveContainer width="100%" height={Math.max(80, chartData!.length * 36)}>
            <BarChart data={chartData} layout="vertical" margin={{ left: 8, right: 24 }}>
              <CartesianGrid horizontal={false} stroke="var(--gridline)" />
              <XAxis
                type="number"
                domain={[0, "dataMax"]}
                tickFormatter={(v: number) => formatPercent(v, 0)}
                stroke="var(--baseline)"
                tick={{ fill: "var(--text-secondary)", fontSize: 12 }}
              />
              <YAxis
                type="category"
                dataKey="label"
                width={labelFor ? 140 : 70}
                stroke="var(--baseline)"
                tick={{ fill: "var(--text-secondary)", fontSize: 12 }}
              />
              <Tooltip content={<WeightsTooltip />} cursor={{ fill: "var(--diverging-mid)" }} />
              <Bar dataKey="weight" radius={4} barSize={14}>
                {chartData!.map((entry) => (
                  <Cell key={entry.ticker} fill="var(--accent-blue)" />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>

          {result.warnings.length > 0 && (
            <div className="space-y-1">
              {result.warnings.map((w) => (
                <div key={w} className="text-xs" style={{ color: "var(--status-warning)" }}>
                  ⚠ {w}
                </div>
              ))}
            </div>
          )}

          <button
            type="button"
            onClick={() =>
              onApply(result.optimized_weights.map((h) => ({ ticker: h.ticker, weight: h.weight })))
            }
            className="text-sm px-3 py-1.5 rounded-md"
            style={{ border: "1px solid var(--border)", color: "var(--text-secondary)" }}
          >
            Apply to holdings
          </button>
        </div>
      )}
    </div>
  );
}
