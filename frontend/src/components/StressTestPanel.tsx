import type { ScenarioOut } from "../api/client";
import { formatMacroValue, formatPercentValue } from "../lib/format";

interface StressTestPanelProps {
  scenarios: ScenarioOut[];
}

function returnColor(value: number): string {
  if (value > 0) return "var(--status-good)";
  if (value < 0) return "var(--status-critical)";
  return "var(--text-muted)";
}

export function StressTestPanel({ scenarios }: StressTestPanelProps) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
      {scenarios.map((scenario) => (
        <div
          key={scenario.scenario_id}
          className="rounded-lg p-4"
          style={{ background: "var(--surface-1)", border: "1px solid var(--border)" }}
        >
          <div className="text-sm font-medium" style={{ color: "var(--text-secondary)" }}>
            {scenario.label}
          </div>
          <div className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
            {scenario.start} to {scenario.end}
          </div>

          <div
            className="mt-3 text-2xl font-semibold"
            style={{ color: returnColor(scenario.portfolio_return) }}
          >
            {formatPercentValue(scenario.portfolio_return * 100)}
          </div>
          <div className="text-xs" style={{ color: "var(--text-muted)" }}>
            Portfolio · benchmark {formatPercentValue(scenario.benchmark_return * 100)}
          </div>

          {scenario.has_estimated && (
            <div
              className="mt-2 text-xs inline-block px-1.5 py-0.5 rounded"
              style={{
                background: "var(--page-plane)",
                border: "1px solid var(--border)",
                color: "var(--text-muted)",
              }}
            >
              includes estimated holdings
            </div>
          )}

          <div className="mt-3 text-xs" style={{ color: "var(--text-muted)" }}>
            {scenario.description}
          </div>

          {scenario.macro_context.length > 0 && (
            <div
              className="mt-3 pt-2 space-y-1"
              style={{ borderTop: "1px solid var(--border)" }}
            >
              {scenario.macro_context.map((point) => (
                <div
                  key={point.series_id}
                  className="text-xs flex justify-between gap-2"
                  style={{ color: "var(--text-muted)" }}
                >
                  <span>{point.label}</span>
                  <span style={{ color: "var(--text-secondary)" }}>
                    {point.start_value !== null
                      ? formatMacroValue(point.start_value, point.unit, point.decimals)
                      : "—"}{" "}
                    (then) →{" "}
                    {point.current_value !== null
                      ? formatMacroValue(point.current_value, point.unit, point.decimals)
                      : "—"}{" "}
                    (now)
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
