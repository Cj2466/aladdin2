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
import type { ExposureSliceOut } from "../api/client";
import { formatPercentValue } from "../lib/format";

interface SectorExposureChartProps {
  title: string;
  slices: ExposureSliceOut[];
}

// Fixed categorical order (never cycled) — an 8th+ distinct label folds
// into "Other" rather than reusing a hue, so identity stays unambiguous.
const SERIES_COLORS = [
  "var(--series-1)",
  "var(--series-2)",
  "var(--series-3)",
  "var(--series-4)",
  "var(--series-5)",
  "var(--series-6)",
  "var(--series-7)",
  "var(--series-8)",
];
const MAX_DIRECT_SLICES = 7;
const OTHER_COLOR = "var(--text-muted)";

function foldOverflow(slices: ExposureSliceOut[]): ExposureSliceOut[] {
  const sorted = [...slices].sort((a, b) => b.weight - a.weight);
  if (sorted.length <= MAX_DIRECT_SLICES + 1) return sorted;
  const top = sorted.slice(0, MAX_DIRECT_SLICES);
  const restWeight = sorted.slice(MAX_DIRECT_SLICES).reduce((sum, s) => sum + s.weight, 0);
  return [...top, { label: "Other", weight: restWeight }];
}

interface TooltipPayloadEntry {
  value: number;
  payload: { label: string };
}

function ExposureTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: TooltipPayloadEntry[];
}) {
  if (!active || !payload?.length) return null;
  return (
    <div
      className="rounded-md px-3 py-2 text-sm shadow-sm"
      style={{ background: "var(--surface-1)", border: "1px solid var(--border)" }}
    >
      <div style={{ color: "var(--text-secondary)" }}>{payload[0].payload.label}</div>
      <div className="font-semibold" style={{ color: "var(--text-primary)" }}>
        {formatPercentValue(payload[0].value * 100)}
      </div>
    </div>
  );
}

export function SectorExposureChart({ title, slices }: SectorExposureChartProps) {
  const data = foldOverflow(slices);
  const height = Math.max(80, data.length * 36);

  return (
    <div
      className="rounded-lg p-4"
      style={{ background: "var(--surface-1)", border: "1px solid var(--border)" }}
    >
      <div className="text-sm mb-3" style={{ color: "var(--text-secondary)" }}>
        {title}
      </div>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} layout="vertical" margin={{ left: 8, right: 24 }}>
          <CartesianGrid horizontal={false} stroke="var(--gridline)" />
          <XAxis
            type="number"
            domain={[0, "dataMax"]}
            tickFormatter={(v: number) => formatPercentValue(v * 100, 0)}
            stroke="var(--baseline)"
            tick={{ fill: "var(--text-secondary)", fontSize: 12 }}
          />
          <YAxis
            type="category"
            dataKey="label"
            width={110}
            stroke="var(--baseline)"
            tick={{ fill: "var(--text-secondary)", fontSize: 12 }}
          />
          <Tooltip content={<ExposureTooltip />} cursor={{ fill: "var(--diverging-mid)" }} />
          <Bar dataKey="weight" radius={4} barSize={20}>
            {data.map((entry, index) => (
              <Cell
                key={entry.label}
                fill={entry.label === "Other" ? OTHER_COLOR : SERIES_COLORS[index % SERIES_COLORS.length]}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
