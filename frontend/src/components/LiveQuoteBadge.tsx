import { useEffect, useState } from "react";
import type { ConnectionState, LiveQuote } from "../hooks/useLiveQuotes";
import { formatPercentValue } from "../lib/format";

const STALE_AFTER_MS = 2 * 60 * 1000;
const RECHECK_INTERVAL_MS = 30_000;

interface LiveQuoteBadgeProps {
  quote: LiveQuote | undefined;
  connectionState: ConnectionState;
}

export function LiveQuoteBadge({ quote, connectionState }: LiveQuoteBadgeProps) {
  // No new message ever arriving (market closed, illiquid ticker) shouldn't
  // look identical to "still live" — a periodic re-check of the clock makes
  // staleness visible without depending on the next tick that may never come.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const interval = setInterval(() => setNow(Date.now()), RECHECK_INTERVAL_MS);
    return () => clearInterval(interval);
  }, []);

  if (connectionState === "unavailable") {
    return null; // no server-side live-quotes config — don't show a badge that never resolves
  }

  if (!quote || quote.status === "pending") {
    return (
      <span className="text-xs" style={{ color: "var(--text-muted)" }}>
        …
      </span>
    );
  }

  if (quote.status === "invalid") {
    return (
      <span className="text-xs" style={{ color: "var(--text-muted)" }}>
        unknown ticker
      </span>
    );
  }

  const isStale = now - quote.lastUpdated > STALE_AFTER_MS;
  if (isStale) {
    return (
      <span className="text-xs" style={{ color: "var(--text-muted)" }}>
        no live updates
      </span>
    );
  }

  const color =
    quote.changePercent > 0
      ? "var(--status-good)"
      : quote.changePercent < 0
        ? "var(--status-critical)"
        : "var(--text-muted)";

  return (
    <span className="text-xs flex items-center gap-1.5">
      <span style={{ color: "var(--text-secondary)" }}>${quote.price.toFixed(2)}</span>
      <span style={{ color }}>{formatPercentValue(quote.changePercent)}</span>
    </span>
  );
}
