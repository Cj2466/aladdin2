"""WHAT DOES lazy_prices ACTUALLY SHORT, AND WHAT DOES BORROWING IT COST?

The 2026-09-05 cost correction (39f7cb5) priced this family's short leg two
ways and called both of them assumptions rather than measurements:

  S2  every shorted name is general collateral      ->  34 bp/yr
  S3  every shorted name is a special               -> 430 bp/yr

borrow_cost.BorrowSchedule does not actually endorse either of those as a
description of a real book. Its own rule assigns a rate PER NAME from that
name's cross-sectional SHORT-INTEREST percentile -- both tails pay the
specials rate (D'Avolio's Fig. 1 deciles 9/10 plus Beneish/Lee/Nichols'
U-shape at the LOW end, driven by lendable supply), the middle 80% pays
general collateral -- and book_borrow_bps_per_year() exists precisely to
average that schedule over a real short leg. worst_case_bps_per_year() (S3)
is documented in that module as "the bound to quote when a family cannot
compute percentiles at all".

THIS SCRIPT COMPUTES THE PERCENTILES, so the family does not have to quote
the bound. It answers three questions with measurements rather than priors:

  Q1  Does lazy_prices' short leg -- the LOW-similarity "changers" quintile
      -- tilt toward heavily-shorted (hard-to-borrow) names, away from them,
      or neither? The registration's own text argues both directions are
      plausible: "changers" are distressed-adjacent (tilt toward), but the
      universe is S&P 500 large caps that D'Avolio p.273 says "are almost
      always general collateral" (tilt away).
  Q2  Given the measured composition, what does borrow_cost's OWN schedule
      charge this specific short leg?
  Q3  How stable is that across the 24 real formations?

THE BASELINE THAT MAKES Q1 READABLE. Under BorrowSchedule's default 10%
tails, ANY short leg drawn independently of short interest holds ~20% tail
names and therefore costs

    0.20 * 430 + 0.80 * 34 = 113.2 bp/yr

NOT 34. So S2 is not the "no tilt" answer -- it is the answer for a leg that
actively AVOIDS both tails, which is a strictly stronger claim than "this
family has nothing to do with short interest". 113.2 is the no-tilt number,
and the measurement below says which side of it this family lands on.

--------------------------------------------------------------------------
DATA, AND ITS HONEST LIMIT
--------------------------------------------------------------------------
The short-interest ratio panel is built by the SHORT-INTEREST FAMILY'S OWN
functions -- finra_short_interest_provider.fetch_observations_for_tickers,
sec_shares_outstanding_provider.fetch_share_counts, cross_sectional_short_
interest.build_point_in_time_share_count_frame and .build_short_interest_
panels -- not by anything reimplemented here. Its own point-in-time
contract (value visible only from FINRA's publication date, share count read
at the later of the two inputs' public dates) therefore applies unchanged.

COVERAGE IS SHORTER THAN THE BACKTEST WINDOW AND THAT IS DISCLOSED, NOT
PAPERED OVER. FINRA's free file starts 2017-12-29 and SEC's shares-
outstanding frames cache starts CY2017Q4, while this family's window opens
2015-01-07. Formations before SIR coverage begins are reported separately
and are NEVER silently folded into the average as if they were measured.

The percentile is taken WITHIN THIS FAMILY'S OWN ELIGIBLE S&P 500
CROSS-SECTION, not within the whole US market. That direction is
conservative: D'Avolio p.273 says S&P 500 constituents are almost always
general collateral, so the top decile of an S&P 500 panel contains far fewer
true specials than the top decile of the market-wide panel his fee schedule
was measured on. Charging it the specials rate overcharges, which is the
safe direction.

    ./venv/bin/python data/research_runs/run_lazy_prices_borrow_composition.py
"""

import json
import logging
import sys
from collections import Counter
from datetime import date

import numpy as np

