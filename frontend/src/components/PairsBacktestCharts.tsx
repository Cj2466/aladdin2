import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { PairsBacktestResponse } from "../api/client";

export function EquityCurveChart({ result }: { result: PairsBacktestResponse }) {
  return (
    <ResponsiveContainer width="100%" height={180}>
      <LineChart data={result.equity_curve} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid stroke="var(--gridline)" vertical={false} />
        <XAxis
          dataKey="date"
          stroke="var(--baseline)"
          tick={{ fill: "var(--text-secondary)", fontSize: 10 }}
          interval="preserveStartEnd"
        />
        <YAxis
          tickFormatter={(v: number) => v.toFixed(2)}
          stroke="var(--baseline)"
          tick={{ fill: "var(--text-secondary)", fontSize: 12 }}
          width={44}
          domain={["auto", "auto"]}
        />
        <Tooltip
          contentStyle={{ background: "var(--surface-1)", border: "1px solid var(--border)" }}
          labelStyle={{ color: "var(--text-secondary)" }}
          formatter={(v: unknown) => (typeof v === "number" ? v.toFixed(4) : String(v))}
        />
        <ReferenceLine y={1.0} stroke="var(--baseline)" strokeDasharray="3 3" />
        <Line type="monotone" dataKey="equity" stroke="var(--series-1)" strokeWidth={2} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

export function ZScoreChart({ result }: { result: PairsBacktestResponse }) {
  return (
    <ResponsiveContainer width="100%" height={140}>
      <LineChart data={result.equity_curve} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid stroke="var(--gridline)" vertical={false} />
        <XAxis
          dataKey="date"
          stroke="var(--baseline)"
          tick={{ fill: "var(--text-secondary)", fontSize: 10 }}
          interval="preserveStartEnd"
        />
        <YAxis
          stroke="var(--baseline)"
          tick={{ fill: "var(--text-secondary)", fontSize: 12 }}
          width={30}
          domain={["auto", "auto"]}
        />
        <Tooltip
          contentStyle={{ background: "var(--surface-1)", border: "1px solid var(--border)" }}
          labelStyle={{ color: "var(--text-secondary)" }}
          formatter={(v: unknown) => (typeof v === "number" ? v.toFixed(2) : "—")}
        />
        <ReferenceLine y={0} stroke="var(--baseline)" />
        <ReferenceLine y={result.entry_z} stroke="var(--status-warning)" strokeDasharray="3 3" />
        <ReferenceLine y={-result.entry_z} stroke="var(--status-warning)" strokeDasharray="3 3" />
        <Line
          type="monotone"
          dataKey="z_score"
          stroke="var(--series-2)"
          strokeWidth={1.5}
          dot={false}
          connectNulls={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
