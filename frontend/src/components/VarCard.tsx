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
import { formatPercent } from "../lib/format";

interface VarCardProps {
  varHistorical95: number;
  varParametric95: number;
  cvar95: number;
}

interface TooltipPayloadEntry {
  value: number;
}

function VarTooltip({
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
        {formatPercent(payload[0].value)}
      </div>
    </div>
  );
}

export function VarCard({ varHistorical95, varParametric95, cvar95 }: VarCardProps) {
  const data = [
    { method: "Historical VaR (95%)", value: varHistorical95 },
    { method: "Parametric VaR (95%)", value: varParametric95 },
    { method: "CVaR / Expected Shortfall", value: cvar95 },
  ];

  return (
    <div
      className="rounded-lg p-4"
      style={{ background: "var(--surface-1)", border: "1px solid var(--border)" }}
    >
      <div className="text-sm mb-1" style={{ color: "var(--text-secondary)" }}>
        Value at Risk — worst-case daily loss at 95% confidence
      </div>
      <div className="text-xs mb-3" style={{ color: "var(--text-muted)" }}>
        Historical and parametric methods shown side by side — disagreement between
        them is informative, not an error.
      </div>
      <ResponsiveContainer width="100%" height={140}>
        <BarChart data={data} layout="vertical" margin={{ left: 8, right: 24 }}>
          <CartesianGrid horizontal={false} stroke="var(--gridline)" />
          <XAxis
            type="number"
            tickFormatter={(v: number) => formatPercent(v, 1)}
            tickCount={5}
            stroke="var(--baseline)"
            tick={{ fill: "var(--text-secondary)", fontSize: 12 }}
          />
          <YAxis
            type="category"
            dataKey="method"
            width={150}
            stroke="var(--baseline)"
            tick={{ fill: "var(--text-secondary)", fontSize: 12 }}
          />
          <Tooltip content={<VarTooltip />} cursor={{ fill: "var(--diverging-mid)" }} />
          <Bar dataKey="value" radius={4} barSize={20}>
            {data.map((entry) => (
              <Cell key={entry.method} fill="var(--accent-blue)" />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
