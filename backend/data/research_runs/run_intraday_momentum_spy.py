"""Production run for the intraday_momentum_spy family.

Reads the cached SPY 1-minute bars (data/research_runs/fetch_spy_1min_bars.py),
screens the 8 pre-registered specs at all four cost arms, persists one trial row
per spec on the VERDICT arm to cross_sectional_trial_results, verifies the write
by reading it back, and writes the run report.

Persistence is the separate second call that cross_sectional_persistence.py's
docstring prescribes -- run the screen, then persist -- never a hidden side
effect of the screen.
"""

from __future__ import annotations

import json
import pickle
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.config import _main_checkout_backend_dir
from app.db import SessionLocal
from app.services.research_lab.cross_sectional_persistence import (
    describe_configured_database,
    persist_cross_sectional_trial_results,
    verify_persisted_trial_results,
)
from app.services.research_lab.dsr_power import POWER_FLOOR, dsr_power_report
from app.services.research_lab.intraday_momentum_spy import (
    COST_ARMS,
    FAMILY_KEY,
    NEWEY_WEST_RULE,
    PAPER_SIGN_RULE_SHARPE,
    SCOPING_MEMO_OPTIMAL_SCALING_SHARPE,
    SCREENING_FLOOR,
    VALIDATED_EDGE_BAR,
    directional_hit_rate,
    predictive_regression,
    run_intraday_momentum_screening,
)

RUN_TAG = "intraday_momentum_spy_2026-09-09"
OUT_DIR = BACKEND / "data" / "research_runs" / "intraday_momentum_spy_2026-09-09"
CACHE = _main_checkout_backend_dir(BACKEND) / "data" / "spy_1min_bars"


def _load(name: str) -> pd.DataFrame:
    path = CACHE / name
    if not path.is_file():
        raise SystemExit(f"{path} missing -- run data/research_runs/fetch_spy_1min_bars.py first")
    with path.open("rb") as fh:
        return pickle.load(fh)


