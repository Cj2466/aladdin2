import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { isAxiosError } from "axios";
import {
  createScreeningJob,
  getScreeningJob,
  listScreeningJobs,
  runMomentumBacktest,
  runPairsBacktest,
} from "../api/client";
import type { ApiErrorBody, ScreeningCandidateOut, ScreeningJobOut, ScreeningStrategyName } from "../api/client";
import { isMomentum, tickerLabel } from "./LeaderboardTable";

const METHODOLOGY_NOTE =
  "Research tool, not a trading signal. Screens a fixed, hand-curated cross-section of large-cap " +
  "tickers (a point-in-time snapshot, not a live index feed) using a cheap statistical pre-filter — " +
  "correlation for pairs, trend significance for momentum — before any expensive backtest runs. " +
  "This surfaces a shortlist, it does not validate anything; only a full walk-forward backtest on a " +
  "specific candidate (and, beyond that, real forward-time evidence) carries evidentiary weight.";

function statusLabel(status: ScreeningJobOut["status"]): string {
  if (status === "completed") return "completed";
  if (status === "failed") return "failed";
  if (status === "running") return "running";
  return "queued";
}

function statusColor(status: ScreeningJobOut["status"]): string {
  if (status === "completed") return "var(--status-good)";
  if (status === "failed") return "var(--status-critical)";
  if (status === "running") return "var(--accent-blue)";
  return "var(--text-muted)";
}

function formatScore(strategyName: string, score: number): string {
  return isMomentum(strategyName) ? `t-stat ${score.toFixed(2)}` : `corr ${score.toFixed(2)}`;
}

function regimeBadgeLabel(regime: ScreeningCandidateOut["regime"]): string | null {
  // "indeterminate" is the overwhelming majority outcome (empirically ~95% of the real
  // universe) — not worth a badge's visual weight. Only the rare, real tag earns one.
  if (regime === "trending") return "Trending";
  if (regime === "mean_reverting") return "Mean-reverting";
  return null;
}

function CandidateBacktestButton({
  strategyName,
  candidate,
}: {
  strategyName: string;
  candidate: ScreeningCandidateOut;
}) {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: () =>
      isMomentum(strategyName)
        ? runMomentumBacktest({ ticker: candidate.ticker_a })
        : runPairsBacktest({ ticker_a: candidate.ticker_a, ticker_b: candidate.ticker_b }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["experimentRuns"] });
    },
  });

  let label = "Backtest this candidate";
  if (mutation.isPending) label = "Running…";
  else if (mutation.isSuccess) label = "Backtested — see leaderboard";
  else if (mutation.isError) label = "Couldn't run backtest";

  return (
    <button
      type="button"
      onClick={() => mutation.mutate()}
      disabled={mutation.isPending || mutation.isSuccess}
      className="text-xs px-2.5 py-1 rounded-md disabled:opacity-70"
      style={{
        background: mutation.isSuccess ? "var(--status-good)" : "var(--page-plane)",
        border: "1px solid var(--border)",
        color: mutation.isSuccess ? "white" : "var(--text-secondary)",
      }}
    >
      {label}
    </button>
  );
}

