import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  getExperimentRunDetail,
  listExperimentRuns,
} from "../api/client";
import type { ExperimentRunSortBy, ExperimentRunSummaryOut, PairsBacktestStatus, SortDirection } from "../api/client";
import { formatPercent } from "../lib/format";
import { EquityCurveChart, ZScoreChart } from "./PairsBacktestCharts";

const PAGE_SIZE = 20;

const STATUS_OPTIONS: { value: PairsBacktestStatus | ""; label: string }[] = [
  { value: "", label: "Any status" },
  { value: "ok", label: "ok" },
  { value: "not_mean_reverting", label: "not mean-reverting" },
  { value: "not_trending", label: "not trending" },
  { value: "insufficient_history", label: "insufficient history" },
];

const COLUMNS: { key: ExperimentRunSortBy; label: string }[] = [
  { key: "sharpe_net", label: "Sharpe (net)" },
  { key: "sharpe_gross", label: "Sharpe (gross)" },
  { key: "max_drawdown_net", label: "Max DD" },
  { key: "num_trades", label: "Trades" },
  { key: "win_rate", label: "Win rate" },
  { key: "computed_at", label: "Computed" },
];

function formatSharpe(value: number | null): string {
  return value === null ? "N/A" : value.toFixed(2);
}

function statusColor(status: PairsBacktestStatus): string {
  if (status === "ok") return "var(--status-good)";
  if (status === "not_mean_reverting" || status === "not_trending") return "var(--status-critical)";
  return "var(--text-muted)";
}

function isMomentum(strategyName: string): boolean {
  return strategyName === "momentum_v1";
}

function tickerLabel(strategyName: string, tickerA: string, tickerB: string): string {
  return isMomentum(strategyName) ? tickerA : `${tickerA}/${tickerB}`;
}

