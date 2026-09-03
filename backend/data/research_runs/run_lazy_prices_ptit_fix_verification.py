"""VERIFICATION OF THE PRICE-DATA POINT-IN-TIME FIX (2026-09-04).

BACKGROUND. lazy_prices_forward_registration.py's 2026-09-04 correction
("Refute the XOM CIK-fix hypothesis...", commit 3af7904) left the family's
reproduction drift (+0.6035 -> +0.5741 -> +0.5946 -> +0.5498 across four
same-window reruns) honestly unexplained beyond "consistent with this
family's own live, non-point-in-time dependencies". A follow-up
investigation the same night found and PROVED the actual dominant driver:
YFinanceProvider.get_daily_ohlcv (auto_adjust=True, no caching layer) is not
point-in-time -- Yahoo continuously reprocesses dividends/splits and
retroactively re-adjusts its ENTIRE historical Close series, so a rerun of
the identical nominal window on a different calendar day sees different
historical prices. An isolation test (identical similarity panels, identical
code, only the live price fetch re-run ~5.5h apart) moved the registered
spec's Sharpe by +0.0205 and other specs by up to 0.0433 with ZERO code
changes -- the same order of magnitude as the drift under investigation.
SEC's ticker->CIK map (the ORIGINAL leading suspect) was separately re-tested
over a comparable window and found NOT to have moved at all.

THE FIX: yfinance_provider.save_ohlcv_snapshot/load_ohlcv_snapshot (new) plus
run_lazy_prices_screening's new `price_frames` parameter -- freeze a
get_daily_ohlcv result to disk once, replay it on every later rerun, exactly
the shape save_filing_index/load_filing_index/`filing_index` already
established for the EDGAR side (which this script ALSO now actually uses via
DEFAULT_FILING_INDEX_PATH, populated here for the first time).

THIS SCRIPT is the actual before/after proof required to call the fix done:
 STEP 1: build the canonical frozen snapshot (full 768-ticker point-in-time
         universe, live fetch) for the registration's own window
         (MEMBERSHIP_DATA_START..2026-08-31), and the filing index for
         whichever tickers priced -- reusing the existing ~924MB EDGAR
         filing-TEXT disk cache (documents are immutable, so this changes no
         bytes of any result) for the individual filing bodies, so only the
         EDGAR submissions LISTING step needs a live call.
 STEP 2: save both snapshots to disk (DEFAULT_PRICE_SNAPSHOT_DIR,
         DEFAULT_FILING_INDEX_PATH) -- these become the family's own
         reproducibility artifacts, committed to git.
 STEP 3: load BOTH snapshots back from disk (not the in-memory objects --
         a genuine round-trip through the persisted files) and run
         run_lazy_prices_screening TWICE against them.
 STEP 4: diff all 36 specs' Sharpe/DSR between the two runs. Success is
         EXACT equality (delta == 0.0 to the printed precision) for every
         spec, because both runs now share byte-identical inputs and the
         family's own code has no other source of non-determinism (already
         established by 3af7904's XOM ablation, which reproduced to
         delta 0.0000 reusing a cached filing index and a same-session live
         price fetch).

Run from backend/ with ./venv/bin/python data/research_runs/run_lazy_prices_ptit_fix_verification.py
"""

from __future__ import annotations

import logging
import sys
import time
from datetime import date
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("lazy_prices_ptit_fix_verification")

SCRATCH = Path(__file__).parent
RUN_START = date(2015, 1, 7)  # MEMBERSHIP_DATA_START
RUN_END = date(2026, 8, 31)  # matches the original registration's own window
TARGET_PATTERN = "lazy_jaccard_full_h126_ivol"