from app.services.market_data.edgar_filing_text_provider import (
    EdgarFilingTextProvider,
    load_filing_index,
)
from app.services.market_data.edgar_xbrl_provider import EdgarXbrlProvider
from app.services.market_data.finra_short_interest_provider import (
    FinraShortInterestProvider,
)
from app.services.market_data.sec_shares_outstanding_provider import (
    SecSharesOutstandingProvider,
)
from app.services.market_data.yfinance_provider import load_ohlcv_snapshot
from app.services.research_lab.borrow_cost import (
    DEFAULT_SCHEDULE,
    GENERAL_COLLATERAL_BPS_PER_YEAR,
    HARD_TO_BORROW_BPS_PER_YEAR,
    cross_sectional_percentiles,
    financing_bps_for_long_short_book,
)
from app.services.research_lab.cross_sectional import (
    CrossSectionalConfig,
    CrossSectionalData,
    run_cross_sectional_backtest,
)
from app.services.research_lab.cross_sectional_lazy_prices import (
    DEFAULT_FILING_INDEX_PATH,
    DEFAULT_PRICE_SNAPSHOT_DIR,
    LAZY_PRICES_FAMILY,
    LAZY_PRICES_FILING_WARMUP_DAYS,
    build_inverse_vol_basis,
    build_similarity_observations,
    build_similarity_panel,
)
from app.services.research_lab.cross_sectional_short_interest import (
    SHARES_MAX_STALENESS_DAYS,
    SHORT_INTEREST_CYCLE_FETCH_START,
    build_point_in_time_share_count_frame,
    build_short_interest_panels,
)
from app.services.research_lab.sp500_membership_history import MEMBERSHIP_DATA_START
from app.services.research_lab.spread_estimator import (
    build_calibrated_half_spread_frame,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("borrow_composition")

RUN_DATE = "2026-09-05"
START = MEMBERSHIP_DATA_START
END = date(2026, 8, 31)
REGISTERED_SPEC_ID = "lazy_jaccard_full_h126_ivol"
OUT_JSON = "data/research_runs/lazy_prices_borrow_composition_2026-09-05.json"

# The no-tilt reference: a short leg independent of short interest holds one
# tail decile at each end, i.e. 2 * tail_fraction of its names at the
# specials rate. Computed from the schedule rather than hardcoded.
NO_TILT_TAIL_SHARE = 2.0 * DEFAULT_SCHEDULE.tail_fraction
NO_TILT_BPS = (
    NO_TILT_TAIL_SHARE * HARD_TO_BORROW_BPS_PER_YEAR
    + (1.0 - NO_TILT_TAIL_SHARE) * GENERAL_COLLATERAL_BPS_PER_YEAR
)


def main() -> None:
    if not DEFAULT_PRICE_SNAPSHOT_DIR.exists():
        sys.exit(f"frozen price snapshot missing at {DEFAULT_PRICE_SNAPSHOT_DIR}")
    frames = load_ohlcv_snapshot(DEFAULT_PRICE_SNAPSHOT_DIR)
    if frames is None:
        sys.exit(f"no readable snapshot manifest under {DEFAULT_PRICE_SNAPSHOT_DIR}")
    close = frames["close"]
    log.info("price snapshot: %d tickers %s..%s", len(close.columns), close.index[0].date(),
             close.index[-1].date())

    loaded = load_filing_index(DEFAULT_FILING_INDEX_PATH)
    if loaded is None:
        sys.exit(f"frozen filing index missing at {DEFAULT_FILING_INDEX_PATH}")
    filing_index, _report = loaded
    warmup_floor = START.toordinal() - LAZY_PRICES_FILING_WARMUP_DAYS
    trimmed = {
        t: [f for f in fl if f.filing_date.toordinal() >= warmup_floor]
        for t, fl in filing_index.items()
        if t in close.columns
    }

    # --- the family's own (jaccard, full) panel, its own way ---------------
    text_provider = EdgarFilingTextProvider()
    observations, _sim_report = build_similarity_observations(
        text_provider, trimmed, metrics=("jaccard",), scopes=("full",)
    )
    panel, _ages, _unusable = build_similarity_panel(close, observations[("jaccard", "full")])
    log.info("jaccard/full panel: %d cells scored", int(panel.notna().to_numpy().sum()))

    # --- the registered spec's REAL formations ----------------------------
    spec = next(s.spec for s in LAZY_PRICES_FAMILY if s.spec.pattern_id == REGISTERED_SPEC_ID)
    calibrated, calibration = build_calibrated_half_spread_frame(
        frames["open"], frames["high"], frames["low"], close, calibration_start=START
    )
    log.info("calibration: %s", calibration.summary())
    config = CrossSectionalConfig(cost_model="edge_spread")
    config.formation_start = START
    replay = run_cross_sectional_backtest(
        CrossSectionalData(
            close=close,
            fundamental_signal=panel,
            half_spread=calibrated,
            leg_weight_basis=build_inverse_vol_basis(close),
        ),
        spec,
        config,
    )
    formed = [f for f in replay.formations if f.skipped_reason is None]
    log.info("replay status=%s formations=%d", replay.status, len(formed))
    if not formed:
        sys.exit("no formations — nothing to measure")

    # --- the short-interest RATIO panel, by the SI family's own path ------
    priced = list(close.columns)
    finra = FinraShortInterestProvider()
    si_obs, finra_diag = finra.fetch_observations_for_tickers(
        priced, SHORT_INTEREST_CYCLE_FETCH_START, END
    )
    log.info("FINRA cycles resolved: %d", finra_diag.n_cycles_resolved)

    cik_map = EdgarXbrlProvider().get_ticker_cik_map()
    resolvable = {t: cik_map[t] for t in priced if t in cik_map}
    log.info("CIK-resolvable: %d of %d priced", len(resolvable), len(priced))
    share_obs, _share_diag = SecSharesOutstandingProvider().fetch_share_counts(
        resolvable, START, END, missing_from_map=[t for t in priced if t not in cik_map]
    )
    share_frame, no_shares = build_point_in_time_share_count_frame(
        close, share_obs, max_staleness_days=SHARES_MAX_STALENESS_DAYS
    )
    ratio_frame, _dtc, panel_diag = build_short_interest_panels(close, si_obs, share_frame)
    log.info(
        "SIR panel: %d cells, %d tickers with no share count, %d never ranked",
        int(ratio_frame.notna().to_numpy().sum()),
        len(no_shares),
        len(panel_diag.tickers_never_ranked),
    )
    covered = ratio_frame.notna().any(axis=1)
    first_covered = ratio_frame.index[covered][0] if covered.any() else None
    log.info("SIR coverage begins %s", first_covered)

    # --- per formation: what does the schedule charge this short leg? -----
    per_formation = []
    for f in formed:
        row = ratio_frame.loc[f.date] if f.date in ratio_frame.index else None
        short_names = list(f.short_tickers)
        long_names = list(f.long_tickers)
        record = {
            "date": f.date.date().isoformat(),
            "n_short": len(short_names),
            "n_long": len(long_names),
        }
        if row is None or not row.notna().any():
            record["sir_covered"] = False
            per_formation.append(record)
            continue
        # Percentiles over the ELIGIBLE cross-section this formation actually
        # ranked (long leg + short leg + everything in between that carried a
        # similarity value on this date), restricted to names with a SIR.
        eligible = panel.loc[f.date].dropna().index
        cross_section = row.reindex(eligible).dropna()
        if len(cross_section) < 20:
            record["sir_covered"] = False
            record["n_cross_section"] = len(cross_section)
            per_formation.append(record)
            continue
        pct = cross_sectional_percentiles(cross_section)
        short_pct = pct.reindex(short_names)
        long_pct = pct.reindex(long_names)
        rates = DEFAULT_SCHEDULE.rate_for_percentiles(short_pct)
        n_measured = int(short_pct.notna().sum())
        lo, hi = DEFAULT_SCHEDULE.tail_fraction, 1.0 - DEFAULT_SCHEDULE.tail_fraction
        sv = short_pct.dropna().to_numpy()
        lv = long_pct.dropna().to_numpy()
        record.update(
            {
                "sir_covered": True,
                "n_cross_section": len(cross_section),
                "n_short_with_sir": n_measured,
                "short_sir_coverage": n_measured / len(short_names) if short_names else 0.0,
                # Composition, measured on the names that HAVE a SIR.
                "short_tail_share": float(((sv <= lo) | (sv >= hi)).mean()) if sv.size else None,
                "short_high_tail_share": float((sv >= hi).mean()) if sv.size else None,
                "short_low_tail_share": float((sv <= lo).mean()) if sv.size else None,
                "long_tail_share": float(((lv <= lo) | (lv >= hi)).mean()) if lv.size else None,
                "short_median_sir_pct": float(np.median(sv)) if sv.size else None,
                "long_median_sir_pct": float(np.median(lv)) if lv.size else None,
                # What the schedule charges. Two readings of the names with NO
                # SIR observation: schedule_default follows borrow_cost's own
                # documented NaN->GC rule; measured_only ignores them.
                "book_bps_schedule_default": float(rates.mean()),
                "book_bps_measured_only": (
                    float(DEFAULT_SCHEDULE.rate_for_percentiles(short_pct.dropna()).mean())
                    if n_measured
                    else None
                ),
            }
        )
        per_formation.append(record)

    covered_rows = [r for r in per_formation if r.get("sir_covered")]
    if not covered_rows:
        sys.exit("no formation has SIR coverage — cannot measure composition")

    def agg(key):
        vals = [r[key] for r in covered_rows if r.get(key) is not None]
        return {
            "n": len(vals),
            "mean": float(np.mean(vals)),
            "median": float(np.median(vals)),
            "min": float(np.min(vals)),
            "max": float(np.max(vals)),
        }

    summary = {
        "run_date": RUN_DATE,
        "spec": REGISTERED_SPEC_ID,
        "window": [START.isoformat(), END.isoformat()],
        "n_formations_total": len(formed),
        "n_formations_sir_covered": len(covered_rows),
        "sir_coverage_first_date": str(first_covered.date()) if first_covered is not None else None,
        "schedule": {
            "general_collateral_bps": GENERAL_COLLATERAL_BPS_PER_YEAR,
            "hard_to_borrow_bps": HARD_TO_BORROW_BPS_PER_YEAR,
            "tail_fraction": DEFAULT_SCHEDULE.tail_fraction,
            "no_tilt_tail_share": NO_TILT_TAIL_SHARE,
            "no_tilt_book_bps": NO_TILT_BPS,
        },
        "short_tail_share": agg("short_tail_share"),
        "short_high_tail_share": agg("short_high_tail_share"),
        "short_low_tail_share": agg("short_low_tail_share"),
        "long_tail_share": agg("long_tail_share"),
        "short_median_sir_pct": agg("short_median_sir_pct"),
        "long_median_sir_pct": agg("long_median_sir_pct"),
        "book_bps_schedule_default": agg("book_bps_schedule_default"),
        "book_bps_measured_only": agg("book_bps_measured_only"),
        "short_sir_coverage": agg("short_sir_coverage"),
        "per_formation": per_formation,
    }

    for key in ("book_bps_schedule_default", "book_bps_measured_only"):
        b = summary[key]["mean"]
        summary[key]["implied_financing_bps_per_year"] = financing_bps_for_long_short_book(b)

    counts = Counter(r.get("sir_covered", False) for r in per_formation)
    log.info("formations: %s", dict(counts))
    log.info(
        "short-leg tail share: mean %.4f (no-tilt baseline %.4f); long-leg %.4f",
        summary["short_tail_share"]["mean"],
        NO_TILT_TAIL_SHARE,
        summary["long_tail_share"]["mean"],
    )
    log.info(
        "book borrow bps/yr: schedule-default mean %.2f (range %.2f..%.2f), measured-only %.2f",
        summary["book_bps_schedule_default"]["mean"],
        summary["book_bps_schedule_default"]["min"],
        summary["book_bps_schedule_default"]["max"],
        summary["book_bps_measured_only"]["mean"],
    )
    log.info(
        "=> financing_bps_per_year (B/2): schedule-default %.4f, measured-only %.4f",
        summary["book_bps_schedule_default"]["implied_financing_bps_per_year"],
        summary["book_bps_measured_only"]["implied_financing_bps_per_year"],
    )

    with open(OUT_JSON, "w") as fh:
        json.dump(summary, fh, indent=2, default=str)
    log.info("wrote %s", OUT_JSON)


if __name__ == "__main__":
    main()
