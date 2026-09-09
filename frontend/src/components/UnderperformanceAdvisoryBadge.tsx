import type { UnderperformanceAdvisoryOut } from "../api/client";

// The trailing-window underperformance signal, shown as an ADVISORY rather
// than a status. Until 2026-09-09 the backend parked a registration as
// "underperforming" the first time its trailing 60-day Sharpe fell to -0.5;
// that rule was measured to kill a genuinely good (Sharpe 1.0) strategy two
// times in three, so the runner no longer acts on it. What a human should
// read instead is the whole-record PSR: the probability that the true Sharpe
// of everything realized so far is above zero. Parking is a CLAUDE.md rule-6
// decision — the project owner's, never the dashboard's.
export function UnderperformanceAdvisoryBadge({ advisory }: { advisory: UnderperformanceAdvisoryOut }) {
  if (advisory.whole_record_psr_vs_zero === null) return null; // below the 20-day floor: nothing to say yet
  const psr = advisory.whole_record_psr_vs_zero;
  const flagged = advisory.trailing_flag;
  const color = flagged ? "var(--status-warning)" : "var(--text-muted)";
  const title = flagged
    ? `Trailing ${advisory.n_realized_days >= 60 ? "60" : advisory.n_realized_days}-day Sharpe ${advisory.trailing_sharpe_annualized?.toFixed(2)} — the retired auto-park rule would have fired here. Advisory only; a 60-day Sharpe has a standard error of ~2.0.`
    : "Advisory: P(true Sharpe of the whole realized record > 0). Not a rule.";
  // Retirement rule R-2026-09-09-v2 (CUSUM, protect Sharpe 1.0, calibrated
  // so a genuinely-1.0 registration is recommended for retirement <= 5% of
  // the time in five years). A recommendation for the owner, never a status.
  const retire = advisory.retirement_recommended;
  const retireTitle = retire
    ? `Retirement rule ${advisory.retirement_rule_id}: CUSUM ${advisory.retirement_statistic?.toFixed(2)} reached the ${advisory.retirement_bucket} boundary ${advisory.retirement_boundary?.toFixed(2)} on day ${advisory.retirement_first_trigger_day}. Recommendation only (rule 6); the owner decides.`
    : `Retirement rule ${advisory.retirement_rule_id}: CUSUM ${advisory.retirement_statistic?.toFixed(2)} vs boundary ${advisory.retirement_boundary?.toFixed(2)} (${advisory.retirement_bucket}). Not triggered.`;
  return (
    <>
      <span
        className="text-xs px-1.5 py-0.5 rounded"
        title={title}
        style={{ background: "var(--page-plane)", border: `1px solid ${color}`, color }}
      >
        {flagged ? "trailing window weak · " : ""}P(edge&gt;0) {(psr * 100).toFixed(0)}% over {advisory.n_realized_days}d
      </span>
      {advisory.retirement_rule_id && (
        <span
          className="text-xs px-1.5 py-0.5 rounded ml-1"
          title={retireTitle}
          style={{
            background: "var(--page-plane)",
            border: `1px solid ${retire ? "var(--status-danger, var(--status-warning))" : "var(--text-muted)"}`,
            color: retire ? "var(--status-danger, var(--status-warning))" : "var(--text-muted)",
          }}
        >
          {retire ? "retirement recommended" : "retirement rule: clear"}
        </span>
      )}
    </>
  );
}
