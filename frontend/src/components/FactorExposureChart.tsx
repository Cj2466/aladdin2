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
import type { FactorExposureOut } from "../api/client";

interface FactorExposureChartProps {
  exposures: FactorExposureOut[];
}

interface TooltipPayloadEntry {
  value: number;
}

function ExposureTooltip({
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
        {payload[0].value.toFixed(2)}
      </div>
    </div>
  );
}

export function FactorExposureChart({ exposures }: FactorExposureChartProps) {
  const data = exposures.map((f) => ({ label: f.label, exposure: f.exposure }));
  const height = Math.max(80, data.length * 36);

  return (
    <div
      className="rounded-lg p-4"
      style={{ background: "var(--surface-1)", border: "1px solid var(--border)" }}
    >
      <div className="text-sm mb-3" style={{ color: "var(--text-secondary)" }}>
        Net factor exposure (beta)
      </div>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} layout="vertical" margin={{ left: 8, right: 24 }}>
          <CartesianGrid horizontal={false} stroke="var(--gridline)" />
          <XAxis
            type="number"
            tickFormatter={(v: number) => v.toFixed(2)}
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
          <Bar dataKey="exposure" radius={4} barSize={20}>
            {data.map((entry) => (
              <Cell key={entry.label} fill="var(--accent-blue)" />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
