import { StatTile } from "./StatTile";

interface DiversificationCardProps {
  hhi: number;
  avgPairwiseCorrelation: number;
}

export function DiversificationCard({ hhi, avgPairwiseCorrelation }: DiversificationCardProps) {
  return (
    <div className="grid grid-cols-2 gap-3">
      <StatTile
        label="Concentration (HHI)"
        value={hhi.toFixed(3)}
        sublabel="Weight concentration only — 1.0 = single holding, lower = more spread out"
      />
      <StatTile
        label="Avg. pairwise correlation"
        value={avgPairwiseCorrelation.toFixed(2)}
        sublabel="Low HHI with high correlation still isn't diversified"
      />
    </div>
  );
}
