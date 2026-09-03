"""FAST companion to run_xom_hypothesis_test.py: the identical XOM-exclusion
ablation, but reusing the filing index a7957eb's ceiling-confound run already
built and saved on disk 2026-09-03T15:29:18Z (~10.5h before this script runs)
-- data/research_runs/... no, the SHARED SCRATCHPAD path
lazy_ceiling_filing_index.json -- instead of re-listing ~625 tickers' EDGAR
submissions live again. That saved index already independently confirms, from
a run captured HOURS before this one and completely separately from today's
live check in run_xom_hypothesis_test.py's STEP 0: XOM IS a CIK-resolved,
indexed ticker (not unresolved, not failed) whose periodic-filings list is
EMPTY (len 0) -- i.e. it already contributes nothing, exactly matching
today's fresh live check (CIK 2115436, 0 periodic filings). Reusing it lets
the ablation run in ~1 minute instead of ~15-20, using the SAME window
(2015-01-07..2026-08-31) as BOTH the original 2026-09-01 registration AND
a7957eb's own reproduction (+0.5741/0.7278) -- the cleanest possible
apples-to-apples comparison, uncontaminated by 82b69fa's own choice of a
one-calendar-day-later end date (2026-09-01), which is a separate, mundane,
non-XOM methodological difference worth disclosing on its own.

Because the ablation varies ONLY `tickers=` (full universe vs universe minus
"XOM"), and run_lazy_prices_screening filters the shared filing_index by
`ticker in close.columns` (the PRICED set, itself governed by `tickers`),
reusing the identical cached filing_index for both runs is exactly equivalent
to rebuilding it twice live -- XOM's absence from `close.columns` in Run B
already removes it from the trimmed panel regardless of what the raw index
dict still holds for that key.
"""

from __future__ import annotations

import logging
import math
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("xom_hypothesis_test_fast")

MAIN_REPO_CACHE_DIR = Path(
    "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend/data/edgar_filing_text/v1"
)
CACHED_FILING_INDEX = Path(
    "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/"
    "142109e4-1c17-421d-b8eb-cdbe7ecaf779/scratchpad/lazy_ceiling_filing_index.json"
)
SCRATCH = Path(__file__).parent
TARGET_PATTERN = "lazy_jaccard_full_h126_ivol"
RUN_TAG_WITH = "lazy_prices_xom_included_fast_2026-09-04"
RUN_TAG_WITHOUT = "lazy_prices_xom_excluded_fast_2026-09-04"


