import { useQuery } from "@tanstack/react-query";
import { getMacroDashboard } from "../api/client";
import type { MacroCategory, MacroSeriesOut } from "../api/client";
import { MacroStatCard } from "./MacroStatCard";
import { MacroYieldCurveChart } from "./MacroYieldCurveChart";

const CATEGORY_ORDER: MacroCategory[] = ["inflation", "rates", "debt", "growth"];
const CATEGORY_LABEL: Record<MacroCategory, string> = {
  inflation: "Inflation",
  rates: "Rates",
  debt: "Debt",
  growth: "Growth & labor",
};

function groupByCategory(series: MacroSeriesOut[]): Map<MacroCategory, MacroSeriesOut[]> {
  const grouped = new Map<MacroCategory, MacroSeriesOut[]>();
  for (const category of CATEGORY_ORDER) grouped.set(category, []);
  for (const s of series) grouped.get(s.category)?.push(s);
  return grouped;
}

export function MacroPanel() {
  // Ambient economic context, not a user-triggered portfolio computation —
  // auto-loads and refreshes on its own, unlike every other analytical
  // panel on this page (which use useMutation, fired by a button).
  const { data, isLoading, isError } = useQuery({
    queryKey: ["macroDashboard"],
    queryFn: getMacroDashboard,
    refetchInterval: 5 * 60_000,
  });

  if (isLoading) {
    return (
      <div className="text-sm" style={{ color: "var(--text-muted)" }}>
        Loading macro environment…
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="text-sm" style={{ color: "var(--status-critical)" }}>
        Couldn't load macro environment data.
      </div>
    );
  }

  const grouped = groupByCategory(data.series);

  return (
    <div className="space-y-4">
      <div className="text-sm font-medium" style={{ color: "var(--text-secondary)" }}>
        Macro environment
      </div>

      {CATEGORY_ORDER.map((category) => {
        const items = grouped.get(category) ?? [];
        if (items.length === 0) return null;
        return (
          <div key={category} className="space-y-2">
            <div className="text-xs" style={{ color: "var(--text-muted)" }}>
              {CATEGORY_LABEL[category]}
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {items.map((s) => (
                <MacroStatCard key={s.series_id} series={s} />
              ))}
            </div>
          </div>
        );
      })}

      <MacroYieldCurveChart points={data.yield_curve} />
    </div>
  );
}