def feed_check(minute: pd.DataFrame, daily: pd.DataFrame) -> dict:
    """PREREGISTRATION section 2c: sum the 1-minute volume per session and
    compare against the 1Day bar's volume for the same session."""
    mv = minute["volume"].groupby(pd.DatetimeIndex(minute.index).normalize()).sum()
    dv = daily["volume"].copy()
    dv.index = pd.DatetimeIndex(dv.index).normalize()
    common = mv.index.intersection(dv.index)
    ratio = mv[common] / dv[common]
    return {
        "n_sessions_compared": len(common),
        "minute_sum_median_shares": float(mv[common].median()),
        "daily_bar_median_shares": float(dv[common].median()),
        "ratio_median": float(ratio.median()),
        "ratio_mean": float(ratio.mean()),
        "ratio_min": float(ratio.min()),
        "ratio_max": float(ratio.max()),
        "verdict": (
            "CONSOLIDATED (SIP)"
            if float(mv[common].median()) > 2e7
            else "SUSPECT -- volume far below consolidated SPY levels"
        ),
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    minute, daily = _load("SPY_1Min.pkl"), _load("SPY_1Day.pkl")
    feed = feed_check(minute, daily)

    summary = run_intraday_momentum_screening(minute)
    audit = summary.audit
    best = summary.best_candidate()
    placebo = summary.best_placebo()
    assert best is not None and placebo is not None

    # The power block uses the REALIZED sigma_sr from this run and the paper's
    # own Table 5 Sharpe for the exact rule tested. Both bars.
    power_by_bar = {
        bar: dsr_power_report(
            claimed_sharpe_annualized=PAPER_SIGN_RULE_SHARPE,
            threshold=bar,
            n_observations=best.n_trading_days,
            n_trials=summary.n_local,
            sigma_sr_annualized=summary.sigma_sr_annualized or 0.0,
            periods_per_year=252.0,
        )
        for bar in (VALIDATED_EDGE_BAR, SCREENING_FLOOR)
    }
    # Secondary scenario only: the scoping memo's optimally-scaled upper bound.
    power_memo = dsr_power_report(
        claimed_sharpe_annualized=SCOPING_MEMO_OPTIMAL_SCALING_SHARPE,
        threshold=VALIDATED_EDGE_BAR,
        n_observations=best.n_trading_days,
        n_trials=summary.n_local,
        sigma_sr_annualized=summary.sigma_sr_annualized or 0.0,
        periods_per_year=252.0,
    )

    # ---- persist the VERDICT arm's trials -------------------------------
    with SessionLocal() as db:
        written = persist_cross_sectional_trial_results(
            db, FAMILY_KEY, summary.baseline_results(), run_tag=RUN_TAG
        )
        read_back = verify_persisted_trial_results(db, RUN_TAG, written, family_key=FAMILY_KEY)

    regressions: dict = {}
    hit_rates: dict = {}
    lines: list[str] = []
    w = lines.append
    w("=" * 78)
    w("INTRADAY MOMENTUM ON SPY (intraday_momentum_spy) -- run report")
    w(f"run_tag {RUN_TAG}   written {datetime.now(UTC).isoformat()}")
    w("=" * 78)
    w("")
    w("Gao, Han, Li & Zhou, 'Intraday Momentum: The First Half-Hour Return Predicts the")
    w("Last Half-Hour Return', SSRN 2440866, OCTOBER 2014 DRAFT (published as 'Market")
    w("intraday momentum', JFE 129(2) 2018, 394-414 -- the PUBLISHED version's figures")
    w("are UNVERIFIED, paywalled; every paper number below is from the draft).")
    w("")
    w("*** THE ENTIRE SAMPLE HERE IS OUT-OF-SAMPLE RELATIVE TO THE PAPER. ***")
    w("The paper's sample is 1993-02-01..2013-12-31. This sample starts 2016-01-04.")
    w("ZERO OVERLAP. This is not a replication and cannot be one.")
    w("")
    w("Pre-registration: PREREGISTRATION.md (commit 1532641, before any backtest) and")
    w("ADDENDUM_01_DATA_AND_COST.md (commit dd07220, after the data audit, before any")
    w("strategy return -- it records that the pre-registered EDGE cost procedure FAILED")
    w("its own sanity check and what replaced it).")
    w("")
    w("-" * 78)
    w("1. DATA")
    w("-" * 78)
    w(f"SPY 1-minute SIP bars: {len(minute):,}  {minute.index[0]} .. {minute.index[-1]}")
    w(f"SPY 1-day bars:        {len(daily):,}")
    w(f"calendar sessions seen:            {audit.n_sessions}")
    w(f"usable sessions (U1+U2+U3):        {audit.n_usable}")
    w(f"  dropped, <380 bars (U3):         {len(audit.dropped_too_few_bars)}")
    w(f"  dropped, last bar < 15:55 (U2):  {len(audit.dropped_late_bar)}")
    w(f"  dropped, incomplete block (U1):  {len(audit.dropped_incomplete_blocks)}")
    w(f"  dropped, no usable predecessor:  {len(audit.dropped_no_previous)}")
    w(f"TRADING DAYS IN THE SAMPLE:        {audit.n_traded_days}")
    w("")
    w("U3 drops (date list):")
    for d in audit.dropped_too_few_bars:
        w(f"  {d}")
    w("U2 drops: " + (", ".join(audit.dropped_late_bar) or "(none)"))
    w("U1 drops: " + (", ".join(audit.dropped_incomplete_blocks) or "(none)"))
    w("no-predecessor drops: " + (", ".join(audit.dropped_no_previous) or "(none)"))
    w("")
    w("NOTE, disclosed because it cuts AGAINST the paper: the U3 380-bar floor drops")
    w("2020-03-09/12/16/18, the four COVID circuit-breaker days (376 bars each), which")
    w("are the most volatile days in the sample and exactly where the paper's Table 6")
    w("says the effect is strongest. The rule was pre-registered before the data was")
    w("examined and is NOT being changed; a sensitivity re-run admitting them would be")
    w("a post-hoc rule change made after seeing which days it excludes.")
    w("")
    w("-" * 78)
    w("2. FEED CHECK (PREREGISTRATION section 2c)")
    w("-" * 78)
    for k, v in feed.items():
        w(f"  {k}: {v:,.4f}" if isinstance(v, float) else f"  {k}: {v}")
    w("")
    w("Decisive evidence is the ABSOLUTE LEVEL, not the ratio: IEX is ~2-3% of")
    w("consolidated US equity volume, so an IEX-only minute-sum would have been one to")
    w("two orders of magnitude below what came back. The residual shortfall vs the 1Day")
    w("bar is the excluded pre/post-market volume plus the 16:00 closing-auction print")
    w("(the minute frame is filtered to bar-starts in [09:30,16:00)).")
    w("WHY IT DOES NOT MATTER HERE: every quantity tested is a RATIO OF TWO PRINTS, and")
    w("prints sit inside the NBBO, so a thin feed would move a half-hour return by at")
    w("most a fraction of a one-cent spread on a $200-700 instrument. It WOULD have")
    w("mattered for any volume- or auction-based construction; this family uses neither.")
    w("")
    w("-" * 78)
    w("3. RESULTS -- every spec, every cost arm (annualized Sharpe on NET daily returns)")
    w("-" * 78)
    header = f"{'spec_id':<30}" + "".join(f"{a.key:>14}" for a in COST_ARMS)
    w(header)
    w("-" * len(header))
    order = [r.spec_id for r in summary.results_by_arm["cost_free"]]
    for spec_id in order:
        row = f"{spec_id:<30}"
        for arm in COST_ARMS:
            r = next(x for x in summary.results_by_arm[arm.key] if x.spec_id == spec_id)
            row += f"{r.sharpe_annualized:>14.4f}"
        flag = "  [CONTROL]" if "placebo" in spec_id else ""
        w(row + flag)
    w("")
    w("one-way bps per arm: " + ", ".join(f"{a.key}={a.one_way_bps}" for a in COST_ARMS))
    w("")
    w("-" * 78)
    w("4. THE VERDICT ARM (baseline, 1.0 bp one-way = 2 crossings/traded day)")
    w("-" * 78)
    for r in summary.baseline_results():
        w("")
        w(f"  {r.spec_id}{'  [PRE-REGISTERED CONTROL]' if r.is_control else ''}")
        w(f"    net Sharpe (ann.)      {r.sharpe_annualized:+.4f}")
        w(f"    gross Sharpe (ann.)    {r.gross_sharpe_annualized:+.4f}")
        w(f"    net ann. return        {r.annualized_return * 100:+.4f}%")
        w(f"    ann. volatility        {r.annualized_volatility * 100:.4f}%")
        w(f"    success rate           {'n/a' if r.success_rate is None else f'{r.success_rate * 100:.2f}%'}")
        w(f"    days long/short/flat   {r.n_long_days}/{r.n_short_days}/{r.n_flat_days}")
        w(f"    total cost drag        {r.total_cost_drag * 100:.4f}% of notional-days")
        w(
            f"    BREAK-EVEN one-way     "
            f"{'n/a' if r.breakeven_one_way_bps is None else f'{r.breakeven_one_way_bps:+.4f} bp'}"
        )
        w(f"    DSR by N               {json.dumps({str(k): v for k, v in r.dsr_by_n.items()})}")
        w(
            f"    preservation_score     {r.preservation['preservation_score']:.6f}"
            f"   (no_stab {r.preservation['preservation_score_no_stab']:.6f})"
        )
    w("")
    w("-" * 78)
    w("5. DSR LADDER, BOTH BARS -- best NON-CONTROL spec on the verdict arm")
    w("-" * 78)
    w(f"best non-control spec: {best.spec_id}   net Sharpe {best.sharpe_annualized:+.4f}")
    w(f"n_local = {summary.n_local}   ladder = {summary.denominators}")
    w(f"realized sigma_SR across the 8 specs = {summary.sigma_sr_annualized:.6f}")
    w("")
    w(f"{'N':>6}{'DSR':>14}{'>=0.95?':>10}{'>=0.50?':>10}")
    for n in summary.denominators:
        d = best.dsr_by_n.get(n)
        ds = "None" if d is None else f"{d:.6f}"
        p95 = "PASS" if (d is not None and d >= VALIDATED_EDGE_BAR) else "FAIL"
        p50 = "PASS" if (d is not None and d >= SCREENING_FLOOR) else "FAIL"
        w(f"{n:>6}{ds:>14}{p95:>10}{p50:>10}")
    verdict, rationale = summary.verdict(VALIDATED_EDGE_BAR)
    w("")
    w(f"screen verdict @0.95: {verdict}  --  {rationale}")
    w(f"screen verdict @0.50: {summary.verdict(SCREENING_FLOOR)[0]}")
    w("")
    w("-" * 78)
    w("6. PLACEBO (pre-registered control: r2, the 10:00-10:30 return)")
    w("-" * 78)
    w(f"best placebo spec:     {placebo.spec_id}   net Sharpe {placebo.sharpe_annualized:+.4f}")
    w(f"best candidate spec:   {best.spec_id}   net Sharpe {best.sharpe_annualized:+.4f}")
    w(f"placebo DSR by N:      {json.dumps({str(k): v for k, v in placebo.dsr_by_n.items()})}")
    w(
        f"PLACEBO OVERRIDE (PREREGISTRATION 6.4) TRIGGERED: "
        f"{summary.placebo_override_triggered()}"
    )
    w("  Rule: if the placebo's net Sharpe >= the best candidate's, the family is a")
    w("  negative on ATTRIBUTION grounds regardless of DSR.")
    w("")
    w("-" * 78)
    w("7. POWER (dsr_power, realized sigma_SR, claimed Sharpe = the paper's own 1.08)")
    w("-" * 78)
    w("Claimed effect = 1.08, the draft's Table 5 Panel A SRatio for eta(r1) -- the")
    w("EXACT rule spec r1__sign implements. GROSS of costs, 1993-2013, and the best of")
    w("the three signals the paper reports: an upper bound on all three counts.")
    w("")
    for bar, report in power_by_bar.items():
        w(f"  at the {bar:.2f} bar: {report.summary()}")
    w("")
    w("  SECONDARY SCENARIO (not the power input for this grid): the scoping memo's")
    w("  derived 2.088 is the maximal Sharpe of an OPTIMALLY-SCALED linear-forecast bet,")
    w("  a richer strategy this +/-1 sign grid does not contain.")
    w(f"  at the 0.95 bar, claimed 2.088: {power_memo.summary()}")
    w("")
    w(f"  POWER_FLOOR = {POWER_FLOOR}. A failing DSR at n_local with power below it is")
    w("  reported as UNDERPOWERED, not DEFINITE_NEGATIVE (registration_scorecard")
    w("  .policy_d_verdict enforces this from the scorecard's power block).")
    w("")
    w("-" * 78)
    w("8. THE PAPER'S OWN TEST, RE-RUN OUT OF SAMPLE (diagnostic -- NOT a spec,")
    w("   not in N_local, never enters the DSR or the verdict)")
    w("-" * 78)
    w("Eq. (2): r13_t = alpha + beta*x_t + eps_t, Newey-West (1987) HAC t-statistics,")
    w(f"lag truncation {NEWEY_WEST_RULE} (the draft cites NW but states no lag choice,")
    w("so the rule is disclosed as this project's own). Compared against the draft's")
    w("Table 1 Panel A, whole sample 1993-2013.")
    w("")
    w(
        f"{'predictor':<12}{'beta (OOS)':>14}{'NW t':>10}{'R2 %':>9}"
        f"{'| paper beta':>14}{'paper t':>10}{'paper R2 %':>12}"
    )
    for predictor in ("r1", "r12", "r2"):
        reg = predictive_regression(summary.panel, predictor)
        pb = "-" if reg.paper_beta is None else f"{reg.paper_beta:+.3f}"
        pt = "-" if reg.paper_t is None else f"{reg.paper_t:.2f}"
        pr = "-" if reg.paper_r_squared_pct is None else f"{reg.paper_r_squared_pct:.1f}"
        tag = "  [placebo]" if predictor == "r2" else ""
        w(
            f"{predictor:<12}{reg.beta:>+14.6f}{reg.newey_west_t:>10.2f}"
            f"{reg.r_squared_pct:>9.3f}{pb:>14}{pt:>10}{pr:>12}{tag}"
        )
        regressions[predictor] = reg
    w("")
    w(f"{'predictor':<12}{'directional hit rate (gross)':>32}{'n days':>10}")
    for predictor in ("r1", "r12", "r2"):
        rate, n = directional_hit_rate(summary.panel, predictor)
        hit_rates[predictor] = {"hit_rate": rate, "n_days": n}
        # Binomial standard error of a hit rate under the 50/50 null.
        se = float(np.sqrt(0.25 / n))
        z = (rate - 0.5) / se
        w(f"{predictor:<12}{rate * 100:>30.2f}%{n:>10}   ({z:+.2f} SD vs 50%)")
    w("")
    w("The draft's Table 5 Panel A reports a 54.37% success rate for eta(r1) against a")
    w("50.42% Always-Long benchmark, and Table 1 Panel A a slope of +0.069 (t=4.08).")
    w("This section says whether that relationship is present at all in 2016-2026,")
    w("SEPARATELY from whether a strategy built on it clears a multiple-testing gate.")
    w("Those are different questions and only this one is answered by the paper's own")
    w("test. It is reported as a diagnostic precisely so it cannot be mistaken for an")
    w("extra spec: it adds nothing to N_local and changes no verdict.")
    w("")
    w("TWO THINGS THIS SECTION SHOWS THAT THE DSR LADDER ALONE DOES NOT:")
    w("  (a) The paper's HEADLINE relationship is not merely undetected out of sample,")
    w("      its point estimate has the WRONG SIGN. beta_r1 = -0.0511 against the")
    w("      paper's +0.069, and the gross directional hit rate is 48.68%, BELOW the")
    w("      50% coin flip, against the paper's 54.37%. A test can fail to detect a")
    w("      real effect; it does not usually estimate it backwards.")
    w("      (Note R2 is sign-blind, so r1's 1.711% R2 -- close to the paper's 1.6% --")
    w("      is NOT corroboration: it is the fit of a line sloping the other way.)")
    w("  (b) The only predictor with a same-sign, marginally-significant slope is r12")
    w("      (+0.0956, t=1.79), and the PLACEBO r2 sits right next to it (+0.0703,")
    w("      t=1.46). The two are not distinguishable, which is an attribution problem")
    w("      for r12 even though the pre-registered placebo override -- which compares")
    w("      STRATEGY Sharpes, not regression slopes -- did not fire.")
    w("")
    w("-" * 78)
    w("9. COST ATTRIBUTION -- how much the costs ate")
    w("-" * 78)
    w(f"{'spec_id':<30}{'gross SR':>12}{'net SR':>12}{'break-even bp':>16}")
    for r in summary.baseline_results():
        be = "n/a" if r.breakeven_one_way_bps is None else f"{r.breakeven_one_way_bps:+.4f}"
        w(f"{r.spec_id:<30}{r.gross_sharpe_annualized:>12.4f}{r.sharpe_annualized:>12.4f}{be:>16}")
    w("")
    w("Pre-result arithmetic on the paper's OWN Table 5 (ADDENDUM_01 section 4d): this")
    w("strategy pays 504 crossings a year for a 30-minute hold, so at the verdict arm's")
    w("1.0bp/side even a perfect 1993-2013-strength replication (gross 6.67%/yr, sigma")
    w("6.19%/yr) would net Sharpe ~0.26. The whole claim lives inside the first 1.3bp")
    w("per side. That was written down before these numbers existed.")
    w("")
    w("-" * 78)
    w("10. PERSISTENCE")
    w("-" * 78)
    w(f"database:  {describe_configured_database()}")
    w(f"family_key {FAMILY_KEY}   run_tag {RUN_TAG}")
    w(f"rows written {written}, read back {read_back} (verify_persisted_trial_results)")
    w("Rows are the VERDICT arm (baseline). The other arms are reported here and in the")
    w("scorecard; only one arm is persisted so the multiple-testing pool counts this")
    w("family once per spec, not four times.")
    w("")
    w("-" * 78)
    w("11. WHAT IS AND IS NOT CLAIMED")
    w("-" * 78)
    w("NOTHING IS REGISTERED FOR FORWARD VALIDATION and NO LIVE REGISTRATION IS")
    w("TOUCHED (CLAUDE.md rule 6). This run recommends only.")
    w("")
    w("UNVERIFIED, listed together:")
    w("  1. The PUBLISHED JFE 2018 article's figures. Only the October 2014 draft was")
    w("     obtained; ScienceDirect is paywalled and SSRN 403s. Every paper number in")
    w("     this run is from the draft.")
    w("  2. Whether the draft's Table 5/Table 3 figures survived peer review unchanged.")
    w("  3. Alpaca's delisted-symbol coverage (irrelevant here -- one continuously")
    w("     listed instrument -- but the scoping memo's item stands for anything else).")
    w("")

    report = "\n".join(lines) + "\n"
    (OUT_DIR / "RUN_REPORT.txt").write_text(report)
    print(report)

    # machine-readable dump alongside the human report
    payload = {
        "run_tag": RUN_TAG,
        "family_key": FAMILY_KEY,
        "sample": {
            "first_bar": str(minute.index[0]),
            "last_bar": str(minute.index[-1]),
            "n_minute_bars": len(minute),
            "n_sessions": audit.n_sessions,
            "n_usable_sessions": audit.n_usable,
            "n_trading_days": audit.n_traded_days,
            "dropped_too_few_bars": audit.dropped_too_few_bars,
            "dropped_late_bar": audit.dropped_late_bar,
            "dropped_incomplete_blocks": audit.dropped_incomplete_blocks,
            "dropped_no_previous": audit.dropped_no_previous,
        },
        "feed_check": feed,
        "n_local": summary.n_local,
        "denominators": summary.denominators,
        "sigma_sr_annualized": summary.sigma_sr_annualized,
        "best_candidate_spec_id": best.spec_id,
        "best_placebo_spec_id": placebo.spec_id,
        "placebo_override_triggered": summary.placebo_override_triggered(),
        "verdict_at_0.95": summary.verdict(VALIDATED_EDGE_BAR),
        "verdict_at_0.50": summary.verdict(SCREENING_FLOOR),
        "power": {
            str(bar): {
                "claimed_sharpe_annualized": r.claimed_sharpe_annualized,
                "required_observed_sharpe": r.required_observed_sharpe,
                "power_at_claimed_sharpe": r.power_at_claimed_sharpe,
                "min_detectable_sharpe": r.min_detectable_sharpe,
                "years_to_detect_claimed": r.years_to_detect_claimed,
                "underpowered": r.underpowered,
            }
            for bar, r in power_by_bar.items()
        },
        "arms": {
            arm.key: {
                "one_way_bps": arm.one_way_bps,
                "specs": {
                    r.spec_id: {
                        "sharpe_annualized": r.sharpe_annualized,
                        "gross_sharpe_annualized": r.gross_sharpe_annualized,
                        "annualized_return": r.annualized_return,
                        "annualized_volatility": r.annualized_volatility,
                        "success_rate": r.success_rate,
                        "n_trading_days": r.n_trading_days,
                        "n_traded_days": r.n_traded_days,
                        "breakeven_one_way_bps": r.breakeven_one_way_bps,
                        "dsr_by_n": {str(k): v for k, v in r.dsr_by_n.items()},
                        "preservation": r.preservation,
                        "is_control": r.is_control,
                    }
                    for r in summary.results_by_arm[arm.key]
                },
            }
            for arm in COST_ARMS
        },
        "predictive_regressions": {
            k: {
                "beta": v.beta,
                "newey_west_t": v.newey_west_t,
                "r_squared_pct": v.r_squared_pct,
                "newey_west_lags": v.newey_west_lags,
                "n_observations": v.n_observations,
                "paper_beta": v.paper_beta,
                "paper_t": v.paper_t,
                "paper_r_squared_pct": v.paper_r_squared_pct,
            }
            for k, v in regressions.items()
        },
        "directional_hit_rates": hit_rates,
        "persistence": {"rows_written": written, "rows_read_back": read_back},
    }
    (OUT_DIR / "run_output.json").write_text(json.dumps(payload, indent=2, default=str))
    print(f"wrote {OUT_DIR / 'RUN_REPORT.txt'} and {OUT_DIR / 'run_output.json'}")


if __name__ == "__main__":
    main()
