import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { isAxiosError } from "axios";
import { createMomentumSweep, listSweeps } from "../api/client";
import type { ApiErrorBody, SweepJobOut } from "../api/client";

// Mirrors backend/app/services/research_lab/sweep_service.py's
// MAX_SWEEP_COMBINATIONS — a client-side mirror so the counter below can
// warn before submitting, not just after a 422 comes back.
const MAX_SWEEP_COMBINATIONS = 500;

const DEFAULT_FIT_WINDOW_DAYS = "90";
const DEFAULT_ENTRY_Z = "2.0";
const DEFAULT_EXIT_Z = "0.0";
const DEFAULT_COST_BPS = "5.0";

function parseNumberList(input: string): number[] {
  return input
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s.length > 0)
    .map(Number)
    .filter((n) => !Number.isNaN(n));
}

function countValidCombinations(
  fitWindowDays: number[],
  entryZ: number[],
  exitZ: number[],
  costBps: number[],
): number {
  let validPairs = 0;
  for (const e of entryZ) {
    for (const x of exitZ) {
      if (x < e) validPairs += 1;
    }
  }
  return validPairs * fitWindowDays.length * costBps.length;
}

function formatCombos(n: number): string {
  return `${n} combination${n === 1 ? "" : "s"}`;
}

function statusLabel(status: SweepJobOut["status"]): string {
  if (status === "completed") return "completed";
  if (status === "running") return "running";
  return "queued";
}

function MomentumSweepJobRow({ job }: { job: SweepJobOut }) {
  const attempted = job.configurations_completed + job.configurations_failed;
  const progressPct = job.total_configurations > 0 ? (attempted / job.total_configurations) * 100 : 0;
  const isDone = job.status === "completed";

  return (
    <div
      className="rounded-lg p-4 space-y-2"
      style={{ background: "var(--surface-1)", border: "1px solid var(--border)" }}
    >
      <div className="flex items-center justify-between">
        <div className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
          {job.ticker_a}
        </div>
        <span
          className="text-xs px-1.5 py-0.5 rounded"
          style={{
            background: "var(--page-plane)",
            border: `1px solid ${isDone ? "var(--status-good)" : "var(--border)"}`,
            color: isDone ? "var(--status-good)" : "var(--text-muted)",
          }}
        >
          {statusLabel(job.status)}
        </span>
      </div>
      <div>
        <div className="flex items-center justify-between text-xs mb-1" style={{ color: "var(--text-muted)" }}>
          <span>
            {attempted} / {job.total_configurations} configurations
            {job.configurations_failed > 0 ? ` (${job.configurations_failed} failed)` : ""}
          </span>
        </div>
        <div className="h-1.5 rounded-full overflow-hidden" style={{ background: "var(--page-plane)" }}>
          <div
            style={{
              width: `${progressPct}%`,
              height: "100%",
              background: isDone ? "var(--status-good)" : "var(--accent-blue)",
            }}
          />
        </div>
      </div>
    </div>
  );
}

