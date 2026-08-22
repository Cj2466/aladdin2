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

/** For a macro indicator's own level/rate (e.g. a Treasury yield or the
 * unemployment rate) — unlike formatPercentValue, no forced "+" sign,
 * since these are levels, not returns. A genuinely negative value (e.g. an
 * inverted yield curve spread) still shows its natural minus sign. */
export function formatMacroValue(
  value: number,
  unit: "percent" | "usd_trillions",
  digits: number,
): string {
  if (unit === "usd_trillions") return `$${value.toFixed(digits)}T`;
  return `${value.toFixed(digits)}%`;
}