def main() -> int:
    from datetime import date

    from app.services.market_data.edgar_filing_text_provider import (
        EdgarFilingTextProvider,
        load_filing_index,
    )
    from app.services.market_data.yfinance_provider import YFinanceProvider
    from app.services.research_lab.cross_sectional_lazy_prices import (
        run_lazy_prices_screening,
    )
    from app.services.research_lab.sp500_membership_history import (
        MEMBERSHIP_DATA_START,
        get_universe_over,
    )

    # Same window as the ORIGINAL 2026-09-01 registration and as a7957eb's
    # own reproduction (+0.5741/0.7278) -- NOT 82b69fa's 2026-09-01 end,
    # deliberately, for the cleanest possible apples-to-apples ablation.
    end = date(2026, 8, 31)

    loaded = load_filing_index(CACHED_FILING_INDEX)
    if loaded is None:
        logger.error("cached filing index not found at %s", CACHED_FILING_INDEX)
        return 1
    filing_index, filing_report = loaded
    logger.info(
        "loaded cached filing_index: requested=%d cik_resolved=%d indexed=%d filings_listed=%d",
        filing_report.n_tickers_requested,
        filing_report.n_tickers_cik_resolved,
        filing_report.n_tickers_indexed,
        filing_report.n_filings_listed,
    )
    xom_filings = filing_index.get("XOM")
    logger.info(
        "cached index: XOM key present=%s, filings=%s",
        "XOM" in filing_index,
        len(xom_filings) if xom_filings is not None else None,
    )

    universe = get_universe_over(MEMBERSHIP_DATA_START, end)
    universe_without_xom = [t for t in universe if t != "XOM"]
    logger.info(
        "universe size=%d (XOM present=%s); without_xom size=%d",
        len(universe),
        "XOM" in universe,
        len(universe_without_xom),
    )

    def _run(label: str, tickers: list[str]):
        t0 = time.monotonic()
        text_provider = EdgarFilingTextProvider(cache_dir=MAIN_REPO_CACHE_DIR)
        yf_provider = YFinanceProvider()
        summary = run_lazy_prices_screening(
            MEMBERSHIP_DATA_START,
            end,
            provider=yf_provider,
            text_provider=text_provider,
            tickers=tickers,
            filing_index=filing_index,
            filing_report=filing_report,
        )
        dt = time.monotonic() - t0
        logger.info("[%s] finished in %.1fs, n_priced=%d", label, dt, summary.n_priced_tickers)
        return summary, dt

    summary_a, dt_a = _run("A(with_XOM, cached index, end=2026-08-31)", universe)
    summary_b, dt_b = _run("B(without_XOM, cached index, end=2026-08-31)", universe_without_xom)

    def _find(summary, pattern_id: str):
        for r in summary.results:
            if r.pattern_id == pattern_id:
                return r
        return None

    row_a = _find(summary_a, TARGET_PATTERN)
    row_b = _find(summary_b, TARGET_PATTERN)
    if row_a is None or row_b is None:
        logger.error("pattern not found in one of the runs")
        return 1

    logger.info(
        "REGISTERED SPEC %s\n"
        "  committed (2026-09-01)                : Sharpe +0.6035  DSR 0.7540\n"
        "  a7957eb rebuild (2026-09-03, same window, no ablation): Sharpe +0.5741  DSR 0.7278\n"
        "  THIS RUN A (with XOM, cached index)   : Sharpe %+.4f  DSR %.4f\n"
        "  THIS RUN B (XOM excluded from tickers): Sharpe %+.4f  DSR %.4f\n"
        "  delta (B - A), the ablation's own effect: Sharpe %+.4f  DSR %+.4f",
        TARGET_PATTERN,
        row_a.sharpe_annualized,
        row_a.deflated_sharpe.dsr,
        row_b.sharpe_annualized,
        row_b.deflated_sharpe.dsr,
        row_b.sharpe_annualized - row_a.sharpe_annualized,
        row_b.deflated_sharpe.dsr - row_a.deflated_sharpe.dsr,
    )

    by_id_a = {r.pattern_id: r for r in summary_a.results}
    by_id_b = {r.pattern_id: r for r in summary_b.results}
    diffs = []
    for pid in sorted(set(by_id_a) | set(by_id_b)):
        ra, rb = by_id_a.get(pid), by_id_b.get(pid)
        sa = ra.sharpe_annualized if ra else float("nan")
        sb = rb.sharpe_annualized if rb else float("nan")
        d = (sb - sa) if (ra and rb) else float("nan")
        diffs.append((abs(d) if math.isfinite(d) else -1.0, pid, sa, sb, d))
    diffs.sort(reverse=True)
    logger.info("FULL GRID, sorted by |delta| descending:")
    for _, pid, sa, sb, d in diffs:
        logger.info("  %-32s A=%+.4f  B=%+.4f  delta=%+.4f", pid, sa, sb, d)
    max_abs_delta = max((abs(d) for _, _, _, _, d in diffs if math.isfinite(d)), default=float("nan"))
    logger.info("MAX |delta Sharpe| across all specs from the XOM-only ablation: %.4f", max_abs_delta)

    # persist
    from sqlalchemy import text as sql_text

    from app.db import SessionLocal
    from app.services.research_lab.cross_sectional_persistence import (
        persist_cross_sectional_trial_results,
    )

    def _persist(run_tag: str, summary, note: str) -> None:
        rows = list(summary.results)
        if not rows:
            logger.warning("[%s] no rows to persist", run_tag)
            return
        db = SessionLocal()
        try:
            deleted = db.execute(
                sql_text("DELETE FROM cross_sectional_trial_results WHERE run_tag = :tag"),
                {"tag": run_tag},
            ).rowcount
            db.commit()
            n = persist_cross_sectional_trial_results(
                db, "lazy_prices_xom_hypothesis_test_fast", rows, run_tag=run_tag
            )
            logger.info("[%s] persisted %d rows (replaced %d) -- %s", run_tag, n, deleted, note)
        finally:
            db.close()

    _persist(RUN_TAG_WITH, summary_a, "cached-index ablation, WITH XOM, end=2026-08-31")
    _persist(RUN_TAG_WITHOUT, summary_b, "cached-index ablation, WITHOUT XOM, end=2026-08-31")

    report_path = SCRATCH / "lazy_prices_xom_hypothesis_test_fast_2026-09-04.txt"
    lines = [
        "XOM ABLATION (FAST, cached filing index) -- 2026-09-04",
        f"window {MEMBERSHIP_DATA_START.isoformat()}..{end.isoformat()} (matches original registration + a7957eb)",
        "committed: Sharpe +0.6035 DSR 0.7540",
        "a7957eb rebuild (no ablation, same window): Sharpe +0.5741 DSR 0.7278",
        f"THIS RUN A (with XOM):    Sharpe {row_a.sharpe_annualized:+.4f}  DSR {row_a.deflated_sharpe.dsr:.4f}  ({dt_a:.0f}s)",
        f"THIS RUN B (without XOM): Sharpe {row_b.sharpe_annualized:+.4f}  DSR {row_b.deflated_sharpe.dsr:.4f}  ({dt_b:.0f}s)",
        f"delta (B-A): Sharpe {row_b.sharpe_annualized - row_a.sharpe_annualized:+.4f}  DSR {row_b.deflated_sharpe.dsr - row_a.deflated_sharpe.dsr:+.4f}",
        f"MAX |delta Sharpe| across all specs: {max_abs_delta:.4f}",
        "",
        "Full grid:",
    ]
    for _, pid, sa, sb, d in diffs:
        lines.append(f"  {pid:32s} A={sa:+.4f}  B={sb:+.4f}  delta={d:+.4f}")
    report_path.write_text("\n".join(lines) + "\n")
    logger.info("wrote %s", report_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
