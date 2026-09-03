"""THE DECISIVE TEST OF THE "XOM CIK-FIX EXPLAINS THE lazy_prices REPRODUCTION
DRIFT" HYPOTHESIS (2026-09-04).

BACKGROUND. 0c576bb registered lazy_jaccard_full_h126_ivol at Sharpe +0.6035 /
DSR 0.7540 (run_tag lazy_prices_2026-09-01). Commit 82b69fa (run_preservation_
score.py, 2026-09-04 00:51 +07) rebuilt the family with the SAME fixed window
(MEMBERSHIP_DATA_START..2026-09-01, matching the registration exactly, not
today's date) and reproduced the registered spec at only +0.5498 -- a drop of
-0.0537 -- with 7 other lazy_prices `full`-arm specs down 0.05-0.10 the same
direction, while every `rf`/`mda`-arm spec reproduced inside tolerance. That
commit explicitly flagged the 2026-09-02 XOM CIK-mapping fix (dcdf864 /
401d98d, "resolve successor-shell CIKs to their predecessor") as the "leading
candidate explanation" and labelled it UNVERIFIED -- diffing panels was not
done.

WHY THIS IS SUSPICIOUS BEFORE ANY CODE RUNS, stated so the test is not run
blind. Reading dcdf864 and 401d98d shows the fix touched exactly THREE
provider/family files: edgar_xbrl_provider.py, cross_sectional_quality.py,
cross_sectional_quality_neutral.py, cross_sectional_asset_growth.py. It did
NOT touch edgar_filing_text_provider.py -- the provider lazy_prices uses (a
"genuinely NEW fetch path, not an extension of edgar_xbrl_provider.py", per
that module's own docstring). Two commits made the SAME evening as the fix
(52634ac, 34df35d) already disclosed this in the lazy_prices run report:
"edgar_filing_text_provider.py shares the same successor-shell CIK resolution
bug ... Deliberately left unfixed (out of scope for that change, a different
provider used only by this family)." a7957eb (2026-09-03 23:11, an hour and a
half before 82b69fa) rebuilt the SAME real panel for an unrelated confound
test and reconfirmed in its own limits section: "XOM IS STILL EXCLUDED, by
the disclosed and still-unfixed CIK gap in edgar_filing_text_provider.py."
And reading edgar_filing_text_provider.py itself (build_filing_index /
get_ticker_cik_map) confirms there is no successor-CIK resolution logic of
any kind in this module -- it is a straight ticker->CIK passthrough against
SEC's live company_tickers.json, with none of edgar_xbrl_provider.resolve_
company_facts' fallback-probe machinery. So the fix, wherever it lives, was
never wired to the code path this family calls.

Taken together this is strong PRIOR evidence the XOM hypothesis is wrong for
THIS family -- but the task requires the decisive empirical test rather than
resting on docstrings, so this script runs it: the family's own real
production entry point (run_lazy_prices_screening -> screen_lazy_prices_family
-> run_cross_sectional_backtest, no logic reimplemented), on the exact same
window 82b69fa used (MEMBERSHIP_DATA_START..2026-09-01), reusing the existing
~924MB filing-text disk cache (documents are immutable per accession number,
so this changes nothing about correctness), twice:

  RUN A  -- current main, full point-in-time universe, unchanged.
  RUN B  -- the IDENTICAL universe with "XOM" stripped before the filing
            index is built, simulating "XOM properly excluded" as a
            controlled ablation. (If XOM already contributes ~0 filings to
            the "full" panel, A and B should be ~identical -- confirming
            XOM was never the free variable here, one way or the other.)

Also recorded, cheaply, before either run: XOM's CURRENT live CIK resolution
through this exact provider (get_ticker_cik_map + list_filings), so the "is
XOM actually still excluded today" claim is fresh evidence, not a re-quote of
a two-day-old docstring.

Run from backend/ with ./venv/bin/python data/research_runs/run_xom_hypothesis_test.py
"""

from __future__ import annotations

import logging
import math
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("xom_hypothesis_test")

