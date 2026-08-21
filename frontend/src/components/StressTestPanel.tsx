import type { ScenarioOut } from "../api/client";
import { formatPercentValue } from "../lib/format";

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
        </div>
      ))}
    </div>
  );
}
