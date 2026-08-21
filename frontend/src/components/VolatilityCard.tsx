import { StatTile } from "./StatTile";
import { formatPercent } from "../lib/format";

interface VolatilityCardProps {
  volatilityAnnualized: number;
  beta: number;
}

export function VolatilityCard({ volatilityAnnualized, beta }: VolatilityCardProps) {
  return (
    <div className="grid grid-cols-2 gap-3">
      <StatTile
        label="Annualized volatility"
        value={formatPercent(volatilityAnnualized)}
        sublabel="Std. dev. of daily returns, scaled to a year"
      />
      <StatTile
        label="Beta vs. benchmark"
        value={beta.toFixed(2)}
        sublabel={beta > 1 ? "More volatile than benchmark" : "Less volatile than benchmark"}
      />
    </div>
  );
}