export function MomentumSweepPanel() {
  const [isExpanded, setIsExpanded] = useState(false);
  const [ticker, setTicker] = useState("");
  const [lookbackYears, setLookbackYears] = useState(5);
  const [fitWindowDaysInput, setFitWindowDaysInput] = useState(DEFAULT_FIT_WINDOW_DAYS);
  const [entryZInput, setEntryZInput] = useState(DEFAULT_ENTRY_Z);
  const [exitZInput, setExitZInput] = useState(DEFAULT_EXIT_Z);
  const [costBpsInput, setCostBpsInput] = useState(DEFAULT_COST_BPS);

  const queryClient = useQueryClient();

  const { data: allJobs } = useQuery({
    queryKey: ["sweepJobs"],
    queryFn: listSweeps,
    refetchInterval: (query) => {
      const list = query.state.data;
      const hasActive = list?.some((j) => j.status === "queued" || j.status === "running") ?? false;
      return hasActive ? 5000 : false;
    },
  });
  // Scoped to this strategy's own jobs — see SweepPanel.tsx's identical note.
  const jobs = allJobs?.filter((j) => j.strategy_name === "momentum_v1");

  const mutation = useMutation({
    mutationFn: () =>
      createMomentumSweep({
        ticker,
        lookback_years: lookbackYears,
        grid: {
          fit_window_days: parseNumberList(fitWindowDaysInput),
          entry_z: parseNumberList(entryZInput),
          exit_z: parseNumberList(exitZInput),
          cost_bps: parseNumberList(costBpsInput),
        },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sweepJobs"] });
    },
  });

  const parsedGrid = useMemo(
    () => ({
      fitWindowDays: parseNumberList(fitWindowDaysInput),
      entryZ: parseNumberList(entryZInput),
      exitZ: parseNumberList(exitZInput),
      costBps: parseNumberList(costBpsInput),
    }),
    [fitWindowDaysInput, entryZInput, exitZInput, costBpsInput],
  );

  const combinationCount = countValidCombinations(
    parsedGrid.fitWindowDays,
    parsedGrid.entryZ,
    parsedGrid.exitZ,
    parsedGrid.costBps,
  );
  const overCap = combinationCount > MAX_SWEEP_COMBINATIONS;
  const canSubmit = ticker.trim() !== "" && combinationCount > 0 && !overCap && !mutation.isPending;

  const errorMessage = mutation.error
    ? isAxiosError<ApiErrorBody>(mutation.error)
      ? (mutation.error.response?.data?.detail ?? "Sweep submission failed.")
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
        Momentum parameter sweep — test many configurations at once {isExpanded ? "▾" : "▸"}
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
            ⚠ Enter comma-separated values to test multiple settings per parameter — leave a field at
            its default to hold that parameter fixed. Every combination gets a "1 of N" label
            wherever it shows up, so a result found on the first try is never confused with one found
            on the 500th.
          </div>

          <div className="flex flex-wrap items-end gap-2">
            <div>
              <div className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>
                Ticker
              </div>
              <input
                type="text"
                value={ticker}
                onChange={(e) => setTicker(e.target.value)}
                placeholder="e.g. AAPL"
                className="text-sm px-3 py-1.5 rounded-md w-28"
                style={{ background: "var(--page-plane)", border: "1px solid var(--border)", color: "var(--text-primary)" }}
              />
            </div>
            <div>
              <div className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>
                Lookback (years)
              </div>
              <input
                type="number"
                value={lookbackYears}
                onChange={(e) => setLookbackYears(Number(e.target.value))}
                className="text-sm px-3 py-1.5 rounded-md w-24"
                style={{ background: "var(--page-plane)", border: "1px solid var(--border)", color: "var(--text-primary)" }}
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-4 gap-2">
            <div>
              <div className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>
                Fit window (days) values
              </div>
              <input
                type="text"
                value={fitWindowDaysInput}
                onChange={(e) => setFitWindowDaysInput(e.target.value)}
                placeholder="e.g. 60, 90, 150"
                className="text-sm px-2 py-1.5 rounded-md w-full"
                style={{ background: "var(--page-plane)", border: "1px solid var(--border)", color: "var(--text-primary)" }}
              />
            </div>
            <div>
              <div className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>
                Entry z values
              </div>
              <input
                type="text"
                value={entryZInput}
                onChange={(e) => setEntryZInput(e.target.value)}
                placeholder="e.g. 1.5, 2.0, 2.5"
                className="text-sm px-2 py-1.5 rounded-md w-full"
                style={{ background: "var(--page-plane)", border: "1px solid var(--border)", color: "var(--text-primary)" }}
              />
            </div>
            <div>
              <div className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>
                Exit z values
              </div>
              <input
                type="text"
                value={exitZInput}
                onChange={(e) => setExitZInput(e.target.value)}
                placeholder="e.g. 0.0, 0.5"
                className="text-sm px-2 py-1.5 rounded-md w-full"
                style={{ background: "var(--page-plane)", border: "1px solid var(--border)", color: "var(--text-primary)" }}
              />
            </div>
            <div>
              <div className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>
                Cost (bps) values
              </div>
              <input
                type="text"
                value={costBpsInput}
                onChange={(e) => setCostBpsInput(e.target.value)}
                placeholder="e.g. 5, 10"
                className="text-sm px-2 py-1.5 rounded-md w-full"
                style={{ background: "var(--page-plane)", border: "1px solid var(--border)", color: "var(--text-primary)" }}
              />
            </div>
          </div>

          <div className="flex items-center justify-between gap-3">
            <span
              className="text-xs"
              style={{ color: overCap ? "var(--status-critical)" : "var(--text-muted)" }}
            >
              This will run {formatCombos(combinationCount)}
              {overCap ? ` — above the ${MAX_SWEEP_COMBINATIONS} limit per sweep` : ""}
            </span>
            <button
              type="button"
              onClick={() => mutation.mutate()}
              disabled={!canSubmit}
              className="text-sm px-3 py-1.5 rounded-md text-white disabled:opacity-50"
              style={{ background: "var(--accent-blue)" }}
            >
              {mutation.isPending ? "Submitting…" : "Run sweep"}
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
                Your sweeps
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {jobs.map((job) => (
                  <MomentumSweepJobRow key={job.id} job={job} />
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