# Reuse the MAIN checkout's already-warmed EDGAR filing-text cache (924MB,
# 7733 files as of 2026-09-04) rather than re-fetching ~7,800 documents from
# a cold cache in this worktree. Documents are immutable per accession number
# (edgar_filing_text_provider's own docstring), so reading -- and appending
# any genuinely missing ones -- from the shared cache changes no bytes of any
# existing cached document and is pure data reuse, not a code change.
MAIN_REPO_CACHE_DIR = Path(
    "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend/data/edgar_filing_text/v1"
)

SCRATCH = Path(__file__).parent
END_DATE_STR = "2026-09-01"  # identical to 82b69fa's own reproduction window
RUN_TAG_WITH = "lazy_prices_xom_included_2026-09-04"
RUN_TAG_WITHOUT = "lazy_prices_xom_excluded_2026-09-04"
TARGET_PATTERN = "lazy_jaccard_full_h126_ivol"


def _section(title: str) -> None:
    logger.info("=" * 78)
    logger.info(title)
    logger.info("=" * 78)


def main() -> int:
    from datetime import date

    from app.services.market_data.edgar_filing_text_provider import (
        EdgarFilingTextProvider,
    )
    from app.services.market_data.yfinance_provider import YFinanceProvider
    from app.services.research_lab.cross_sectional_lazy_prices import (
        LAZY_PRICES_FORMS,
        run_lazy_prices_screening,
    )
    from app.services.research_lab.sp500_membership_history import (
        MEMBERSHIP_DATA_START,
        get_universe_over,
    )

    end = date.fromisoformat(END_DATE_STR)

    # --- 0. FRESH, LIVE CHECK: what does XOM resolve to RIGHT NOW through
    # THIS family's own provider? Cheap (2-3 requests), done before anything
    # else so it cannot be biased by what the backtest later finds. ---------
    _section("STEP 0 -- live XOM CIK resolution through edgar_filing_text_provider TODAY")
    probe = EdgarFilingTextProvider(cache_dir=MAIN_REPO_CACHE_DIR)
    cik_map = probe.get_ticker_cik_map()
    xom_cik = cik_map.get("XOM")
    logger.info("XOM resolves to CIK=%r via SEC's LIVE company_tickers.json (fetched just now)", xom_cik)
    xom_filings: list = []
    xom_entity_name = None
    if xom_cik is not None:
        try:
            xom_filings, _n_pages = probe.list_filings(xom_cik, forms=LAZY_PRICES_FORMS)
        except Exception as exc:  # noqa: BLE001 -- diagnostic probe, report and continue
            logger.warning("list_filings(XOM CIK=%s) failed: %s", xom_cik, exc)
            xom_filings = []
        # Peek at the raw submissions payload for the entity name and total
        # filing count, purely diagnostic (not used by the family itself).
        try:
            raw = probe._get(
                f"https://data.sec.gov/submissions/CIK{xom_cik:010d}.json", as_json=True
            )
            assert isinstance(raw, dict)
            xom_entity_name = raw.get("name")
            all_forms = raw.get("filings", {}).get("recent", {}).get("form", [])
            logger.info(
                "CIK%010d entityName=%r, %d filings in `recent` (all forms), "
                "%d of them 10-K/10-Q",
                xom_cik,
                xom_entity_name,
                len(all_forms),
                len(xom_filings),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("submissions peek for CIK=%s failed: %s", xom_cik, exc)
    logger.info(
        "XOM periodic (10-K/10-Q) filings visible to lazy_prices's provider TODAY: %d",
        len(xom_filings),
    )
    if len(xom_filings) < 2:
        logger.info(
            "FEWER THAN 2 periodic filings means XOM can form ZERO same-type consecutive "
            "pairs -- i.e. XOM contributes NOTHING to any lazy_prices similarity panel "
            "today, exactly as disclosed in lazy_prices_2026-09-01.txt section 9 and "
            "reconfirmed in a7957eb's 2026-09-03 23:11 rebuild."
        )

    # --- 1. the universe both runs will share, computed ONCE -----------------
    _section("STEP 1 -- point-in-time universe (static membership data, no network)")
    universe = get_universe_over(MEMBERSHIP_DATA_START, end)
    universe_without_xom = [t for t in universe if t != "XOM"]
    logger.info(
        "universe size=%d; 'XOM' present=%s; universe_without_xom size=%d (removed %d ticker(s))",
        len(universe),
        "XOM" in universe,
        len(universe_without_xom),
        len(universe) - len(universe_without_xom),
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
        )
        dt = time.monotonic() - t0
        logger.info("[%s] run_lazy_prices_screening finished in %.1fs", label, dt)
        logger.info(
            "[%s] universe_size=%d n_priced=%d filing_report: requested=%d "
            "cik_resolved=%d indexed=%d filings_listed=%d unresolved=%d failed=%d",
            label,
            summary.universe_size,
            summary.n_priced_tickers,
            summary.filing_report.n_tickers_requested,
            summary.filing_report.n_tickers_cik_resolved,
            summary.filing_report.n_tickers_indexed,
            summary.filing_report.n_filings_listed,
            len(summary.filing_report.unresolved_tickers),
            len(summary.filing_report.failed_tickers),
        )
        xom_in_unresolved = "XOM" in summary.filing_report.unresolved_tickers
        xom_in_failed = "XOM" in summary.filing_report.failed_tickers
        logger.info(
            "[%s] XOM in input tickers=%s, in unresolved_tickers=%s, in failed_tickers=%s",
            label,
            "XOM" in tickers,
            xom_in_unresolved,
            xom_in_failed,
        )
        return summary, dt

    _section("STEP 2 -- RUN A: current main, full universe (XOM included per the live map)")
    summary_a, dt_a = _run("A(with_XOM)", universe)

    _section("STEP 3 -- RUN B: identical universe, XOM manually stripped (simulated pre-fix / fixed exclusion)")
    summary_b, dt_b = _run("B(without_XOM)", universe_without_xom)

    # --- 4. compare the registered spec, and the whole grid -------------------
    _section("STEP 4 -- COMPARISON: does excluding XOM move the registered spec?")

    def _find(summary, pattern_id: str):
        for r in summary.results:
            if r.pattern_id == pattern_id:
                return r
        return None

    row_a = _find(summary_a, TARGET_PATTERN)
    row_b = _find(summary_b, TARGET_PATTERN)
    if row_a is None or row_b is None:
        logger.error("could not find %s in one of the two runs' results", TARGET_PATTERN)
        return 1

    logger.info(
        "REGISTERED SPEC %s\n"
        "  committed (2026-09-01, run_tag lazy_prices_2026-09-01): Sharpe +0.6035  DSR 0.7540\n"
        "  82b69fa rebuild  (2026-09-04 00:51, same window, no XOM ablation): Sharpe +0.5498\n"
        "  RUN A here (with XOM, same window)   : Sharpe %+.4f  DSR %.4f\n"
        "  RUN B here (XOM manually excluded)   : Sharpe %+.4f  DSR %.4f\n"
        "  delta (B - A), the XOM ablation's OWN marginal effect : Sharpe %+.4f  DSR %+.4f",
        TARGET_PATTERN,
        row_a.sharpe_annualized,
        row_a.deflated_sharpe.dsr,
        row_b.sharpe_annualized,
        row_b.deflated_sharpe.dsr,
        row_b.sharpe_annualized - row_a.sharpe_annualized,
        row_b.deflated_sharpe.dsr - row_a.deflated_sharpe.dsr,
    )

    # Full 36-spec diff, so a reader can see whether ANY spec moved beyond
    # floating point / formation-membership noise from dropping one ticker.
    by_id_a = {r.pattern_id: r for r in summary_a.results}
    by_id_b = {r.pattern_id: r for r in summary_b.results}
    all_ids = sorted(set(by_id_a) | set(by_id_b))
    logger.info("FULL GRID -- Sharpe(A) vs Sharpe(B), sorted by |delta| descending:")
    diffs = []
    for pid in all_ids:
        ra, rb = by_id_a.get(pid), by_id_b.get(pid)
        sa = ra.sharpe_annualized if ra else float("nan")
        sb = rb.sharpe_annualized if rb else float("nan")
        d = (sb - sa) if (ra and rb) else float("nan")
        diffs.append((abs(d) if math.isfinite(d) else -1.0, pid, sa, sb, d))
    diffs.sort(reverse=True)
    for _, pid, sa, sb, d in diffs:
        logger.info("  %-32s A=%+.4f  B=%+.4f  delta=%+.4f", pid, sa, sb, d)

    max_abs_delta = max((abs(d) for _, _, _, _, d in diffs if math.isfinite(d)), default=float("nan"))
    logger.info("MAX |delta Sharpe| across all 36 specs from the XOM-only ablation: %.4f", max_abs_delta)

    # --- 5. persist both runs' full grids, per this project's standing rule
    # that every computed trial reaches a real table, not just a text file. --
    _section("STEP 5 -- persisting both probe runs to cross_sectional_trial_results")
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
                db, "lazy_prices_xom_hypothesis_test", rows, run_tag=run_tag
            )
            logger.info("[%s] persisted %d rows (replaced %d earlier rows) -- %s", run_tag, n, deleted, note)
        finally:
            db.close()

    _persist(
        RUN_TAG_WITH,
        summary_a,
        "RUN A: current main, full point-in-time universe, XOM resolved however SEC's live map says today",
    )
    _persist(
        RUN_TAG_WITHOUT,
        summary_b,
        "RUN B: identical universe with XOM manually stripped before filing-index build (ablation)",
    )

    # --- 6. write a flat text report -------------------------------------
    report_path = SCRATCH / "lazy_prices_xom_hypothesis_test_2026-09-04.txt"
    lines = []
    lines.append("XOM CIK-FIX HYPOTHESIS TEST FOR lazy_jaccard_full_h126_ivol -- 2026-09-04")
    lines.append("=" * 78)
    lines.append(f"XOM live CIK today: {xom_cik} entityName={xom_entity_name!r}")
    lines.append(f"XOM periodic (10-K/10-Q) filings visible today: {len(xom_filings)}")
    lines.append("")
    lines.append(f"Window: {MEMBERSHIP_DATA_START.isoformat()}..{end.isoformat()} (== 82b69fa's own window)")
    lines.append(f"Universe size: {len(universe)}; without XOM: {len(universe_without_xom)}")
    lines.append("")
    lines.append(f"{TARGET_PATTERN}:")
    lines.append("  committed (2026-09-01)                 : Sharpe +0.6035  DSR 0.7540")
    lines.append("  82b69fa rebuild (2026-09-04 00:51)      : Sharpe +0.5498  DSR (not separately reported here)")
    lines.append(f"  RUN A here, WITH XOM   ({dt_a:.0f}s)        : Sharpe {row_a.sharpe_annualized:+.4f}  DSR {row_a.deflated_sharpe.dsr:.4f}")
    lines.append(f"  RUN B here, WITHOUT XOM ({dt_b:.0f}s)       : Sharpe {row_b.sharpe_annualized:+.4f}  DSR {row_b.deflated_sharpe.dsr:.4f}")
    lines.append(f"  delta from excluding XOM (B - A)        : Sharpe {row_b.sharpe_annualized - row_a.sharpe_annualized:+.4f}  DSR {row_b.deflated_sharpe.dsr - row_a.deflated_sharpe.dsr:+.4f}")
    lines.append(f"  MAX |delta Sharpe| across all 36 specs from the XOM-only ablation: {max_abs_delta:.4f}")
    lines.append("")
    lines.append("Full grid:")
    for _, pid, sa, sb, d in diffs:
        lines.append(f"  {pid:32s} A={sa:+.4f}  B={sb:+.4f}  delta={d:+.4f}")
    report_path.write_text("\n".join(lines) + "\n")
    logger.info("wrote report to %s", report_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
