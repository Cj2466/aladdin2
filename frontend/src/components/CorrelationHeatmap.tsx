import { Fragment, useEffect, useState } from "react";

interface CorrelationHeatmapProps {
  matrix: Record<string, Record<string, number>>;
}

const LIGHT = { blue: "#2a78d6", red: "#e34948", mid: "#f0efec" };
const DARK = { blue: "#3987e5", red: "#e66767", mid: "#383835" };

function hexToRgb(hex: string): [number, number, number] {
  const clean = hex.replace("#", "");
  return [
    parseInt(clean.slice(0, 2), 16),
    parseInt(clean.slice(2, 4), 16),
    parseInt(clean.slice(4, 6), 16),
  ];
}

function lerp(a: number, b: number, t: number): number {
  return Math.round(a + (b - a) * t);
}

function blend(hexA: string, hexB: string, t: number): [number, number, number] {
  const [r1, g1, b1] = hexToRgb(hexA);
  const [r2, g2, b2] = hexToRgb(hexB);
  return [lerp(r1, r2, t), lerp(g1, g2, t), lerp(b1, b2, t)];
}

function usePrefersDark(): boolean {
  const [prefersDark, setPrefersDark] = useState(
    () => window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false,
  );
  useEffect(() => {
    const mql = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = (e: MediaQueryListEvent) => setPrefersDark(e.matches);
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, []);
  return prefersDark;
}

function divergingRgb(value: number, isDark: boolean): [number, number, number] {
  const palette = isDark ? DARK : LIGHT;
  const clamped = Math.max(-1, Math.min(1, value));
  return clamped >= 0
    ? blend(palette.mid, palette.blue, clamped)
    : blend(palette.mid, palette.red, -clamped);
}

function contrastTextColor([r, g, b]: [number, number, number]): string {
  const luminance = 0.299 * r + 0.587 * g + 0.114 * b;
  return luminance < 150 ? "#ffffff" : "var(--text-primary)";
}

export function CorrelationHeatmap({ matrix }: CorrelationHeatmapProps) {
  const tickers = Object.keys(matrix);
  const isDark = usePrefersDark();
  const [hovered, setHovered] = useState<{ row: string; col: string; value: number } | null>(
    null,
  );

  return (
    <div
      className="rounded-lg p-4"
      style={{ background: "var(--surface-1)", border: "1px solid var(--border)" }}
    >
      <div className="text-sm mb-3" style={{ color: "var(--text-secondary)" }}>
        Correlation matrix
      </div>
      <div className="overflow-x-auto">
        <div
          className="inline-grid gap-0.5"
          style={{ gridTemplateColumns: `auto repeat(${tickers.length}, 44px)` }}
        >
          <div />
          {tickers.map((col) => (
            <div
              key={col}
              className="text-xs text-center pb-1 font-medium"
              style={{ color: "var(--text-secondary)" }}
            >
              {col}
            </div>
          ))}
          {tickers.map((row) => (
            <Fragment key={row}>
              <div
                className="text-xs pr-2 flex items-center font-medium"
                style={{ color: "var(--text-secondary)" }}
              >
                {row}
              </div>
              {tickers.map((col) => {
                const value = matrix[row][col];
                const rgb = divergingRgb(value, isDark);
                return (
                  <div
                    key={`${row}-${col}`}
                    tabIndex={0}
                    role="gridcell"
                    aria-label={`${row} vs ${col}: ${value.toFixed(2)}`}
                    onMouseEnter={() => setHovered({ row, col, value })}
                    onMouseLeave={() => setHovered(null)}
                    onFocus={() => setHovered({ row, col, value })}
                    onBlur={() => setHovered(null)}
                    className="h-11 flex items-center justify-center text-xs font-medium rounded-sm cursor-default outline-none focus-visible:ring-2"
                    style={{
                      background: `rgb(${rgb.join(",")})`,
                      color: contrastTextColor(rgb),
                    }}
                  >
                    {value.toFixed(2)}
                  </div>
                );
              })}
            </Fragment>
          ))}
        </div>
      </div>
      <div className="mt-3 text-xs h-4" style={{ color: "var(--text-muted)" }}>
        {hovered
          ? `${hovered.row} × ${hovered.col}: ${hovered.value.toFixed(3)}`
          : "Hover or focus a cell to see the exact pairwise correlation."}
      </div>
    </div>
  );
}
