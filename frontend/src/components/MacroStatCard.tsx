import type { ReactNode } from "react";
import type { MacroSeriesOut } from "../api/client";
import { formatMacroValue } from "../lib/format";

interface MacroStatCardProps {
  series: MacroSeriesOut;
}

function minutesAgo(iso: string): number {
  return Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60_000));
}

function Badge({ children, color }: { children: ReactNode; color: string }) {
  return (
    <span
      className="inline-block mt-1.5 px-1.5 py-0.5 rounded text-[11px]"
      style={{ background: "var(--page-plane)", border: "1px solid var(--border)", color }}
    >
      {children}
    </span>
  );
}

export function MacroStatCard({ series }: MacroStatCardProps) {
  return (
    <div
      className="rounded-lg p-4"
      style={{ background: "var(--surface-1)", border: "1px solid var(--border)" }}
    >
      <div className="text-sm" style={{ color: "var(--text-secondary)" }}>
        {series.label}
      </div>

      {series.status === "unavailable" || series.value === null ? (
        <>
          <div className="mt-1 text-2xl font-semibold" style={{ color: "var(--text-muted)" }}>
            —
          </div>
          <Badge color="var(--text-muted)">Data unavailable</Badge>
        </>
      ) : (
        <>
          <div className="mt-1 text-2xl font-semibold" style={{ color: "var(--text-primary)" }}>
            {formatMacroValue(series.value, series.unit, series.decimals)}
          </div>
          {series.cadence === "daily" && series.fetched_at ? (
            <Badge color="var(--status-good)">Live · updated {minutesAgo(series.fetched_at)}m ago</Badge>
          ) : (
            <Badge color="var(--text-muted)">
              {series.reference_period_label ? `As of ${series.reference_period_label}` : "As of —"}
            </Badge>
          )}
        </>
      )}
    </div>
  );
}
