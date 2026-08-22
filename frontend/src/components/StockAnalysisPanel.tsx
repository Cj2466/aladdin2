import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { isAxiosError } from "axios";
import { getStockAnalysis } from "../api/client";
import type { ApiErrorBody, RecommendationTrendOut } from "../api/client";
import { MacroStatCard } from "./MacroStatCard";

// Every one of these renders "N/A" for a null field rather than 0 or a
// silent blank — a missing Finnhub metric must never look like a real
// zero value.

function formatPercentLevel(value: number | null, digits = 1): string {
  return value === null ? "N/A" : `${value.toFixed(digits)}%`;
}

function formatRatio(value: number | null, digits = 2): string {
  return value === null ? "N/A" : `${value.toFixed(digits)}x`;
}

function formatPrice(value: number | null, currency: string | null, digits = 2): string {
  if (value === null) return "N/A";
  const symbol = !currency || currency === "USD" ? "$" : `${currency} `;
  return `${symbol}${value.toFixed(digits)}`;
}

// market_capitalization / share_outstanding arrive from Finnhub in
// millions (confirmed via a live profile2 call) — converted here at the
// display layer, same convention as GFDEBTN's millions->trillions
// conversion for the macro dashboard.
function formatMarketCap(millions: number | null): string {
  if (millions === null) return "N/A";
  if (millions >= 1_000_000) return `$${(millions / 1_000_000).toFixed(2)}T`;
  if (millions >= 1_000) return `$${(millions / 1_000).toFixed(2)}B`;
  return `$${millions.toFixed(0)}M`;
}

function formatShareCount(millions: number | null): string {
  if (millions === null) return "N/A";
  if (millions >= 1_000) return `${(millions / 1_000).toFixed(2)}B shares`;
  return `${millions.toFixed(1)}M shares`;
}

function formatVolume(millions: number | null): string {
  if (millions === null) return "N/A";
  return `${millions.toFixed(2)}M shares/day`;
}

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

