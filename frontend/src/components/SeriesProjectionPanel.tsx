import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  CartesianGrid,
  ComposedChart,
  ErrorBar,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getSeriesProjections } from "../api/client";
import type { SeriesProjectionOut } from "../api/client";
import { formatMacroValue } from "../lib/format";

interface ChartPoint {
  date: string;
  actual: number | null;
  projected: number | null;
  errorRange?: [number, number];
}

function buildChartData(projection: SeriesProjectionOut): ChartPoint[] {
  const points: ChartPoint[] = projection.recent_history.map((p) => ({
    date: p.date,
    actual: p.value,
    projected: null,
  }));
  if (points.length > 0 && projection.last_value !== null) {
    // Bridge point — same date as the last actual observation, but also
    // carries the projected series so the dashed line visually connects
    // to the solid history line instead of floating disconnected.
    points[points.length - 1].projected = projection.last_value;
  }
  if (projection.point_estimate !== null && projection.band_low !== null && projection.band_high !== null) {
    const errorLow = Math.max(0, projection.point_estimate - projection.band_low);
    const errorHigh = Math.max(0, projection.band_high - projection.point_estimate);
    points.push({
      date: `+${projection.horizon_trading_days}d`,
      actual: null,
      projected: projection.point_estimate,
      errorRange: [errorLow, errorHigh],
    });
  }
  return points;
}

function ProjectionTooltip({
  active,
  payload,
  label,
  unit,
  decimals,
}: {
  active?: boolean;
  payload?: { value: number; dataKey: string }[];
  label?: string;
  unit: "percent" | "usd_trillions";
  decimals: number;
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
        <div key={entry.dataKey} style={{ color: "var(--text-primary)" }}>
          {entry.dataKey === "projected" ? "Projected" : "Actual"}:{" "}
          {formatMacroValue(entry.value, unit, decimals)}
        </div>
      ))}
    </div>
  );
}

function ProjectionChart({ projection }: { projection: SeriesProjectionOut }) {
  if (projection.status !== "ok") {
    return (
      <div className="text-sm py-8 text-center" style={{ color: "var(--text-muted)" }}>
        Not enough history to project this series yet.
      </div>
    );
  }

  const data = buildChartData(projection);
  const isWeak = projection.trend_strength === "weak";
  const isOutside = projection.point_estimate_outside_historical_range === true;

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span
          className="px-1.5 py-0.5 rounded"
          style={{ background: "var(--page-plane)", border: "1px solid var(--border)", color: "var(--text-secondary)" }}
        >
          Trend: {projection.trend_strength ?? "—"}
        </span>
        <span
          className="px-1.5 py-0.5 rounded"
          style={{ background: "var(--page-plane)", border: "1px solid var(--border)", color: "var(--text-secondary)" }}
        >
          R² {projection.r_squared !== null ? projection.r_squared.toFixed(2) : "—"}
        </span>
        {isOutside && (
          <span
            className="px-1.5 py-0.5 rounded"
            style={{ background: "var(--page-plane)", border: `1px solid var(--status-critical)`, color: "var(--status-critical)" }}
          >
            Outside typical historical range
          </span>
        )}
      </div>

      <ResponsiveContainer width="100%" height={220}>
        <ComposedChart data={data} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="var(--gridline)" vertical={false} />
          <XAxis
            dataKey="date"
            stroke="var(--baseline)"
            tick={{ fill: "var(--text-secondary)", fontSize: 10 }}
            interval="preserveStartEnd"
          />
          <YAxis
            tickFormatter={(v: number) => formatMacroValue(v, projection.unit, 1)}
            stroke="var(--baseline)"
            tick={{ fill: "var(--text-secondary)", fontSize: 12 }}
            width={52}
            domain={["auto", "auto"]}
          />
          <Tooltip
            content={<ProjectionTooltip unit={projection.unit} decimals={projection.decimals} />}
            cursor={{ stroke: "var(--gridline)" }}
          />
          <Line
            type="monotone"
            dataKey="actual"
            stroke="var(--series-1)"
            strokeWidth={2}
            dot={false}
            connectNulls={false}
          />
          <Line
            type="monotone"
            dataKey="projected"
            stroke="var(--series-2)"
            strokeWidth={isWeak ? 1 : 2}
            strokeOpacity={isWeak ? 0.5 : 0.9}
            strokeDasharray="4 4"
            dot={{ r: 4 }}
            connectNulls
          >
            <ErrorBar dataKey="errorRange" width={6} strokeWidth={1.5} stroke="var(--series-2)" opacity={isWeak ? 0.5 : 0.9} />
          </Line>
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

export function SeriesProjectionPanel() {
  const [isExpanded, setIsExpanded] = useState(false);
  const [activeSeriesId, setActiveSeriesId] = useState<string | null>(null);

  // Never fetches, let alone renders a chart, until the user explicitly
  // opts in — a trending line reads as "this is where it's going" faster
  // than any caption gets read, so this must not appear by default.
  const { data, isLoading, isError } = useQuery({
    queryKey: ["seriesProjections"],
    queryFn: getSeriesProjections,
    enabled: isExpanded,
  });

  const activeProjection = data?.projections.find((p) => p.series_id === activeSeriesId) ?? data?.projections[0];

  return (
    <div>
      <button
        type="button"
        onClick={() => setIsExpanded((v) => !v)}
        className="text-sm"
        style={{ color: "var(--text-secondary)" }}
      >
        Statistical projections — methodology &amp; limitations {isExpanded ? "▾" : "▸"}
      </button>

      {isExpanded && (
        <div
          className="mt-3 rounded-lg p-4 space-y-3"
          style={{ background: "var(--surface-1)", border: "1px solid var(--border)" }}
        >
          <div
            className="rounded-md p-3 text-xs"
            style={{
              background: "var(--page-plane)",
              border: `1px solid var(--status-warning)`,
              color: "var(--text-secondary)",
            }}
          >
            ⚠ {data?.methodology_note ??
              "These are naive statistical projections, not forecasts, and should not be relied on to make decisions."}
          </div>

          {isLoading && (
            <div className="text-sm" style={{ color: "var(--text-muted)" }}>
              Loading projections…
            </div>
          )}

          {isError && (
            <div className="text-sm" style={{ color: "var(--status-critical)" }}>
              Couldn't load projections.
            </div>
          )}

          {data && (
            <>
              <div className="flex flex-wrap gap-1.5">
                {data.projections.map((p) => (
                  <button
                    key={p.series_id}
                    type="button"
                    onClick={() => setActiveSeriesId(p.series_id)}
                    className="text-xs px-2 py-1 rounded-md"
                    style={{
                      background:
                        (activeProjection?.series_id ?? data.projections[0]?.series_id) === p.series_id
                          ? "var(--accent-blue)"
                          : "var(--page-plane)",
                      color:
                        (activeProjection?.series_id ?? data.projections[0]?.series_id) === p.series_id
                          ? "white"
                          : "var(--text-secondary)",
                      border: "1px solid var(--border)",
                    }}
                  >
                    {p.label}
                  </button>
                ))}
              </div>

              {activeProjection && <ProjectionChart projection={activeProjection} />}
            </>
          )}
        </div>
      )}
    </div>
  );
}