function RunDetail({ runId, onClose }: { runId: number; onClose: () => void }) {
  const { data: result, isLoading } = useQuery({
    queryKey: ["experimentRunDetail", runId],
    queryFn: () => getExperimentRunDetail(runId),
  });

  return (
    <div
      className="rounded-lg p-4 space-y-3"
      style={{ background: "var(--surface-1)", border: "1px solid var(--border)" }}
    >
      <div className="flex items-center justify-between">
        <div className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
          {result
            ? `${isMomentum(result.strategy_name) ? result.ticker_a : `${result.ticker_a} / ${result.ticker_b}`} — run #${runId}`
            : `Run #${runId}`}
        </div>
        <button type="button" onClick={onClose} className="text-xs" style={{ color: "var(--text-muted)" }}>
          close
        </button>
      </div>

      {isLoading && (
        <div className="text-sm" style={{ color: "var(--text-muted)" }}>
          Loading…
        </div>
      )}

      {result && (
        <div className="space-y-3">
          <div className="text-xs italic" style={{ color: "var(--text-muted)" }}>
            {result.search_context.note}
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
                {isMomentum(result.strategy_name)
                  ? `Momentum signal (t-stat of trailing trend; dashed lines mark entry thresholds ±${result.entry_z})`
                  : `Spread z-score (dashed lines mark entry thresholds ±${result.entry_z})`}
              </div>
              <ZScoreChart result={result} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function LeaderboardTable() {
  const [sortBy, setSortBy] = useState<ExperimentRunSortBy>("sharpe_net");
  const [sortDir, setSortDir] = useState<SortDirection>("desc");
  const [tickerFilter, setTickerFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState<PairsBacktestStatus | "">("");
  const [offset, setOffset] = useState(0);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);

  const trimmedTicker = tickerFilter.trim().toUpperCase();

  const { data, isLoading } = useQuery({
    queryKey: ["experimentRuns", sortBy, sortDir, trimmedTicker, statusFilter, offset],
    queryFn: () =>
      listExperimentRuns({
        sort_by: sortBy,
        sort_dir: sortDir,
        ticker_a: trimmedTicker || undefined,
        status: statusFilter || undefined,
        limit: PAGE_SIZE,
        offset,
      }),
  });

  function handleSort(column: ExperimentRunSortBy) {
    if (column === sortBy) {
      setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    } else {
      setSortBy(column);
      setSortDir("desc");
    }
    setOffset(0);
  }

  const results = data?.results ?? [];
  const totalMatching = data?.total_matching ?? 0;
  const rangeStart = totalMatching === 0 ? 0 : offset + 1;
  const rangeEnd = Math.min(offset + PAGE_SIZE, totalMatching);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-2">
        <div>
          <div className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>
            Ticker
          </div>
          <input
            type="text"
            value={tickerFilter}
            onChange={(e) => {
              setTickerFilter(e.target.value);
              setOffset(0);
            }}
            placeholder="e.g. AAPL"
            className="text-sm px-3 py-1.5 rounded-md w-28"
            style={{ background: "var(--page-plane)", border: "1px solid var(--border)", color: "var(--text-primary)" }}
          />
        </div>
        <div>
          <div className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>
            Status
          </div>
          <select
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value as PairsBacktestStatus | "");
              setOffset(0);
            }}
            className="text-sm px-2 py-1.5 rounded-md"
            style={{ background: "var(--page-plane)", border: "1px solid var(--border)", color: "var(--text-primary)" }}
          >
            {STATUS_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {isLoading && (
        <div className="text-sm" style={{ color: "var(--text-muted)" }}>
          Loading…
        </div>
      )}

      {!isLoading && results.length === 0 && (
        <div className="text-sm" style={{ color: "var(--text-muted)" }}>
          No backtests match these filters yet.
        </div>
      )}

      {results.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs" style={{ borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ color: "var(--text-muted)" }}>
                <th className="text-left py-1.5 pr-3">Ticker</th>
                <th className="text-left py-1.5 pr-3">Status</th>
                {COLUMNS.map((col) => (
                  <th key={col.key} className="text-right py-1.5 pr-3">
                    <button
                      type="button"
                      onClick={() => handleSort(col.key)}
                      style={{ color: sortBy === col.key ? "var(--text-primary)" : "var(--text-muted)" }}
                    >
                      {col.label}
                      {sortBy === col.key ? (sortDir === "desc" ? " ↓" : " ↑") : ""}
                    </button>
                  </th>
                ))}
                <th className="text-left py-1.5 pr-3">Config</th>
                <th className="text-left py-1.5">Tested</th>
              </tr>
            </thead>
            <tbody>
              {results.map((row: ExperimentRunSummaryOut) => (
                <tr
                  key={row.id}
                  onClick={() => setSelectedRunId(row.id)}
                  className="cursor-pointer"
                  style={{ borderTop: "1px solid var(--border)" }}
                >
                  <td className="py-1.5 pr-3" style={{ color: "var(--text-primary)" }}>
                    {tickerLabel(row.strategy_name, row.ticker_a, row.ticker_b)}
                  </td>
                  <td className="py-1.5 pr-3" style={{ color: statusColor(row.status) }}>
                    {row.status}
                  </td>
                  <td className="text-right py-1.5 pr-3" style={{ color: "var(--text-primary)" }}>
                    {formatSharpe(row.sharpe_net)}
                  </td>
                  <td className="text-right py-1.5 pr-3" style={{ color: "var(--text-secondary)" }}>
                    {formatSharpe(row.sharpe_gross)}
                  </td>
                  <td className="text-right py-1.5 pr-3" style={{ color: "var(--text-secondary)" }}>
                    {row.max_drawdown_net !== null ? formatPercent(row.max_drawdown_net, 1) : "N/A"}
                  </td>
                  <td className="text-right py-1.5 pr-3" style={{ color: "var(--text-secondary)" }}>
                    {row.num_trades}
                  </td>
                  <td className="text-right py-1.5 pr-3" style={{ color: "var(--text-secondary)" }}>
                    {row.win_rate !== null ? formatPercent(row.win_rate, 0) : "N/A"}
                  </td>
                  <td className="text-right py-1.5 pr-3" style={{ color: "var(--text-muted)" }}>
                    {row.computed_at.slice(0, 10)}
                  </td>
                  <td className="py-1.5 pr-3" style={{ color: "var(--text-muted)" }}>
                    fit {row.fit_window_days}d · z {row.entry_z}/{row.exit_z} · {row.cost_bps}bps
                  </td>
                  <td className="py-1.5" title={`1 of ${row.configurations_tested} configurations tested together`}>
                    <span
                      className="px-1.5 py-0.5 rounded"
                      style={{
                        background: "var(--page-plane)",
                        border: "1px solid var(--border)",
                        color: row.configurations_tested > 1 ? "var(--status-warning)" : "var(--text-muted)",
                      }}
                    >
                      1 of {row.configurations_tested}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {totalMatching > 0 && (
        <div className="flex items-center justify-between text-xs" style={{ color: "var(--text-muted)" }}>
          <span>
            Showing {rangeStart}-{rangeEnd} of {totalMatching}
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
              disabled={offset === 0}
              className="px-2 py-1 rounded-md disabled:opacity-40"
              style={{ border: "1px solid var(--border)" }}
            >
              Prev
            </button>
            <button
              type="button"
              onClick={() => setOffset((o) => o + PAGE_SIZE)}
              disabled={rangeEnd >= totalMatching}
              className="px-2 py-1 rounded-md disabled:opacity-40"
              style={{ border: "1px solid var(--border)" }}
            >
              Next
            </button>
          </div>
        </div>
      )}

      {selectedRunId !== null && (
        <RunDetail runId={selectedRunId} onClose={() => setSelectedRunId(null)} />
      )}
    </div>
  );
}
