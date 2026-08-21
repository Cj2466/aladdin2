interface StatTileProps {
  label: string;
  value: string;
  sublabel?: string;
}

export function StatTile({ label, value, sublabel }: StatTileProps) {
  return (
    <div
      className="rounded-lg p-4"
      style={{ background: "var(--surface-1)", border: "1px solid var(--border)" }}
    >
      <div className="text-sm" style={{ color: "var(--text-secondary)" }}>
        {label}
      </div>
      <div className="mt-1 text-2xl font-semibold" style={{ color: "var(--text-primary)" }}>
        {value}
      </div>
      {sublabel && (
        <div className="mt-1 text-xs" style={{ color: "var(--text-muted)" }}>
          {sublabel}
        </div>
      )}
    </div>
  );
}
