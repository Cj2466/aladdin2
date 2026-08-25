import { BacktestPanel } from "../components/BacktestPanel";
import { ExecutionPanel } from "../components/ExecutionPanel";
import { ForwardValidationPanel } from "../components/ForwardValidationPanel";
import { LeaderboardTable } from "../components/LeaderboardTable";
import { MomentumBacktestPanel } from "../components/MomentumBacktestPanel";
import { MomentumSweepPanel } from "../components/MomentumSweepPanel";
import { ScreeningPanel } from "../components/ScreeningPanel";
import { StrategyPortfolioPanel } from "../components/StrategyPortfolioPanel";
import { SweepPanel } from "../components/SweepPanel";

interface ResearchLabPageProps {
  onBack: () => void;
}

export function ResearchLabPage({ onBack }: ResearchLabPageProps) {
  return (
    <div className="min-h-screen mx-auto max-w-4xl px-4 py-8 space-y-6">
      <header>
        <button
          type="button"
          onClick={onBack}
          className="text-sm mb-3"
          style={{ color: "var(--text-secondary)" }}
        >
          ← Back to dashboard
        </button>
        <h1 className="text-2xl font-semibold" style={{ color: "var(--text-primary)" }}>
          Research Lab
        </h1>
        <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
          Backtest a pair, sweep a grid of parameters, and see every result — cached and swept
          alike — in one leaderboard. Research tooling, not a trading signal.
        </p>
      </header>

      <ScreeningPanel />

      <BacktestPanel />

      <MomentumBacktestPanel />

      <SweepPanel />

      <MomentumSweepPanel />

      <div className="space-y-3">
        <div className="text-sm font-medium" style={{ color: "var(--text-secondary)" }}>
          Leaderboard — every backtested configuration
        </div>
        <LeaderboardTable />
      </div>

      <StrategyPortfolioPanel />

      <ForwardValidationPanel />

      <ExecutionPanel />
    </div>
  );
}
