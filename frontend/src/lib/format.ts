export function formatPercent(value: number, digits = 2): string {
  return `${(value * 100).toFixed(digits)}%`;
}

/** For values already expressed in percent units (e.g. Finnhub's `dp`),
 * as opposed to formatPercent's 0-1 fraction input. Mixing these up
 * silently produces a 100x-wrong display. */
export function formatPercentValue(value: number, digits = 2): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}%`;
}