function RecommendationTrendBar({ trend }: { trend: RecommendationTrendOut[] }) {
  if (trend.length === 0) {
    return (
      <div className="text-xs" style={{ color: "var(--text-muted)" }}>
        No analyst recommendation data available.
      </div>
    );
  }
  const latest = trend[0];
  const segments = [
    { label: "Strong buy", count: latest.strong_buy, color: "var(--status-good)" },
    { label: "Buy", count: latest.buy, color: "var(--series-1)" },
    { label: "Hold", count: latest.hold, color: "var(--text-muted)" },
    { label: "Sell", count: latest.sell, color: "var(--status-warning)" },
    { label: "Strong sell", count: latest.strong_sell, color: "var(--status-critical)" },
  ];
  const total = segments.reduce((sum, s) => sum + s.count, 0);

  return (
    <div className="space-y-1.5">
      <div className="text-xs" style={{ color: "var(--text-muted)" }}>
        Analyst recommendations — {latest.period}
      </div>
      {total > 0 && (
        <div
          className="flex h-2 rounded-full overflow-hidden"
          style={{ background: "var(--page-plane)" }}
        >
          {segments.map(
            (s) =>
              s.count > 0 && (
                <div
                  key={s.label}
                  title={`${s.label}: ${s.count}`}
                  style={{ width: `${(s.count / total) * 100}%`, background: s.color }}
                />
              ),
          )}
        </div>
      )}
      <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs" style={{ color: "var(--text-secondary)" }}>
        {segments.map((s) => (
          <span key={s.label}>
            {s.label}: <span style={{ color: "var(--text-primary)" }}>{s.count}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

export function StockAnalysisPanel() {
  const [tickerInput, setTickerInput] = useState("");
  const mutation = useMutation({
    mutationFn: (ticker: string) => getStockAnalysis(ticker),
  });

  const errorMessage = mutation.error
    ? isAxiosError<ApiErrorBody>(mutation.error)
      ? (mutation.error.response?.data?.detail ?? "Couldn't load stock analysis.")
      : "Something went wrong."
    : undefined;

  function handleAnalyze() {
    const ticker = tickerInput.trim().toUpperCase();
    if (!ticker) return;
    mutation.mutate(ticker);
  }

  function handlePeerClick(peer: string) {
    setTickerInput(peer);
    mutation.mutate(peer);
  }

  const result = mutation.data;
  const f = result?.fundamentals;

  return (
    <div
      className="rounded-lg p-4 space-y-3"
      style={{ background: "var(--surface-1)", border: "1px solid var(--border)" }}
    >
      <div className="text-sm font-medium" style={{ color: "var(--text-secondary)" }}>
        Individual stock analysis
      </div>

      <div className="flex gap-2">
        <input
          type="text"
          value={tickerInput}
          onChange={(e) => setTickerInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleAnalyze()}
          placeholder="Ticker, e.g. AAPL"
          className="text-sm px-3 py-1.5 rounded-md flex-1"
          style={{
            background: "var(--page-plane)",
            border: "1px solid var(--border)",
            color: "var(--text-primary)",
          }}
        />
        <button
          type="button"
          onClick={handleAnalyze}
          disabled={mutation.isPending || !tickerInput.trim()}
          className="text-sm px-3 py-1.5 rounded-md text-white disabled:opacity-50"
          style={{ background: "var(--accent-blue)" }}
        >
          {mutation.isPending ? "Analyzing…" : "Analyze"}
        </button>
      </div>

      {errorMessage && (
        <div className="text-sm" style={{ color: "var(--status-critical)" }}>
          {errorMessage}
        </div>
      )}

      {f && result && (
        <div className="space-y-4">
          <div className="flex items-center gap-3">
            {f.logo && (
              <img
                src={f.logo}
                alt=""
                className="w-10 h-10 rounded"
                style={{ background: "var(--page-plane)" }}
              />
            )}
            <div>
              <div className="text-base font-semibold" style={{ color: "var(--text-primary)" }}>
                {f.company_name ?? f.ticker}{" "}
                <span style={{ color: "var(--text-muted)" }}>({f.ticker})</span>
              </div>
              <div className="text-xs" style={{ color: "var(--text-muted)" }}>
                {[f.exchange, f.finnhub_industry, f.country].filter(Boolean).join(" · ") || "—"}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <Field label="Market cap" value={formatMarketCap(f.market_capitalization)} />
            <Field label="Shares outstanding" value={formatShareCount(f.share_outstanding)} />
            <Field label="P/E (TTM)" value={f.pe_ttm !== null ? f.pe_ttm.toFixed(2) : "N/A"} />
            <Field label="EPS (TTM)" value={formatPrice(f.eps_ttm, f.currency)} />
            <Field label="Beta" value={f.beta !== null ? f.beta.toFixed(2) : "N/A"} />
            <Field
              label="52-week range"
              value={
                f.week52_low !== null && f.week52_high !== null
                  ? `${formatPrice(f.week52_low, f.currency)} – ${formatPrice(f.week52_high, f.currency)}`
                  : "N/A"
              }
            />
            <Field label="Dividend yield (TTM)" value={formatPercentLevel(f.dividend_yield_ttm)} />
            <Field label="Avg volume (10d)" value={formatVolume(f.avg_10day_volume)} />
            <Field label="ROE (TTM)" value={formatPercentLevel(f.roe_ttm)} />
            <Field label="ROA (TTM)" value={formatPercentLevel(f.roa_ttm)} />
            <Field label="Gross margin (TTM)" value={formatPercentLevel(f.gross_margin_ttm)} />
            <Field label="Net margin (TTM)" value={formatPercentLevel(f.net_margin_ttm)} />
            <Field label="Current ratio" value={formatRatio(f.current_ratio)} />
            <Field label="Quick ratio" value={formatRatio(f.quick_ratio)} />
            <Field label="Debt / equity" value={formatRatio(f.debt_to_equity)} />
          </div>

          <RecommendationTrendBar trend={f.recommendation_trend} />

          {f.peers.length > 0 && (
            <div className="space-y-1.5">
              <div className="text-xs" style={{ color: "var(--text-muted)" }}>
                Peers
              </div>
              <div className="flex flex-wrap gap-1.5">
                {f.peers.map((peer) => (
                  <button
                    key={peer}
                    type="button"
                    onClick={() => handlePeerClick(peer)}
                    className="text-xs px-2 py-1 rounded-md"
                    style={{
                      background: "var(--page-plane)",
                      border: "1px solid var(--border)",
                      color: "var(--text-secondary)",
                    }}
                  >
                    {peer}
                  </button>
                ))}
              </div>
            </div>
          )}

          {result.macro_context.length > 0 && (
            <div className="space-y-2">
              <div className="text-xs" style={{ color: "var(--text-muted)" }}>
                Macro backdrop
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {result.macro_context.map((s) => (
                  <MacroStatCard key={s.series_id} series={s} />
                ))}
              </div>
            </div>
          )}

          <div
            className="rounded-md p-3 text-xs"
            style={{
              background: "var(--page-plane)",
              border: "1px solid var(--status-warning)",
              color: "var(--text-secondary)",
            }}
          >
            ⚠ Fundamentals from Finnhub, cached up to 24h — not real-time. For informational
            purposes only, not investment advice.
          </div>
        </div>
      )}
    </div>
  );
}
