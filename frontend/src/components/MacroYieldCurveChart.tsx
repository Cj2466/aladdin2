import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { YieldCurvePointOut } from "../api/client";
import { formatMacroValue } from "../lib/format";

interface MacroYieldCurveChartProps {
  points: YieldCurvePointOut[];
}

interface TooltipPayloadEntry {
  name: string;
  value: number;
  color: string;
}

function CurveTooltip({
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
      <div className="mb-1" style={{ color: "var(--text-secondary)" }}>
        {label}
      </div>
      {payload.map((entry) => (
        <div key={entry.name} style={{ color: entry.color }}>
          {entry.name}: {formatMacroValue(entry.value, "percent", 2)}
        </div>
      ))}
    </div>
  );
}

export function MacroYieldCurveChart({ points }: MacroYieldCurveChartProps) {
  const hasAnyData = points.some((p) => p.today !== null || p.one_year_ago !== null);

  return (
    <div
      className="rounded-lg p-4"
      style={{ background: "var(--surface-1)", border: "1px solid var(--border)" }}
    >
      <div className="text-sm mb-3" style={{ color: "var(--text-secondary)" }}>
        Treasury yield curve
      </div>
      {hasAnyData ? (
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={points} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="var(--gridline)" vertical={false} />
            <XAxis
              dataKey="maturity_label"
              stroke="var(--baseline)"
              tick={{ fill: "var(--text-secondary)", fontSize: 12 }}
            />
            <YAxis
              tickFormatter={(v: number) => formatMacroValue(v, "percent", 1)}
              stroke="var(--baseline)"
              tick={{ fill: "var(--text-secondary)", fontSize: 12 }}
              width={48}
            />
            <Tooltip content={<CurveTooltip />} cursor={{ stroke: "var(--gridline)" }} />
            <Legend wrapperStyle={{ fontSize: 12, color: "var(--text-secondary)" }} />
            <Line
              type="monotone"
              dataKey="today"
              name="Today"
              stroke="var(--series-1)"
              strokeWidth={2}
              dot={{ r: 4 }}
              connectNulls
            />
            <Line
              type="monotone"
              dataKey="one_year_ago"
              name="1 year ago"
              stroke="var(--series-2)"
              strokeWidth={2}
              strokeDasharray="4 4"
              dot={{ r: 4 }}
              connectNulls
            />
          </LineChart>
        </ResponsiveContainer>
      ) : (
        <div className="text-sm py-8 text-center" style={{ color: "var(--text-muted)" }}>
          Yield curve data unavailable
        </div>
      )}
    </div>
  );
}