def main() -> int:
    from app.services.market_data.edgar_filing_text_provider import (
        EdgarFilingTextProvider,
        load_filing_index,
        save_filing_index,
    )
    from app.services.market_data.yfinance_provider import (
        YFinanceProvider,
        load_ohlcv_snapshot,
        save_ohlcv_snapshot,
    )
    from app.services.research_lab.cross_sectional_lazy_prices import (
        DEFAULT_FILING_INDEX_PATH,
        DEFAULT_PRICE_SNAPSHOT_DIR,
        LAZY_PRICES_FORMS,
        MEMBERSHIP_DATA_START,
        run_lazy_prices_screening,
    )
    from app.services.research_lab.sp500_membership_history import get_universe_over

    assert MEMBERSHIP_DATA_START == RUN_START

    # ---- STEP 1: build (or reuse) the canonical frozen snapshots -----------
    universe = get_universe_over(RUN_START, RUN_END)
    logger.info("full point-in-time universe: %d tickers", len(universe))

    if load_ohlcv_snapshot(DEFAULT_PRICE_SNAPSHOT_DIR) is None:
        logger.info("no price snapshot on disk yet -- fetching live now (one-time)")
        provider = YFinanceProvider()
        t0 = time.monotonic()
        frames, missing = provider.get_daily_ohlcv(sorted(universe), RUN_START, RUN_END)
        logger.info(
            "live price fetch done in %.1fs: priced=%d missing=%d",
            time.monotonic() - t0, len(frames["close"].columns), len(missing),
        )
        save_ohlcv_snapshot(frames, DEFAULT_PRICE_SNAPSHOT_DIR)
        logger.info("saved price snapshot to %s", DEFAULT_PRICE_SNAPSHOT_DIR)
    else:
        logger.info("price snapshot already exists on disk at %s -- reusing", DEFAULT_PRICE_SNAPSHOT_DIR)

    price_frames_for_index = load_ohlcv_snapshot(DEFAULT_PRICE_SNAPSHOT_DIR)
    assert price_frames_for_index is not None
    priced_tickers = list(price_frames_for_index["close"].columns)
    logger.info("priced tickers per frozen snapshot: %d", len(priced_tickers))

    if load_filing_index(DEFAULT_FILING_INDEX_PATH) is None:
        logger.info("no filing index on disk yet -- building live now (one-time, reuses cached filing text)")
        text_provider = EdgarFilingTextProvider()
        t0 = time.monotonic()
        filing_index, filing_report = text_provider.build_filing_index(
            priced_tickers, forms=LAZY_PRICES_FORMS
        )
        logger.info(
            "filing index built in %.1fs: requested=%d cik_resolved=%d indexed=%d filings_listed=%d",
            time.monotonic() - t0,
            filing_report.n_tickers_requested,
            filing_report.n_tickers_cik_resolved,
            filing_report.n_tickers_indexed,
            filing_report.n_filings_listed,
        )
        save_filing_index(filing_index, filing_report, DEFAULT_FILING_INDEX_PATH)
        logger.info("saved filing index to %s", DEFAULT_FILING_INDEX_PATH)
    else:
        logger.info("filing index already exists on disk at %s -- reusing", DEFAULT_FILING_INDEX_PATH)

    # ---- STEP 3: load BOTH snapshots back from disk, run screening TWICE ---
    def _run(label: str):
        loaded_prices = load_ohlcv_snapshot(DEFAULT_PRICE_SNAPSHOT_DIR)
        loaded_index = load_filing_index(DEFAULT_FILING_INDEX_PATH)
        assert loaded_prices is not None and loaded_index is not None
        filing_index, filing_report = loaded_index
        t0 = time.monotonic()
        summary = run_lazy_prices_screening(
            RUN_START,
            RUN_END,
            tickers=priced_tickers,
            filing_index=filing_index,
            filing_report=filing_report,
            price_frames=loaded_prices,
        )
        dt = time.monotonic() - t0
        logger.info(
            "[%s] finished in %.1fs, n_priced=%d, n_results=%d",
            label, dt, summary.n_priced_tickers, len(summary.results),
        )
        return summary, dt

    logger.info("=== RUN A: fresh load of both frozen snapshots from disk ===")
    summary_a, _dt_a = _run("A")
    logger.info("=== RUN B: SECOND fresh load of both frozen snapshots from disk ===")
    summary_b, _dt_b = _run("B")

    a_by_id = {r.pattern_id: r for r in summary_a.results}
    b_by_id = {r.pattern_id: r for r in summary_b.results}
    common = sorted(set(a_by_id) & set(b_by_id))
    logger.info("=== REPRODUCIBILITY CHECK: %d common specs ===", len(common))
    diffs = []
    for pid in common:
        ra, rb = a_by_id[pid], b_by_id[pid]
        d_sharpe = rb.sharpe_annualized - ra.sharpe_annualized
        d_dsr = rb.deflated_sharpe.dsr - ra.deflated_sharpe.dsr
        diffs.append((abs(d_sharpe), pid, ra.sharpe_annualized, rb.sharpe_annualized, d_sharpe, d_dsr))
    diffs.sort(reverse=True)
    for _, pid, sa, sb, ds, dd in diffs:
        logger.info("  %-32s A=%+.10f  B=%+.10f  delta_sharpe=%+.2e  delta_dsr=%+.2e", pid, sa, sb, ds, dd)
    max_abs = max((abs(d) for d, *_ in diffs), default=float("nan"))
    logger.info("MAX |delta Sharpe| across all %d common specs: %.2e", len(common), max_abs)

    target_a, target_b = a_by_id.get(TARGET_PATTERN), b_by_id.get(TARGET_PATTERN)
    all_exact = all(abs(d) == 0.0 for d, *_ in diffs)
    logger.info("ALL SPECS BIT-IDENTICAL (delta exactly 0.0): %s", all_exact)

    report_path = SCRATCH.parent / "research_runs" / "lazy_prices_ptit_fix_verification_2026-09-04.txt"
    lines = [
        "LAZY PRICES POINT-IN-TIME FIX -- VERIFICATION -- 2026-09-04",
        f"window {RUN_START.isoformat()}..{RUN_END.isoformat()}, {len(priced_tickers)} priced tickers",
        "Both runs loaded the FROZEN price snapshot and FROZEN filing index fresh from disk",
        "(DEFAULT_PRICE_SNAPSHOT_DIR / DEFAULT_FILING_INDEX_PATH) -- no live EDGAR or Yahoo calls.",
        "",
    ]
    if target_a and target_b:
        lines.append(
            f"registered spec {TARGET_PATTERN}: "
            f"RUN A Sharpe={target_a.sharpe_annualized:.10f} DSR={target_a.deflated_sharpe.dsr:.10f} | "
            f"RUN B Sharpe={target_b.sharpe_annualized:.10f} DSR={target_b.deflated_sharpe.dsr:.10f} | "
            f"delta_sharpe={target_b.sharpe_annualized - target_a.sharpe_annualized:.2e}"
        )
    lines.append(f"ALL {len(common)} SPECS BIT-IDENTICAL BETWEEN THE TWO DISK-ROUNDTRIP RUNS: {all_exact}")
    lines.append(f"MAX |delta Sharpe|: {max_abs:.2e}")
    lines.append("")
    lines.append("Full grid (A, B, delta_sharpe, delta_dsr):")
    for _, pid, sa, sb, ds, dd in diffs:
        lines.append(f"  {pid:32s} A={sa:+.10f}  B={sb:+.10f}  d_sharpe={ds:+.2e}  d_dsr={dd:+.2e}")
    report_path.write_text("\n".join(lines) + "\n")
    logger.info("wrote %s", report_path)

    # ---- persist to the real DB, not just this text file -------------------
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
                db, "lazy_prices_ptit_fix_verification", rows, run_tag=run_tag
            )
            logger.info("[%s] persisted %d rows (replaced %d) -- %s", run_tag, n, deleted, note)
        finally:
            db.close()

    _persist(
        "lazy_prices_ptit_fix_verification_A_2026-09-04", summary_a,
        "frozen-snapshot reproducibility check, run A",
    )
    _persist(
        "lazy_prices_ptit_fix_verification_B_2026-09-04", summary_b,
        "frozen-snapshot reproducibility check, run B",
    )

    return 0 if all_exact else 1


if __name__ == "__main__":
    sys.exit(main())
