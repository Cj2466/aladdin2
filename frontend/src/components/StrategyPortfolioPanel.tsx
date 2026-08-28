import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { isAxiosError } from "axios";
import {
  analyzeStrategyPortfolio,
  createStrategyPortfolio,
  deleteStrategyPortfolio,
  getStrategyPortfolio,
  listExperimentRuns,
  listStrategyPortfolios,
  optimizeStrategyPortfolio,
  setStrategyPortfolioLive,
  updateStrategyPortfolio,
} from "../api/client";
import type {
  ApiErrorBody,
  ExperimentRunSummaryOut,
  PortfolioAnalyzeResponse,
  PortfolioOptimizeResponse,
  StrategyAllocationIn,
} from "../api/client";
import { CorrelationHeatmap } from "./CorrelationHeatmap";
import { DiversificationCard } from "./DiversificationCard";
import { formatSharpe, isMomentum, tickerLabel } from "./LeaderboardTable";
import { OptimizerPanel } from "./OptimizerPanel";
import { VarCard } from "./VarCard";
import { VolatilityCard } from "./VolatilityCard";

const CANDIDATE_PAGE_SIZE = 40;

// Human labels for StrategyPortfolio.last_optimization_method. The backend
// writes exactly these three values (config.py's OPTIMIZATION_METHODS plus
// the autonomous runner's "equal_weight" fallback), and null for anything
// never auto-reweighted. An unrecognized value is shown VERBATIM rather
// than hidden or relabelled: a badge that silently dropped a method the UI
// doesn't know about would recreate exactly the "you can't tell what
// produced these weights" problem the column exists to solve.
const OPTIMIZATION_METHOD_LABELS: Record<string, string> = {
  mean_variance: "Mean-variance",
  hrp: "HRP",
  equal_weight: "Equal weight (fallback)",
};

const METHODOLOGY_NOTE =
  "Combines already-backtested strategy instances into one portfolio and measures it with the same " +
  "risk engine the ticker-level portfolio tools use — the assets are strategy P&L series instead of " +
  "prices, the math is identical. Return series are inner-joined on date, so every number below is " +
  "computed only over days where every selected strategy actually has a realized return; a " +
  "forward-filled join would misrepresent exactly the tail co-movement this view exists to measure. " +
  "Each strategy's Sharpe is its own historical backtest result, uncorrected here for the search that " +
  "produced it — see each run's deflated Sharpe on the leaderboard before trusting it.";

const inputStyle = {
  background: "var(--page-plane)",
  border: "1px solid var(--border)",
  color: "var(--text-primary)",
};

function runLabel(run: { strategy_name: string; ticker_a: string; ticker_b: string }): string {
  return tickerLabel(run.strategy_name, run.ticker_a, run.ticker_b);
}

function errorMessage(error: unknown, fallback: string): string {
  if (isAxiosError<ApiErrorBody>(error)) return error.response?.data?.detail ?? fallback;
  return fallback;
}

/** Equal-weight over the given ids, with any rounding remainder absorbed by
 * the first one so the total lands on exactly 1.0 — the backend's validator
 * only accepts 0.995-1.005, and a naive round() on e.g. 3 or 7 members
 * drifts outside that. */
function equalWeights(runIds: number[]): Map<number, number> {
  const next = new Map<number, number>();
  if (runIds.length === 0) return next;
  const each = Math.round((1 / runIds.length) * 10000) / 10000;
  runIds.forEach((id) => next.set(id, each));
  next.set(runIds[0], Math.round((1 - each * (runIds.length - 1)) * 10000) / 10000);
  return next;
}

function CandidateRow({
  run,
  selected,
  weight,
  onToggle,
  onWeightChange,
}: {
  run: ExperimentRunSummaryOut;
  selected: boolean;
  weight: number | undefined;
  onToggle: () => void;
  onWeightChange: (value: number) => void;
}) {
  return (
    <tr style={{ borderTop: "1px solid var(--border)" }}>
      <td className="py-1.5 pr-2">
        <input type="checkbox" checked={selected} onChange={onToggle} aria-label={`Select run ${run.id}`} />
      </td>
      <td className="py-1.5 pr-3" style={{ color: "var(--text-primary)" }}>
        {runLabel(run)}
      </td>
      <td className="py-1.5 pr-3" style={{ color: "var(--text-muted)" }}>
        {isMomentum(run.strategy_name) ? "momentum" : "pairs"}
      </td>
      <td className="text-right py-1.5 pr-3" style={{ color: "var(--text-primary)" }}>
        {formatSharpe(run.sharpe_net)}
      </td>
      <td className="text-right py-1.5 pr-3" style={{ color: "var(--text-secondary)" }}>
        {run.num_trades}
      </td>
      <td className="py-1.5 pr-3" style={{ color: "var(--text-muted)" }}>
        fit {run.fit_window_days}d · z {run.entry_z}/{run.exit_z}
      </td>
      <td className="py-1.5 pr-3" style={{ color: "var(--text-muted)" }}>
        {run.computed_at.slice(0, 10)}
      </td>
      <td className="text-right py-1.5">
        {selected && (
          <input
            type="number"
            min={0}
            max={1}
            step={0.01}
            value={weight ?? 0}
            onChange={(e) => onWeightChange(Number(e.target.value))}
            className="w-20 text-xs px-1.5 py-1 rounded-md text-right"
            style={inputStyle}
            aria-label={`Weight for run ${run.id}`}
          />
        )}
      </td>
    </tr>
  );
}

