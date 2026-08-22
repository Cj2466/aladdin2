import type { PortfolioFactorRiskResponse } from "../api/client";
import { formatPercent } from "../lib/format";
import { FactorExposureChart } from "./FactorExposureChart";
import { SectorExposureChart } from "./SectorExposureChart";

interface FactorRiskPanelProps {
  result?: PortfolioFactorRiskResponse;
  isLoading: boolean;
  errorMessage?: string;
  onRun: () => void;
  disabled?: boolean;
}

export function FactorRiskPanel({
  result,
  isLoading,
  errorMessage,
  onRun,
  disabled,
}: FactorRiskPanelProps) {
  const factorKeys = result?.factor_detail.map((f) => f.factor) ?? [];
  const factorLabels = result?.factor_detail.map((f) => f.label) ?? [];

  return (
    <div
      className="rounded-lg p-4 space-y-3"
      style={{ background: "var(--surface-1)", border: "1px solid var(--border)" }}
    >
      <div className="flex items-center justify-between">
        <div className="text-sm font-medium" style={{ color: "var(--text-secondary)" }}>
          Factor risk decomposition
        </div>
        <button
          type="button"
          onClick={onRun}
          disabled={isLoading || disabled}
          className="text-sm px-3 py-1.5 rounded-md text-white disabled:opacity-50"
          style={{ background: "var(--accent-blue)" }}
        >
          {isLoading ? "Analyzing…" : "Run factor analysis"}
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
            {result.lookback_years}-year lookback against ETF-proxy style factors — as of{" "}
            {result.as_of}.
          </div>

          {result.warnings.length > 0 && (
            <div className="space-y-1">
              {result.warnings.map((w) => (
                <div key={w} className="text-xs" style={{ color: "var(--status-warning)" }}>
                  ⚠ {w}
                </div>
              ))}
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <FactorExposureChart exposures={result.factor_detail} />
            <SectorExposureChart title="Risk contribution" slices={result.risk_contribution} />
          </div>

          <div className="text-xs" style={{ color: "var(--text-secondary)" }}>
            Per-holding factor betas
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs" style={{ borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border)" }}>
                  <th className="text-left py-1.5 pr-3" style={{ color: "var(--text-secondary)" }}>
                    Ticker
                  </th>
                  {factorLabels.map((label) => (
                    <th
                      key={label}
                      className="text-right py-1.5 px-2"
                      style={{ color: "var(--text-secondary)" }}
                    >
                      {label}
                    </th>
                  ))}
                  <th className="text-right py-1.5 px-2" style={{ color: "var(--text-secondary)" }}>
                    R²
                  </th>
                  <th className="text-right py-1.5 pl-2" style={{ color: "var(--text-secondary)" }}>
                    Idio. vol
                  </th>
                </tr>
              </thead>
              <tbody>
                {result.holdings.map((h) => (
                  <tr key={h.ticker} style={{ borderBottom: "1px solid var(--border)" }}>
                    <td className="py-1.5 pr-3 font-medium" style={{ color: "var(--text-primary)" }}>
                      {h.ticker}
                    </td>
                    {factorKeys.map((key) => (
                      <td
                        key={key}
                        className="text-right py-1.5 px-2"
                        style={{ color: "var(--text-primary)" }}
                      >
                        {h.betas[key].toFixed(2)}
                      </td>
                    ))}
                    <td className="text-right py-1.5 px-2" style={{ color: "var(--text-primary)" }}>
                      {Number.isNaN(h.r_squared) ? "—" : formatPercent(h.r_squared, 0)}
                    </td>
                    <td className="text-right py-1.5 pl-2" style={{ color: "var(--text-primary)" }}>
                      {formatPercent(h.idiosyncratic_volatility_annualized, 1)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