function ScreeningJobDetail({ jobId, onClose }: { jobId: number; onClose: () => void }) {
  const { data: job, isLoading } = useQuery({
    queryKey: ["screeningJobDetail", jobId],
    queryFn: () => getScreeningJob(jobId),
  });

  return (
    <div
      className="rounded-lg p-4 space-y-3"
      style={{ background: "var(--surface-1)", border: "1px solid var(--border)" }}
    >
      <div className="flex items-center justify-between">
        <div className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
          Screening run #{jobId}
        </div>
        <button type="button" onClick={onClose} className="text-xs" style={{ color: "var(--text-muted)" }}>
          close
        </button>
      </div>

      {isLoading && (
        <div className="text-sm" style={{ color: "var(--text-muted)" }}>
          Loading…
        </div>
      )}

      {job && (
        <div className="space-y-3">
          <div className="text-xs italic" style={{ color: "var(--text-muted)" }}>
            {job.methodology_note}
          </div>

          {job.status === "failed" && (
            <div
              className="rounded-md p-3 text-xs"
              style={{
                background: "var(--page-plane)",
                border: "1px solid var(--status-critical)",
                color: "var(--text-secondary)",
              }}
            >
              Screening failed: {job.error_message ?? "unknown error"}
            </div>
          )}

          {job.candidates.length === 0 && job.status === "completed" && (
            <div className="text-sm" style={{ color: "var(--text-muted)" }}>
              No candidates cleared the bar this run.
            </div>
          )}

          {job.candidates.length > 0 && (
            <div className="space-y-2">
              {job.candidates.map((c) => (
                <div
                  key={`${c.ticker_a}-${c.ticker_b}`}
                  className="flex items-center justify-between rounded-md p-2 text-xs"
                  style={{ background: "var(--page-plane)", border: "1px solid var(--border)" }}
                >
                  <div className="flex items-center gap-3">
                    <span style={{ color: "var(--text-primary)", fontWeight: 500 }}>
                      {tickerLabel(job.strategy_name, c.ticker_a, c.ticker_b)}
                    </span>
                    <span style={{ color: "var(--text-secondary)" }}>{formatScore(job.strategy_name, c.score)}</span>
                    {c.direction && (
                      <span
                        className="px-1.5 py-0.5 rounded"
                        style={{
                          background: "var(--surface-1)",
                          border: "1px solid var(--border)",
                          color: c.direction === "long" ? "var(--status-good)" : "var(--status-critical)",
                        }}
                      >
                        {c.direction === "long" ? "Long" : "Short"}
                      </span>
                    )}
                    {isMomentum(job.strategy_name) && regimeBadgeLabel(c.regime) && (
                      <span
                        className="px-1.5 py-0.5 rounded"
                        style={{
                          background: "var(--surface-1)",
                          border: "1px solid var(--accent-blue)",
                          color: "var(--accent-blue)",
                        }}
                      >
                        {regimeBadgeLabel(c.regime)}
                      </span>
                    )}
                  </div>
                  <CandidateBacktestButton strategyName={job.strategy_name} candidate={c} />
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ScreeningJobRow({ job, onSelect }: { job: ScreeningJobOut; onSelect: () => void }) {
  const clickable = job.status === "completed" || job.status === "failed";
  return (
    <div
      onClick={clickable ? onSelect : undefined}
      className="rounded-lg p-4 space-y-2"
      style={{
        background: "var(--surface-1)",
        border: "1px solid var(--border)",
        cursor: clickable ? "pointer" : "default",
      }}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
            {job.strategy_name === "momentum_v1" ? "Momentum" : "Pairs"} screen #{job.id}
          </div>
          {job.is_system && (
            <span
              className="text-xs px-1.5 py-0.5 rounded"
              style={{ background: "var(--page-plane)", border: "1px solid var(--border)", color: "var(--text-muted)" }}
            >
              Automatic daily run
            </span>
          )}
        </div>
        <span
          className="text-xs px-1.5 py-0.5 rounded"
          style={{
            background: "var(--page-plane)",
            border: `1px solid ${statusColor(job.status)}`,
            color: statusColor(job.status),
          }}
        >
          {statusLabel(job.status)}
        </span>
      </div>
      <div className="text-xs" style={{ color: "var(--text-muted)" }}>
        {job.status === "completed"
          ? `${job.n_tickers_resolved}/${job.universe_size} tickers resolved · ${job.n_candidates_found} candidates found`
          : job.status === "failed"
            ? (job.error_message ?? "failed")
            : `universe of ${job.universe_size} tickers`}
      </div>
    </div>
  );
}

export function ScreeningPanel() {
  const [isExpanded, setIsExpanded] = useState(false);
  const [strategyName, setStrategyName] = useState<ScreeningStrategyName>("ou_pairs_v1");
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null);
  const queryClient = useQueryClient();

  const { data: jobs } = useQuery({
    queryKey: ["screeningJobs"],
    queryFn: listScreeningJobs,
    refetchInterval: (query) => {
      const list = query.state.data;
      const hasActive = list?.some((j) => j.status === "queued" || j.status === "running") ?? false;
      return hasActive ? 5000 : false;
    },
  });

  const mutation = useMutation({
    mutationFn: () => createScreeningJob({ strategy_name: strategyName }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["screeningJobs"] });
    },
  });

  const errorMessage = mutation.error
    ? isAxiosError<ApiErrorBody>(mutation.error)
      ? (mutation.error.response?.data?.detail ?? "Screening submission failed.")
      : "Something went wrong."
    : undefined;

  return (
    <div>
      <button
        type="button"
        onClick={() => setIsExpanded((v) => !v)}
        className="text-sm"
        style={{ color: "var(--text-secondary)" }}
      >
        Candidate screening — discover tickers before hand-picking {isExpanded ? "▾" : "▸"}
      </button>

      {isExpanded && (
        <div
          className="mt-3 rounded-lg p-4 space-y-3"
          style={{ background: "var(--surface-1)", border: "1px solid var(--border)" }}
        >
          <div
            className="rounded-md p-3 text-xs"
            style={{
              background: "var(--page-plane)",
              border: "1px solid var(--status-warning)",
              color: "var(--text-secondary)",
            }}
          >
            ⚠ {METHODOLOGY_NOTE}
          </div>

          <div className="flex flex-wrap items-end gap-2">
            <div className="flex rounded-md overflow-hidden" style={{ border: "1px solid var(--border)" }}>
              <button
                type="button"
                onClick={() => setStrategyName("ou_pairs_v1")}
                className="text-sm px-3 py-1.5"
                style={{
                  background: strategyName === "ou_pairs_v1" ? "var(--accent-blue)" : "var(--page-plane)",
                  color: strategyName === "ou_pairs_v1" ? "white" : "var(--text-secondary)",
                }}
              >
                Pairs (mean-reversion)
              </button>
              <button
                type="button"
                onClick={() => setStrategyName("momentum_v1")}
                className="text-sm px-3 py-1.5"
                style={{
                  background: strategyName === "momentum_v1" ? "var(--accent-blue)" : "var(--page-plane)",
                  color: strategyName === "momentum_v1" ? "white" : "var(--text-secondary)",
                }}
              >
                Momentum (trend)
              </button>
            </div>
            <button
              type="button"
              onClick={() => mutation.mutate()}
              disabled={mutation.isPending}
              className="text-sm px-3 py-1.5 rounded-md text-white disabled:opacity-50"
              style={{ background: "var(--accent-blue)" }}
            >
              {mutation.isPending ? "Submitting…" : "Screen the universe"}
            </button>
          </div>

          {errorMessage && (
            <div className="text-sm" style={{ color: "var(--status-critical)" }}>
              {errorMessage}
            </div>
          )}

          {jobs && jobs.length > 0 && (
            <div className="space-y-2 pt-1">
              <div className="text-xs" style={{ color: "var(--text-muted)" }}>
                Screening runs
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {jobs.map((job) => (
                  <ScreeningJobRow key={job.id} job={job} onSelect={() => setSelectedJobId(job.id)} />
                ))}
              </div>
            </div>
          )}

          {selectedJobId !== null && (
            <ScreeningJobDetail jobId={selectedJobId} onClose={() => setSelectedJobId(null)} />
          )}
        </div>
      )}
    </div>
  );
}