export function StrategyPortfolioPanel() {
  const queryClient = useQueryClient();
  const [weights, setWeights] = useState<Map<number, number>>(new Map());
  const [draftName, setDraftName] = useState("");
  const [activeId, setActiveId] = useState<number | null>(null);
  const [analysis, setAnalysis] = useState<PortfolioAnalyzeResponse | null>(null);
  const [optimization, setOptimization] = useState<PortfolioOptimizeResponse | null>(null);

  const { data: candidates, isLoading: candidatesLoading } = useQuery({
    queryKey: ["strategyPortfolioCandidates"],
    queryFn: () =>
      listExperimentRuns({
        status: "ok",
        sort_by: "computed_at",
        sort_dir: "desc",
        limit: CANDIDATE_PAGE_SIZE,
      }),
  });

  const { data: portfolios } = useQuery({
    queryKey: ["strategyPortfolios"],
    queryFn: listStrategyPortfolios,
  });

  const runs = useMemo(() => candidates?.results ?? [], [candidates]);
  const selectedIds = useMemo(() => [...weights.keys()], [weights]);
  const allocations: StrategyAllocationIn[] = useMemo(
    () => selectedIds.map((id) => ({ experiment_run_id: id, weight: weights.get(id) ?? 0 })),
    [selectedIds, weights],
  );

  /** run-id -> human label, for anything that displays an opaque backend
   * key (the correlation heatmap's axes, the optimizer's bar chart).
   * Includes both the candidate list and any run only reachable through a
   * loaded portfolio, so a saved portfolio referencing an older run still
   * labels correctly. */
  const [extraLabels, setExtraLabels] = useState<Map<number, string>>(new Map());
  const labelFor = useMemo(() => {
    const byId = new Map<number, string>(extraLabels);
    runs.forEach((run) => byId.set(run.id, runLabel(run)));
    return (key: string) => byId.get(Number(key)) ?? `run #${key}`;
  }, [runs, extraLabels]);

  function toggle(runId: number) {
    const nextIds = weights.has(runId)
      ? selectedIds.filter((id) => id !== runId)
      : [...selectedIds, runId];
    // Redistribute equally on every selection change — the user can then
    // hand-edit individual weights, or apply the optimizer's.
    setWeights(equalWeights(nextIds));
    setAnalysis(null);
    setOptimization(null);
  }

  function setWeight(runId: number, value: number) {
    const next = new Map(weights);
    next.set(runId, value);
    setWeights(next);
  }

  const weightTotal = allocations.reduce((sum, a) => sum + a.weight, 0);
  const weightsValid = allocations.length > 0 && weightTotal >= 0.995 && weightTotal <= 1.005;

  const analyzeMutation = useMutation({
    mutationFn: () => analyzeStrategyPortfolio(allocations),
    onSuccess: setAnalysis,
  });

  const optimizeMutation = useMutation({
    mutationFn: () => optimizeStrategyPortfolio(allocations),
    onSuccess: setOptimization,
  });

  const saveMutation = useMutation({
    mutationFn: () =>
      createStrategyPortfolio({
        name: draftName || "Untitled strategy portfolio",
        allocations,
      }),
    onSuccess: (portfolio) => {
      queryClient.invalidateQueries({ queryKey: ["strategyPortfolios"] });
      setActiveId(portfolio.id);
      setDraftName(portfolio.name);
    },
  });

  const updateMutation = useMutation({
    mutationFn: () => {
      if (activeId === null) throw new Error("No active strategy portfolio");
      return updateStrategyPortfolio(activeId, { name: draftName, allocations });
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["strategyPortfolios"] }),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteStrategyPortfolio(id),
    onSuccess: (_data, id) => {
      queryClient.invalidateQueries({ queryKey: ["strategyPortfolios"] });
      if (activeId === id) {
        setActiveId(null);
        setWeights(new Map());
      }
    },
  });

  const setLiveMutation = useMutation({
    mutationFn: ({ id, isLive }: { id: number; isLive: boolean }) =>
      setStrategyPortfolioLive(id, isLive),
    // The backend clears every other portfolio's is_live in the same
    // transaction, so the whole list has to be refetched, not just this row.
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["strategyPortfolios"] }),
  });

  async function handleLoad(id: number) {
    const portfolio = await getStrategyPortfolio(id);
    const next = new Map<number, number>();
    const labels = new Map<number, string>();
    portfolio.allocations.forEach((a) => {
      next.set(a.experiment_run_id, a.weight);
      labels.set(a.experiment_run_id, runLabel(a));
    });
    setWeights(next);
    setExtraLabels(labels);
    setDraftName(portfolio.name);
    // A system portfolio is read-only server-side (PUT/DELETE stay strict
    // ownership), so loading one gives you its allocations to work from
    // without making it the update target.
    setActiveId(portfolio.is_system ? null : id);
    setAnalysis(null);
    setOptimization(null);
  }

  const heatmapMatrix = useMemo(() => {
    if (!analysis) return null;
    const remapped: Record<string, Record<string, number>> = {};
    Object.entries(analysis.correlation_matrix).forEach(([rowKey, row]) => {
      const mappedRow: Record<string, number> = {};
      Object.entries(row).forEach(([colKey, value]) => {
        mappedRow[labelFor(colKey)] = value;
      });
      remapped[labelFor(rowKey)] = mappedRow;
    });
    return remapped;
  }, [analysis, labelFor]);

  return (
    <div
      className="rounded-lg p-4 space-y-4"
      style={{ background: "var(--surface-1)", border: "1px solid var(--border)" }}
    >
      <div>
        <div className="text-sm font-medium" style={{ color: "var(--text-secondary)" }}>
          Strategy portfolio — combine backtested strategies
        </div>
        <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
          {METHODOLOGY_NOTE}
        </p>
      </div>

      {candidatesLoading && (
        <div className="text-sm" style={{ color: "var(--text-muted)" }}>
          Loading…
        </div>
      )}

      {!candidatesLoading && runs.length === 0 && (
        <div className="text-sm" style={{ color: "var(--text-muted)" }}>
          No successful backtests to combine yet — run one from the panels above.
        </div>
      )}

      {runs.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs" style={{ borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ color: "var(--text-muted)" }}>
                <th className="text-left py-1.5 pr-2" />
                <th className="text-left py-1.5 pr-3">Ticker</th>
                <th className="text-left py-1.5 pr-3">Strategy</th>
                <th className="text-right py-1.5 pr-3">Sharpe (net)</th>
                <th className="text-right py-1.5 pr-3">Trades</th>
                <th className="text-left py-1.5 pr-3">Config</th>
                <th className="text-left py-1.5 pr-3">Computed</th>
                <th className="text-right py-1.5">Weight</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <CandidateRow
                  key={run.id}
                  run={run}
                  selected={weights.has(run.id)}
                  weight={weights.get(run.id)}
                  onToggle={() => toggle(run.id)}
                  onWeightChange={(value) => setWeight(run.id, value)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {allocations.length > 0 && (
        <div
          className="text-xs"
          style={{ color: weightsValid ? "var(--text-muted)" : "var(--status-warning)" }}
        >
          {allocations.length} selected · weights total {weightTotal.toFixed(4)}
          {weightsValid ? "" : " — must sum to 1.0000 before analyzing"}
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => analyzeMutation.mutate()}
          disabled={!weightsValid || analyzeMutation.isPending}
          className="text-sm px-3 py-1.5 rounded-md text-white disabled:opacity-50"
          style={{ background: "var(--accent-blue)" }}
        >
          {analyzeMutation.isPending ? "Analyzing…" : "Analyze portfolio"}
        </button>
        <input
          type="text"
          value={draftName}
          onChange={(e) => setDraftName(e.target.value)}
          placeholder="Portfolio name"
          className="flex-1 min-w-40 rounded-md px-2 py-1.5 text-sm"
          style={inputStyle}
        />
        {activeId === null ? (
          <button
            type="button"
            onClick={() => saveMutation.mutate()}
            disabled={!weightsValid || saveMutation.isPending}
            className="text-sm px-3 py-1.5 rounded-md disabled:opacity-50"
            style={{ border: "1px solid var(--border)", color: "var(--text-secondary)" }}
          >
            {saveMutation.isPending ? "Saving…" : "Save as new"}
          </button>
        ) : (
          <>
            <button
              type="button"
              onClick={() => updateMutation.mutate()}
              disabled={!weightsValid || updateMutation.isPending}
              className="text-sm px-3 py-1.5 rounded-md disabled:opacity-50"
              style={{ border: "1px solid var(--border)", color: "var(--text-secondary)" }}
            >
              {updateMutation.isPending ? "Saving…" : "Update"}
            </button>
            <button
              type="button"
              onClick={() => {
                setActiveId(null);
                setDraftName("");
              }}
              className="text-sm px-3 py-1.5 rounded-md"
              style={{ border: "1px solid var(--border)", color: "var(--text-secondary)" }}
            >
              New
            </button>
          </>
        )}
      </div>

      {analyzeMutation.isError && (
        <div className="text-sm" style={{ color: "var(--status-critical)" }}>
          {errorMessage(analyzeMutation.error, "Couldn't analyze this strategy portfolio.")}
        </div>
      )}

      {portfolios && portfolios.length > 0 && (
        <div className="space-y-1">
          <div className="text-xs" style={{ color: "var(--text-muted)" }}>
            Saved strategy portfolios
          </div>
          {portfolios.map((p) => (
            <div key={p.id} className="flex items-center gap-2 text-sm">
              <span
                className="flex-1"
                style={{ color: activeId === p.id ? "var(--accent-blue)" : "var(--text-primary)" }}
              >
                {p.name}
              </span>
              {p.is_system && (
                <span
                  className="text-xs px-1.5 py-0.5 rounded"
                  style={{
                    background: "var(--page-plane)",
                    border: "1px solid var(--border)",
                    color: "var(--text-muted)",
                  }}
                >
                  Automatic daily run
                </span>
              )}
              {/* Which allocator actually wrote the stored weights. Absent
                  until something auto-reweights the portfolio, so a
                  user-built one shows no badge rather than a guess. */}
              {p.last_optimization_method && (
                <span
                  className="text-xs px-1.5 py-0.5 rounded"
                  title="The optimizer that produced this portfolio's current weights"
                  style={{
                    background: "var(--page-plane)",
                    border: "1px solid var(--border)",
                    color: "var(--text-muted)",
                  }}
                >
                  {OPTIMIZATION_METHOD_LABELS[p.last_optimization_method] ??
                    p.last_optimization_method}
                </span>
              )}
              {p.is_live && (
                <span
                  className="text-xs px-1.5 py-0.5 rounded"
                  style={{
                    background: "rgba(22, 163, 74, 0.16)",
                    border: "1px solid rgba(22, 163, 74, 0.55)",
                    color: "var(--text-primary)",
                  }}
                >
                  Live
                </span>
              )}
              <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                {p.allocation_count} strategies
              </span>
              {/* Marking a portfolio live only says WHICH one execution may
                  trade — it never starts trading. The kill switch is separate
                  and defaults to halted. */}
              <button
                type="button"
                onClick={() => setLiveMutation.mutate({ id: p.id, isLive: !p.is_live })}
                className="text-xs px-2 py-1 rounded-md"
                style={{ border: "1px solid var(--border)", color: "var(--text-secondary)" }}
              >
                {p.is_live ? "Stop trading" : "Trade live"}
              </button>
              <button
                type="button"
                onClick={() => handleLoad(p.id)}
                className="text-xs px-2 py-1 rounded-md"
                style={{ border: "1px solid var(--border)", color: "var(--text-secondary)" }}
              >
                Load
              </button>
              {!p.is_system && (
                <button
                  type="button"
                  onClick={() => deleteMutation.mutate(p.id)}
                  className="text-xs px-2 py-1 rounded-md"
                  style={{ color: "var(--status-critical)" }}
                >
                  Delete
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {analysis && (
        <div className="space-y-3">
          <div className="text-xs" style={{ color: "var(--text-muted)" }}>
            Measured over overlapping strategy returns through {analysis.as_of}.
          </div>
          <VolatilityCard
            volatilityAnnualized={analysis.volatility_annualized}
            beta={analysis.beta}
          />
          <VarCard
            varHistorical95={analysis.var_historical_95}
            varParametric95={analysis.var_parametric_95}
            cvar95={analysis.cvar_95}
          />
          <DiversificationCard
            hhi={analysis.hhi}
            avgPairwiseCorrelation={analysis.avg_pairwise_correlation}
          />
          {heatmapMatrix && <CorrelationHeatmap matrix={heatmapMatrix} />}
          {analysis.warnings.map((w) => (
            <div key={w} className="text-xs" style={{ color: "var(--status-warning)" }}>
              ⚠ {w}
            </div>
          ))}
        </div>
      )}

      <OptimizerPanel
        result={optimization ?? undefined}
        isLoading={optimizeMutation.isPending}
        errorMessage={
          optimizeMutation.isError
            ? errorMessage(optimizeMutation.error, "Couldn't optimize this strategy portfolio.")
            : undefined
        }
        onRun={() => optimizeMutation.mutate()}
        onApply={(applied) => {
          // `ticker` here is the opaque experiment_run_id key the backend
          // echoed back — never the display label.
          const next = new Map<number, number>();
          applied.forEach((h) => next.set(Number(h.ticker), h.weight));
          setWeights(next);
          setAnalysis(null);
        }}
        disabled={!weightsValid}
        labelFor={labelFor}
      />
    </div>
  );
}
