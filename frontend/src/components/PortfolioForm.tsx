import { useState } from "react";
import type { FormEvent } from "react";
import type { HoldingInput, PortfolioAnalyzeRequest } from "../api/client";
import type { ConnectionState, LiveQuote } from "../hooks/useLiveQuotes";
import { LiveQuoteBadge } from "./LiveQuoteBadge";

interface PortfolioFormProps {
  holdings: HoldingInput[];
  onHoldingsChange: (holdings: HoldingInput[]) => void;
  benchmark: string;
  onBenchmarkChange: (benchmark: string) => void;
  liveQuotes: Record<string, LiveQuote>;
  liveConnectionState: ConnectionState;
  onSubmit: (request: PortfolioAnalyzeRequest) => void;
  isLoading: boolean;
  errorMessage?: string;
}

export function PortfolioForm({
  holdings,
  onHoldingsChange,
  benchmark,
  onBenchmarkChange,
  liveQuotes,
  liveConnectionState,
  onSubmit,
  isLoading,
  errorMessage,
}: PortfolioFormProps) {
  const [lookbackYears, setLookbackYears] = useState(3);

  const weightSum = holdings.reduce((sum, h) => sum + (Number(h.weight) || 0), 0);
  const weightsValid = weightSum >= 0.995 && weightSum <= 1.005;

  function updateHolding(index: number, field: keyof HoldingInput, value: string) {
    onHoldingsChange(
      holdings.map((h, i) =>
        i === index
          ? { ...h, [field]: field === "weight" ? Number(value) : value.toUpperCase() }
          : h,
      ),
    );
  }

  function addRow() {
    onHoldingsChange([...holdings, { ticker: "", weight: 0 }]);
  }

  function removeRow(index: number) {
    onHoldingsChange(holdings.filter((_, i) => i !== index));
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!weightsValid) return;
    onSubmit({
      holdings: holdings.filter((h) => h.ticker.trim().length > 0),
      benchmark,
      lookback_years: lookbackYears,
    });
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-lg p-4 space-y-3"
      style={{ background: "var(--surface-1)", border: "1px solid var(--border)" }}
    >
      <div className="text-sm font-medium" style={{ color: "var(--text-secondary)" }}>
        Portfolio holdings
      </div>

      <div className="space-y-2">
        {holdings.map((holding, index) => (
          <div key={index} className="flex gap-2 items-center">
            <input
              type="text"
              value={holding.ticker}
              onChange={(e) => updateHolding(index, "ticker", e.target.value)}
              placeholder="TICKER"
              className="w-28 rounded-md px-2 py-1.5 text-sm"
              style={{
                background: "var(--page-plane)",
                border: "1px solid var(--border)",
                color: "var(--text-primary)",
              }}
            />
            <input
              type="number"
              step="0.01"
              min="0"
              max="1"
              value={holding.weight}
              onChange={(e) => updateHolding(index, "weight", e.target.value)}
              placeholder="0.00"
              className="w-24 rounded-md px-2 py-1.5 text-sm"
              style={{
                background: "var(--page-plane)",
                border: "1px solid var(--border)",
                color: "var(--text-primary)",
              }}
            />
            <span className="text-xs" style={{ color: "var(--text-muted)" }}>
              weight (0-1)
            </span>
            <div className="w-24">
              {holding.ticker.trim() && (
                <LiveQuoteBadge
                  quote={liveQuotes[holding.ticker.trim().toUpperCase()]}
                  connectionState={liveConnectionState}
                />
              )}
            </div>
            {holdings.length > 1 && (
              <button
                type="button"
                onClick={() => removeRow(index)}
                className="text-xs ml-auto px-2 py-1 rounded-md"
                style={{ color: "var(--text-muted)" }}
              >
                Remove
              </button>
            )}
          </div>
        ))}
      </div>

      <button
        type="button"
        onClick={addRow}
        className="text-sm px-3 py-1.5 rounded-md"
        style={{ border: "1px solid var(--border)", color: "var(--text-secondary)" }}
      >
        + Add holding
      </button>

      <div
        className="text-xs"
        style={{ color: weightsValid ? "var(--text-muted)" : "var(--status-critical)" }}
      >
        Weights sum to {weightSum.toFixed(3)} {weightsValid ? "" : "— must sum to ~1.00"}
      </div>

      <div className="flex gap-4 pt-2 items-end">
        <label className="flex flex-col gap-1 text-sm" style={{ color: "var(--text-secondary)" }}>
          Benchmark
          <input
            type="text"
            value={benchmark}
            onChange={(e) => onBenchmarkChange(e.target.value.toUpperCase())}
            className="w-24 rounded-md px-2 py-1.5 text-sm"
            style={{
              background: "var(--page-plane)",
              border: "1px solid var(--border)",
              color: "var(--text-primary)",
            }}
          />
        </label>
        <div className="pb-1.5">
          <LiveQuoteBadge
            quote={liveQuotes[benchmark.trim().toUpperCase()]}
            connectionState={liveConnectionState}
          />
        </div>
        <label className="flex flex-col gap-1 text-sm" style={{ color: "var(--text-secondary)" }}>
          Lookback (years)
          <input
            type="number"
            min={1}
            max={10}
            value={lookbackYears}
            onChange={(e) => setLookbackYears(Number(e.target.value))}
            className="w-24 rounded-md px-2 py-1.5 text-sm"
            style={{
              background: "var(--page-plane)",
              border: "1px solid var(--border)",
              color: "var(--text-primary)",
            }}
          />
        </label>
      </div>

      {errorMessage && (
        <div className="text-sm" style={{ color: "var(--status-critical)" }}>
          {errorMessage}
        </div>
      )}

      <button
        type="submit"
        disabled={!weightsValid || isLoading}
        className="w-full rounded-md py-2 text-sm font-medium text-white disabled:opacity-50"
        style={{ background: "var(--accent-blue)" }}
      >
        {isLoading ? "Analyzing…" : "Analyze portfolio"}
      </button>
    </form>
  );
}
