import { useQuery } from "@tanstack/react-query";
import { getHistoricalAnalog } from "../api/client";
import type { EpisodeOutcomeOut, ReturnStatus } from "../api/client";
import { formatPercentValue } from "../lib/format";

interface HistoricalAnalogTableProps {
  seriesId: string;
  benchmark: string;
}

function formatReturn(value: number | null, status: ReturnStatus): string {
  if (status === "too_recent") return "N/A (too recent)";
  if (status === "benchmark_unavailable") return "N/A (benchmark not yet listed)";
  return value !== null ? formatPercentValue(value * 100) : "—";
}

function returnColor(value: number | null, status: ReturnStatus): string {
  if (status !== "ok" || value === null) return "var(--text-muted)";
  if (value > 0) return "var(--status-good)";
  if (value < 0) return "var(--status-critical)";
  return "var(--text-muted)";
}

export function HistoricalAnalogTable({ seriesId, benchmark }: HistoricalAnalogTableProps) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["historicalAnalog", seriesId, benchmark],
    queryFn: () => getHistoricalAnalog(seriesId, benchmark),
  });

  if (isLoading) {
    return (
      <div className="text-sm" style={{ color: "var(--text-muted)" }}>
        Loading historical episodes…
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="text-sm" style={{ color: "var(--status-critical)" }}>
        Couldn't load historical episode data.
      </div>
    );
  }

  return (
    <div
      className="rounded-lg p-4"
      style={{ background: "var(--surface-1)", border: "1px solid var(--border)" }}
    >
      <div className="text-sm mb-2" style={{ color: "var(--text-secondary)" }}>
        {data.series_label} — historical episodes vs. {data.benchmark}
      </div>

      <div
        className="rounded-md p-3 mb-3 text-xs"
        style={{
          background: "var(--page-plane)",
          border: `1px solid var(--status-warning)`,
          color: "var(--text-secondary)",
        }}
      >
        ⚠ {data.caveat}
      </div>

      {data.episodes.length === 0 ? (
        <div className="text-sm" style={{ color: "var(--text-muted)" }}>
          No historical episodes found since {data.history_start}.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs" style={{ borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ color: "var(--text-muted)" }}>
                <th className="text-left py-1.5 pr-3">Episode start</th>
                <th className="text-left py-1.5 pr-3">Episode end</th>
                <th className="text-right py-1.5 px-2">6mo</th>
                <th className="text-right py-1.5 px-2">12mo</th>
                <th className="text-right py-1.5 pl-2">18mo</th>
              </tr>
            </thead>
            <tbody>
              {data.episodes.map((episode: EpisodeOutcomeOut) => (
                <tr key={episode.episode_start} style={{ borderTop: "1px solid var(--border)" }}>
                  <td className="py-1.5 pr-3" style={{ color: "var(--text-primary)" }}>
                    {episode.episode_start}
                  </td>
                  <td className="py-1.5 pr-3" style={{ color: "var(--text-secondary)" }}>
                    {episode.episode_end}
                  </td>
                  <td
                    className="text-right py-1.5 px-2"
                    style={{ color: returnColor(episode.return_6m, episode.return_6m_status) }}
                  >
                    {formatReturn(episode.return_6m, episode.return_6m_status)}
                  </td>
                  <td
                    className="text-right py-1.5 px-2"
                    style={{ color: returnColor(episode.return_12m, episode.return_12m_status) }}
                  >
                    {formatReturn(episode.return_12m, episode.return_12m_status)}
                  </td>
                  <td
                    className="text-right py-1.5 pl-2"
                    style={{ color: returnColor(episode.return_18m, episode.return_18m_status) }}
                  >
                    {formatReturn(episode.return_18m, episode.return_18m_status)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
