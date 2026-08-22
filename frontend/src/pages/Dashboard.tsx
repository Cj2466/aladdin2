import { useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { isAxiosError } from "axios";
import {
  analyzePortfolio,
  analyzeSavedPortfolio,
  computeFactorRisk,
  computeFactorRiskForSavedPortfolio,
  optimizePortfolio,
  optimizeSavedPortfolio,
  stressTestPortfolio,
  stressTestSavedPortfolio,
} from "../api/client";
import type { ApiErrorBody, HoldingInput, PortfolioAnalyzeRequest } from "../api/client";
import { useAuth } from "../hooks/useAuth";
import { useLiveQuotes } from "../hooks/useLiveQuotes";
import { PortfolioForm } from "../components/PortfolioForm";
import { SavedPortfolios } from "../components/SavedPortfolios";
import type { ActivePortfolio } from "../components/SavedPortfolios";
import { StatTile } from "../components/StatTile";
import { VolatilityCard } from "../components/VolatilityCard";
import { VarCard } from "../components/VarCard";
import { DiversificationCard } from "../components/DiversificationCard";
import { CorrelationHeatmap } from "../components/CorrelationHeatmap";
import { StressTestPanel } from "../components/StressTestPanel";
import { SectorExposureChart } from "../components/SectorExposureChart";
import { OptimizerPanel } from "../components/OptimizerPanel";
import { FactorRiskPanel } from "../components/FactorRiskPanel";
import { ExportControls } from "../components/ExportControls";
import { AlertBell } from "../components/AlertBell";
import { formatPercentValue } from "../lib/format";

const DEFAULT_HOLDINGS: HoldingInput[] = [
  { ticker: "AAPL", weight: 0.4 },
  { ticker: "MSFT", weight: 0.35 },
  { ticker: "GLD", weight: 0.25 },
];

const CONNECTION_LABEL: Record<string, string> = {
  connecting: "Connecting…",
  open: "Live",
  reconnecting: "Reconnecting…",
  unavailable: "Live data unavailable",
};

export function Dashboard() {
  const { user, logout } = useAuth();
  const [holdings, setHoldings] = useState<HoldingInput[]>(DEFAULT_HOLDINGS);
  const [benchmark, setBenchmark] = useState("SPY");
  const [activePortfolio, setActivePortfolio] = useState<ActivePortfolio | null>(null);

  // Loading/editing a saved portfolio and then changing holdings should stop
  // "Analyze" from silently reusing the old saved-portfolio id — any edit
  // reverts to the ad-hoc/stateless flow until explicitly re-saved.
  function handleHoldingsChange(next: HoldingInput[]) {
    setHoldings(next);
    setActivePortfolio(null);
  }
  function handleBenchmarkChange(next: string) {
    setBenchmark(next);
    setActivePortfolio(null);
  }

  const mutation = useMutation({
    mutationFn: (request: PortfolioAnalyzeRequest) =>
      activePortfolio
        ? analyzeSavedPortfolio(activePortfolio.id, request.benchmark, request.lookback_years)
        : analyzePortfolio(request),
  });

  const stressMutation = useMutation({
    mutationFn: () =>
      activePortfolio
        ? stressTestSavedPortfolio(activePortfolio.id, benchmark)
        : stressTestPortfolio({ holdings, benchmark }),
  });

  const optimizeMutation = useMutation({
    mutationFn: () =>
      activePortfolio
        ? optimizeSavedPortfolio(activePortfolio.id, 3)
        : optimizePortfolio({ holdings, lookback_years: 3 }),
  });

  const factorRiskMutation = useMutation({
    mutationFn: () =>
      activePortfolio
        ? computeFactorRiskForSavedPortfolio(activePortfolio.id, 3)
        : computeFactorRisk({ holdings, lookback_years: 3 }),
  });

  const watchedTickers = useMemo(
    () => [...holdings.map((h) => h.ticker).filter(Boolean), benchmark].filter(Boolean),
    [holdings, benchmark],
  );
  const { quotes, connectionState } = useLiveQuotes(watchedTickers);

  const liveHoldingsReturn = useMemo(() => {
    let weightedSum = 0;
    let coveredWeight = 0;
    for (const holding of holdings) {
      const ticker = holding.ticker.trim().toUpperCase();
      const quote = quotes[ticker];
      if (quote?.status === "ok") {
        weightedSum += holding.weight * quote.changePercent;
        coveredWeight += holding.weight;
      }
    }
    return coveredWeight > 0 ? { value: weightedSum, coveredWeight } : null;
  }, [holdings, quotes]);

  const errorMessage = mutation.error
    ? isAxiosError<ApiErrorBody>(mutation.error)
      ? (mutation.error.response?.data?.detail ?? "Request failed. Is the API running?")
      : "Something went wrong."
    : undefined;

  const result = mutation.data;
  const isCached = result && "cached" in result ? result.cached : undefined;

  const stressResult = stressMutation.data;
  const stressErrorMessage = stressMutation.error
    ? isAxiosError<ApiErrorBody>(stressMutation.error)
      ? (stressMutation.error.response?.data?.detail ?? "Stress test failed.")
      : "Something went wrong."
    : undefined;

  const optimizeErrorMessage = optimizeMutation.error
    ? isAxiosError<ApiErrorBody>(optimizeMutation.error)
      ? (optimizeMutation.error.response?.data?.detail ?? "Optimization failed.")
      : "Something went wrong."
    : undefined;

  const factorRiskErrorMessage = factorRiskMutation.error
    ? isAxiosError<ApiErrorBody>(factorRiskMutation.error)
      ? (factorRiskMutation.error.response?.data?.detail ?? "Factor risk analysis failed.")
      : "Something went wrong."
    : undefined;

  return (
    <div className="min-h-screen mx-auto max-w-4xl px-4 py-8 space-y-6">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold" style={{ color: "var(--text-primary)" }}>
            Aladdin2 — Portfolio Risk Analytics
          </h1>
          <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
            Data from Yahoo Finance (unofficial) and Finnhub (live quotes), for informational
            purposes only — not investment advice.
          </p>
        </div>
        <div className="flex items-center gap-3 shrink-0 pt-1">
          <span className="text-sm" style={{ color: "var(--text-muted)" }}>
            {user?.email}
          </span>
          <AlertBell />
          <button
            type="button"
            onClick={() => logout()}
            className="text-sm px-3 py-1.5 rounded-md"
            style={{ border: "1px solid var(--border)", color: "var(--text-secondary)" }}
          >
            Sign out
          </button>
        </div>
      </header>

      <SavedPortfolios
        activePortfolio={activePortfolio}
        onActivePortfolioChange={setActivePortfolio}
        currentHoldings={holdings}
        onLoadPortfolio={setHoldings}
      />

      {activePortfolio && (
        <ExportControls portfolioId={activePortfolio.id} benchmark={benchmark} />
      )}

      <PortfolioForm
        holdings={holdings}
        onHoldingsChange={handleHoldingsChange}
        benchmark={benchmark}
        onBenchmarkChange={handleBenchmarkChange}
        liveQuotes={quotes}
        liveConnectionState={connectionState}
        onSubmit={(request) => mutation.mutate(request)}
        isLoading={mutation.isPending}
        errorMessage={errorMessage}
      />

      {connectionState !== "unavailable" && (
        <StatTile
          label="Live portfolio return today"
          value={
            liveHoldingsReturn
              ? formatPercentValue(liveHoldingsReturn.value)
              : connectionState === "open"
                ? "—"
                : "…"
          }
          sublabel={
            CONNECTION_LABEL[connectionState] +
            (liveHoldingsReturn && liveHoldingsReturn.coveredWeight < 0.999
              ? ` · covers ${(liveHoldingsReturn.coveredWeight * 100).toFixed(0)}% of weight`
              : "")
          }
        />
      )}

      {result && (
        <div className="space-y-4">
          <div className="text-xs flex items-center gap-2" style={{ color: "var(--text-muted)" }}>
            <span>As of {result.as_of}</span>
            {isCached !== undefined && (
              <span
                className="px-1.5 py-0.5 rounded"
                style={{
                  background: "var(--page-plane)",
                  border: "1px solid var(--border)",
                  color: isCached ? "var(--status-good)" : "var(--text-muted)",
                }}
              >
                {isCached ? "cached" : "freshly computed"}
              </span>
            )}
          </div>

          {result.warnings.length > 0 && (
            <div
              className="rounded-lg p-3 text-sm space-y-1"
              style={{
                background: "var(--surface-1)",
                border: `1px solid var(--status-warning)`,
              }}
            >
              {result.warnings.map((w) => (
                <div key={w} style={{ color: "var(--text-secondary)" }}>
                  ⚠ {w}
                </div>
              ))}
            </div>
          )}

          <VolatilityCard volatilityAnnualized={result.volatility_annualized} beta={result.beta} />
          <VarCard
            varHistorical95={result.var_historical_95}
            varParametric95={result.var_parametric_95}
            cvar95={result.cvar_95}
          />
          <DiversificationCard
            hhi={result.hhi}
            avgPairwiseCorrelation={result.avg_pairwise_correlation}
          />
          <CorrelationHeatmap matrix={result.correlation_matrix} />
        </div>
      )}

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="text-sm font-medium" style={{ color: "var(--text-secondary)" }}>
            Stress testing &amp; sector exposure
          </div>
          <button
            type="button"
            onClick={() => stressMutation.mutate()}
            disabled={stressMutation.isPending || holdings.length === 0}
            className="text-sm px-3 py-1.5 rounded-md text-white disabled:opacity-50"
            style={{ background: "var(--accent-blue)" }}
          >
            {stressMutation.isPending ? "Running…" : "Run stress test"}
          </button>
        </div>

        {stressErrorMessage && (
          <div className="text-sm" style={{ color: "var(--status-critical)" }}>
            {stressErrorMessage}
          </div>
        )}

        {stressResult && (
          <div className="space-y-4">
            {stressResult.warnings.length > 0 && (
              <div
                className="rounded-lg p-3 text-sm space-y-1"
                style={{ background: "var(--surface-1)", border: "1px solid var(--status-warning)" }}
              >
                {stressResult.warnings.map((w) => (
                  <div key={w} style={{ color: "var(--text-secondary)" }}>
                    ⚠ {w}
                  </div>
                ))}
              </div>
            )}
            <StressTestPanel scenarios={stressResult.scenarios} />
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <SectorExposureChart title="Sector exposure" slices={stressResult.sector_exposure} />
              <SectorExposureChart
                title="Asset class exposure"
                slices={stressResult.asset_class_exposure}
              />
            </div>
          </div>
        )}
      </div>

      <OptimizerPanel
        result={optimizeMutation.data}
        isLoading={optimizeMutation.isPending}
        errorMessage={optimizeErrorMessage}
        onRun={() => optimizeMutation.mutate()}
        onApply={handleHoldingsChange}
        disabled={holdings.length === 0}
      />

      <FactorRiskPanel
        result={factorRiskMutation.data}
        isLoading={factorRiskMutation.isPending}
        errorMessage={factorRiskErrorMessage}
        onRun={() => factorRiskMutation.mutate()}
        disabled={holdings.length === 0}
      />
    </div>
  );
}
