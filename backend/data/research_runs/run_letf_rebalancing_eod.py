"""Production run for the letf_rebalancing_eod family.

Reads the cached SPY/QQQ/IWM 1-minute bars and the pinned ProShares AUM
snapshot, screens all 20 pre-registered specs at all three cost arms, runs the
section 4.1 mechanism gate and the reversal regression, persists one trial row
per spec on the VERDICT arm to cross_sectional_trial_results, verifies the write
by reading it back, and writes the run report.

Persistence is the separate second call cross_sectional_persistence.py's
docstring prescribes -- run the screen, then persist -- never a hidden side
effect of the screen.

The power block (data/research_runs/letf_power_block.py, POWER_BLOCK.md,
power_block.json) was computed and COMMITTED BEFORE this file was written, per
PREREGISTRATION section 4.3. It is read here, never recomputed.
"""

from __future__ import annotations

import json
import pickle
import sys
from datetime import UTC, datetime
from pathlib import Path

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
from app.services.research_lab.dsr_power import POWER_FLOOR
from app.services.research_lab.letf_rebalancing_eod import (
    ABS_RETURN_CUT,
    COST_ARMS,
    DEVIATIONS_FROM_SOURCE,
    FAMILY_KEY,
    MECHANICAL_FORMULA_CITATION,
    MECHANISM_GATE_MIN_T,
    PRE_REGISTERED_N_LOCAL,
    SCREENING_FLOOR,
    SHUFFLE_SEED,
    TUZUN_SAMPLE,
    TUZUN_TABLE_IV_PANEL_A,
    TUZUN_TABLE_VI_PANEL_A,
    UNDERLYING_TO_TUZUN_CATEGORY,
    UNDERLYINGS,
    VALIDATED_EDGE_BAR,
    run_letf_screening,
)
from data.research_runs.fetch_letf_aum import (
    AUM_COL,
    DATE_COL,
    TARGET_TICKERS,
    TICKER_COL,
    load_target_frame,
)
from data.research_runs.letf_power_block import AUM_SNAPSHOT, BARS_DIR, OUT_DIR

RUN_TAG = "letf_rebalancing_eod_2026-09-11"
MAIN_BACKEND = _main_checkout_backend_dir(BACKEND)

# The three -1x ProShares funds the pre-registration's twelve-fund list excludes.
# They ARE in the pinned snapshot, so their omission is exactly measurable.
EXCLUDED_PROSHARES_1X = {"SH": ("SPY", -1.0), "PSQ": ("QQQ", -1.0), "RWM": ("IWM", -1.0)}


def load_bars() -> dict[str, pd.DataFrame]:
    out = {}
    for ticker in UNDERLYINGS:
        with (BARS_DIR / f"{ticker}_1Min.pkl").open("rb") as fh:
            out[ticker] = pickle.load(fh)
    return out


def load_daily() -> dict[str, pd.DataFrame]:
    out = {}
    for ticker in UNDERLYINGS:
        with (BARS_DIR / f"{ticker}_1Day.pkl").open("rb") as fh:
            out[ticker] = pickle.load(fh)
    return out


def feed_check(minute: dict[str, pd.DataFrame], daily: dict[str, pd.DataFrame]) -> dict:
    """Sum the 1-minute volume per session and compare against the 1Day bar's
    volume for the same session -- intraday_momentum_spy PREREGISTRATION 2c,
    which this family's section 2 inherits. The decisive evidence is the
    ABSOLUTE LEVEL: IEX is ~2-3% of consolidated US equity volume, so an
    IEX-only minute sum would come back one to two orders of magnitude low."""
    out = {}
    for ticker in UNDERLYINGS:
        index = pd.DatetimeIndex(minute[ticker].index)
        mv = minute[ticker]["volume"].groupby(index.tz_localize(None).normalize()).sum()
        dv = daily[ticker]["volume"].copy()
        dv.index = pd.DatetimeIndex(dv.index).tz_localize(None).normalize()
        common = mv.index.intersection(dv.index)
        ratio = mv[common] / dv[common]
        median = float(mv[common].median())
        out[ticker] = {
            "n_sessions_compared": len(common),
            "minute_sum_median_shares": median,
            "daily_bar_median_shares": float(dv[common].median()),
            "ratio_median": float(ratio.median()),
            "ratio_min": float(ratio.min()),
            "ratio_max": float(ratio.max()),
            "verdict": (
                "CONSOLIDATED (SIP)"
                if median > 2e6
                else "SUSPECT -- volume far below consolidated levels"
            ),
        }
    return out


def scaling_omission(aum: pd.DataFrame, panel: pd.DataFrame) -> dict:
    """How much of each underlying's true coefficient the pre-registered
    twelve-fund K leaves out, measured where it CAN be measured (the three -1x
    ProShares funds, from the pinned snapshot) and quoted from
    SCALING_OMISSION_EVIDENCE.json where it cannot (Direxion, current day only,
    no history exists)."""
    last_date = aum[DATE_COL].max()
    last = aum[aum[DATE_COL] == last_date].set_index(TICKER_COL)["aum"]
    evidence = json.loads((OUT_DIR / "SCALING_OMISSION_EVIDENCE.json").read_text())
    out: dict = {"as_of": str(last_date.date()), "per_underlying": {}}
    direxion_by_underlying: dict[str, float] = {}
    for key, rows in evidence["verified_present"].items():
        if key == "note":
            continue
        for row in rows:
            if row["issuer"] == "Direxion":
                underlying = {"SPY_underlying_sp500": "SPY", "QQQ_underlying_nasdaq100": "QQQ",
                              "IWM_underlying_russell2000": "IWM"}[key]
                direxion_by_underlying[underlying] = direxion_by_underlying.get(underlying, 0.0) + (
                    row["assets_usd"] * row["leverage_sq_minus_l"]
                )
    for underlying in UNDERLYINGS:
        included = sum(
            float(last.get(t, 0.0)) * (lev**2 - lev)
            for t, (u, lev) in TARGET_TICKERS.items()
            if u == underlying
        )
        omitted_1x = sum(
            float(last.get(t, 0.0)) * (lev**2 - lev)
            for t, (u, lev) in EXCLUDED_PROSHARES_1X.items()
            if u == underlying
        )
        omitted_direxion = direxion_by_underlying.get(underlying, 0.0)
        total = included + omitted_1x + omitted_direxion
        series = panel[panel["underlying"] == underlying].sort_values("date")["K"]
        out["per_underlying"][underlying] = {
            "K_included_usd": included,
            "K_omitted_proshares_1x_usd": omitted_1x,
            "K_omitted_direxion_usd_current_day_only": omitted_direxion,
            "included_share_of_measurable_total": (included / total) if total else None,
            "K_first_session": float(series.iloc[0]),
            "K_last_session": float(series.iloc[-1]),
            "K_growth_multiple_over_sample": (
                float(series.iloc[-1] / series.iloc[0]) if series.iloc[0] else None
            ),
        }
    return out


def _fmt(value: float | None, spec: str = "+.6f") -> str:
    return "n/a" if value is None else format(value, spec)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    minute, daily = load_bars(), load_daily()
    feed = feed_check(minute, daily)
    aum = load_target_frame(AUM_SNAPSHOT).rename(columns={AUM_COL: "aum"})[
        [DATE_COL, TICKER_COL, "aum"]
    ]
    manifest = json.loads((OUT_DIR / "aum_snapshot_manifest.json").read_text())
    power = json.loads((OUT_DIR / "power_block.json").read_text())

    summary = run_letf_screening(minute, aum, TARGET_TICKERS)
    audit = summary.audit
    best = summary.best_candidate()
    control = summary.best_control()
    assert best is not None and control is not None

    # The scaling-omission disclosure needs the -1x funds too, so the snapshot is
    # re-read for them rather than widening the family's own fund map -- K itself
    # must stay exactly the twelve funds the pre-registration names.
    wide_aum = pd.read_csv(AUM_SNAPSHOT, low_memory=False)
    wide_aum[DATE_COL] = pd.to_datetime(wide_aum[DATE_COL], format="%m/%d/%Y")
    wide_aum = wide_aum[wide_aum[TICKER_COL].isin(set(TARGET_TICKERS) | set(EXCLUDED_PROSHARES_1X))]
    wide_aum = wide_aum.rename(columns={AUM_COL: "aum"})[[DATE_COL, TICKER_COL, "aum"]]
    omission = scaling_omission(wide_aum, summary.panel)

    # ---- persist the VERDICT arm's trials -------------------------------
    with SessionLocal() as db:
        written = persist_cross_sectional_trial_results(
            db, FAMILY_KEY, summary.baseline_results(), run_tag=RUN_TAG
        )
        read_back = verify_persisted_trial_results(db, RUN_TAG, written, family_key=FAMILY_KEY)

    lines: list[str] = []
    w = lines.append
    w("=" * 78)
    w("LETF END-OF-DAY REBALANCING PRESSURE (letf_rebalancing_eod) -- run report")
    w(f"run_tag {RUN_TAG}   written {datetime.now(UTC).isoformat()}")
    w("=" * 78)
    w("")
    w("Tuzun, 'Are Leveraged and Inverse ETFs the New Portfolio Insurers?', Federal")
    w(f"Reserve Board FEDS 2013-48, Eq. (2)/(3) and Tables IV and VI. Sample {TUZUN_SAMPLE}.")
    w(f"Mechanical formula: {MECHANICAL_FORMULA_CITATION}.")
    w("")
    w("*** THE ENTIRE SAMPLE HERE IS OUT OF SAMPLE RELATIVE TO THE PAPER. ***")
    w("Tuzun's sample ends 2011-12-31; the earliest bar here is 2016-01-04. ZERO")
    w("OVERLAP. This is not a replication and cannot be one.")
    w("")
    w("Pre-registration: PREREGISTRATION.md (merged to main as 6217c57, before any")
    w("panel for this family was assembled) and ADDENDUM_01_CONTROL_DEGENERACY_AND_")
    w("GRID_COUNT.md (committed before any strategy return existed). POWER_BLOCK.md")
    w("and power_block.json were computed and committed BEFORE this run.")
    w("")
    w("-" * 78)
    w("0. THE HEADLINE, STATED FIRST")
    w("-" * 78)
    verdict, rationale = summary.verdict(VALIDATED_EDGE_BAR)
    w(f"SECTION 4.1 MECHANISM GATE: {'PASS' if summary.mechanism_gate_passes() else 'FAIL'}")
    w(f"  b = {summary.mechanism.b:+.6f}   clustered t = {summary.mechanism.b_t:+.4f}   "
      f"(needs b > 0 and t >= {MECHANISM_GATE_MIN_T})")
    w(f"POWER TIER (declared in advance, section 4.3): "
      f"{'UNDERPOWERED' if power['PRE_REGISTERED_DECISION']['declared_underpowered_in_advance'] else 'POWERED'}"
      f"   (50%-Tuzun power at the 0.95 bar = "
      f"{power['PRE_REGISTERED_DECISION']['half_tuzun_power_at_0.95_n_local']:.4f} "
      f"vs floor {POWER_FLOOR})")
    w(f"ECONOMIC TIER (section 4.2, verdict arm): {verdict}")
    w(f"  {rationale}")
    w("")
    w("-" * 78)
    w("1. DATA")
    w("-" * 78)
    for ticker in UNDERLYINGS:
        bars = minute[ticker]
        w(f"{ticker} 1-minute SIP bars: {len(bars):,}  {bars.index[0]} .. {bars.index[-1]}")
    w("")
    w(f"{'ticker':<8}{'calendar':>10}{'usable':>10}{'U3 drop':>10}{'U2 drop':>10}"
      f"{'U1 drop':>10}{'no w bar':>10}")
    for ticker in UNDERLYINGS:
        w(
            f"{ticker:<8}{audit.per_ticker_sessions[ticker]:>10}"
            f"{audit.per_ticker_usable[ticker]:>10}"
            f"{len(audit.dropped_too_few_bars[ticker]):>10}"
            f"{len(audit.dropped_late_bar[ticker]):>10}"
            f"{len(audit.dropped_incomplete_blocks[ticker]):>10}"
            f"{len(audit.dropped_missing_window_bar[ticker]):>10}"
        )
    w("")
    w(f"dropped, not usable for ALL THREE (balanced-panel rule): "
      f"{len(audit.dropped_not_common_to_all)}")
    w("  " + (", ".join(audit.dropped_not_common_to_all) or "(none)"))
    w(f"dropped, no usable predecessor:      {len(audit.dropped_no_previous)}")
    w(f"dropped, trailing window incomplete: {len(audit.dropped_short_trailing)}")
    w(f"PANEL SESSIONS: {audit.n_panel_sessions}   rows: {len(summary.panel)}")
    w(f"measured sessions per year: {summary.periods_per_year:.4f}")
    w("")
    w("The 'no w bar' column is an implementation necessity, not a discretionary")
    w("filter: r_open->w is defined as a return TO THE OPEN OF THE BAR STARTING AT w,")
    w("which is undefined when no bar starts at w. It is counted separately from")
    w("U1-U3 so it can be seen to be near zero.")
    w("")
    w("-" * 78)
    w("2. AUM SNAPSHOT (the A_{i,t-1} input)")
    w("-" * 78)
    w(f"file      {manifest['snapshot_filename']}")
    w(f"bytes     {manifest['bytes']:,}")
    w(f"sha256    {manifest['sha256']}")
    w(f"rows      {manifest['n_rows_target_tickers']:,} across the 12 pre-registered funds")
    w("")
    w(f"{'fund':<8}{'under':>8}{'L':>6}{'L^2-L':>8}{'rows':>8}{'first':>13}{'last':>13}")
    for ticker, info in sorted(manifest["per_ticker"].items()):
        w(
            f"{ticker:<8}{info['underlying']:>8}{info['leverage']:>6.0f}"
            f"{info['leverage_sq_minus_l']:>8.0f}{info['n_rows']:>8}"
            f"{info['first_date']:>13}{info['last_date']:>13}"
        )
    w("")
    w("AUM IDENTITY CHECK (PREREGISTRATION section 2): AUM ~= NAV x Shares(000) x 1000")
    for key, label in (
        ("aum_identity_check", "whole file"),
        ("aum_identity_check_sample_range", "2015-12-01 onward (the only rows this run can read)"),
    ):
        check = manifest[key]
        w(f"  {label}:")
        w(f"    {check['n_rows_within_0.1pct']:,} of {check['n_rows_checked']:,} rows within 0.1% "
          f"= {check['fraction_within_0.1pct'] * 100:.2f}%   passes 99% rule: "
          f"{check['passes_99pct_rule']}")
        w(f"    median relative error {check['median_relative_error']:.3e}   "
          f"max {check['max_relative_error']:.6f}")
    w("")
    w("Every in-range discrepancy is SQQQ, and is the NAV and Shares Outstanding")
    w("columns being TRANSPOSED in those rows (NAV 176,200 against 2.32 thousand")
    w("shares on 2015-12-01). The identity is symmetric in the two, so the residual is")
    w("rounding, under 0.35% throughout, and this family reads the AUM column itself")
    w("rather than the product. The pre-registration's rule is report-and-list, not a")
    w("gate. Rows are the issuer's CURRENT historical record: restatements are")
    w("undetectable from one snapshot, which is why the sha256 above is pinned.")
    w("")
    w("-" * 78)
    w("3. FEED CHECK")
    w("-" * 78)
    for ticker, info in feed.items():
        w(f"  {ticker}: {info['verdict']}   minute-sum median {info['minute_sum_median_shares']:,.0f} "
          f"shares vs 1Day bar {info['daily_bar_median_shares']:,.0f}   "
          f"ratio median {info['ratio_median']:.4f} (min {info['ratio_min']:.4f}, "
          f"max {info['ratio_max']:.4f})")
    w("")
    w("The decisive evidence is the ABSOLUTE LEVEL, not the ratio: IEX is ~2-3% of")
    w("consolidated US equity volume, so an IEX-only minute sum would have come back")
    w("one to two orders of magnitude below these. The residual shortfall against the")
    w("1Day bar is excluded pre/post-market volume plus the 16:00 closing-auction")
    w("print, since the minute frame is filtered to bar-starts in [09:30,16:00).")
    w("WHY IT BARELY MATTERS HERE: every price quantity tested is a RATIO OF TWO")
    w("PRINTS and prints sit inside the NBBO. It WOULD matter for ADV20, which is a")
    w("volume construction -- and ADV20 enters x's MAGNITUDE, hence the section 4.1")
    w("regression, though not the sign of any position.")
    w("")
    w("-" * 78)
    w("4. THE SECTION 4.1 MECHANISM GATE -- the only place the mechanism is tested")
    w("-" * 78)
    w("y_{u,t}/sigma20 = a + b*(x_{u,t}*100) + c*(r_open->w/sigma20) + e,")
    w("standard errors CLUSTERED BY SESSION (Tuzun Table IV's own note, 'standard")
    w("errors are clustered daily'). PASS iff b > 0 with t >= 2.0 at w = 15:30.")
    w("")
    w(f"{'estimate':<52}{'b':>12}{'t(b)':>9}{'se':>11}{'c':>10}{'t(c)':>8}{'R2 %':>8}{'n':>8}")
    for regression in (
        summary.mechanism,
        summary.mechanism_secondary,
        summary.reversal,
        summary.mechanism_placebo,
    ):
        w(
            f"{regression.label[:52]:<52}{regression.b:>+12.5f}{regression.b_t:>+9.2f}"
            f"{regression.b_se:>11.5f}{regression.c:>+10.4f}{regression.c_t:>+8.2f}"
            f"{regression.r_squared_pct:>8.3f}{regression.n_observations:>8}"
        )
    w("")
    w(f"GATE (w=15:30, real K): b = {summary.mechanism.b:+.6f}, t = {summary.mechanism.b_t:+.4f}"
      f"  ->  {'PASS' if summary.mechanism_gate_passes() else 'FAIL'}")
    w("")
    w("Tuzun's own Table IV Panel A, control included, for reference ONLY:")
    for underlying in UNDERLYINGS:
        category = UNDERLYING_TO_TUZUN_CATEGORY[underlying]
        reference = TUZUN_TABLE_IV_PANEL_A[category]
        w(f"  {underlying} ~ {category:<12} b = {reference['beta']:.2f} "
          f"(s.e. {reference['se']:.2f}, N = {reference['n_obs']:,}, "
          f"adj-R2 {reference['adj_r2_pct']:.2f}%)")
    w("")
    w("*** b IS NOT ON TUZUN'S SCALE AND MUST NOT BE COMPARED TO 4.32 AS THOUGH IT")
    w("WERE. *** His ADV is the CONSTITUENT STOCK's 20-day average dollar volume and")
    w("his LETFFlow is that stock's index-weighted share of the total; ours is the")
    w("INDEX ETF's own volume and the whole undivided flow (DEVIATION D1). The SIGN")
    w("and the t-statistic are comparable; the magnitude is not.")
    w("")
    w("REVERSAL (section 4.1's second half, sign reported, NOT gating). Tuzun Eq. (3)")
    w("/ Table VI Panel A lagged-flow coefficients, for reference only:")
    for underlying in UNDERLYINGS:
        category = UNDERLYING_TO_TUZUN_CATEGORY[underlying]
        reference = TUZUN_TABLE_VI_PANEL_A[category]
        w(f"  {underlying} ~ {category:<12} b = {reference['beta']:+.2f} "
          f"(s.e. {reference['se']:.2f})")
    w(f"  measured here: b = {summary.reversal.b:+.6f}, t = {summary.reversal.b_t:+.4f}  "
      f"-> sign {'NEGATIVE (as the paper)' if summary.reversal.b < 0 else 'POSITIVE (opposite the paper)'}")
    w("")
    w("DIAGNOSTIC, not a spec, not in n_local, persists no row, changes no verdict:")
    w(f"the same regression with K PERMUTED across sessions (seed {SHUFFLE_SEED}) gives")
    w(f"b = {summary.mechanism_placebo.b:+.6f}, t = {summary.mechanism_placebo.b_t:+.4f}. "
      "ADDENDUM_01 added it")
    w("because the pre-registered C2 placebo is degenerate on the trading grid and a")
    w("mechanism gate whose only placebo is degenerate has no false-positive check.")
    w("")
    w("-" * 78)
    w("5. THE ALGEBRAIC DEGENERACY OF C1 AND C2, MEASURED")
    w("-" * 78)
    w("ADDENDUM_01 section 1, written before any return existed: K > 0 and ADV20 > 0,")
    w("so sign(x) == sign(r) identically, so rescaling K (C1) or permuting it (C2)")
    w("cannot change a single position on a sign-rule grid. Checked on this run's own")
    w("series rather than asserted:")
    for spec_id, identical in summary.degenerate_controls().items():
        result = summary.result(spec_id)
        w(f"  {spec_id:<32} net Sharpe {result.sharpe_annualized:+.6f}   "
          f"identical to P_1530: {identical}")
    pooled = summary.result("P_1530")
    w(f"  {'P_1530 (the base spec)':<32} net Sharpe {pooled.sharpe_annualized:+.6f}")
    w("")
    w("CONSEQUENCE, stated plainly: the section 3 trading grid contains NO test of the")
    w("LETF mechanism. Every spec in it is plain intraday momentum on the underlying")
    w("ETF. C3 (wrong window) is the only surviving discriminating control on the")
    w("grid, and section 4.1 is the only place the mechanism itself is examined.")
    w("")
    w("-" * 78)
    w("6. RESULTS -- every spec, every cost arm (annualized Sharpe on NET daily returns)")
    w("-" * 78)
    header = f"{'spec_id':<32}" + "".join(f"{arm.key:>13}" for arm in COST_ARMS)
    w(header)
    w("-" * len(header))
    order = [r.spec_id for r in summary.results_by_arm["cost_free"]]
    for spec_id in order:
        row = f"{spec_id:<32}"
        for arm in COST_ARMS:
            result = next(x for x in summary.results_by_arm[arm.key] if x.spec_id == spec_id)
            row += f"{result.sharpe_annualized:>13.4f}"
        flag = "  [CONTROL]" if spec_id.startswith("C") and "_" in spec_id[:3] else ""
        w(row + flag)
    w("")
    w("one-way bps per arm: " + ", ".join(f"{a.key}={a.one_way_bps}" for a in COST_ARMS))
    w(f"spec B's flat cut: |r_open->w| < {ABS_RETURN_CUT:.4f} (fixed before any data; not moved)")
    w("")
    w("-" * 78)
    w("7. THE VERDICT ARM (1.0 bp one-way = 2 crossings per traded day)")
    w("-" * 78)
    for result in summary.baseline_results():
        w("")
        w(f"  {result.spec_id}{'  [PRE-REGISTERED CONTROL]' if result.is_control else ''}")
        w(f"    net Sharpe (ann.)      {result.sharpe_annualized:+.4f}")
        w(f"    gross Sharpe (ann.)    {result.gross_sharpe_annualized:+.4f}")
        w(f"    net ann. return        {result.annualized_return * 100:+.4f}%")
        w(f"    ann. volatility        {result.annualized_volatility * 100:.4f}%")
        w(f"    hit rate (traded days) "
          f"{'n/a' if result.hit_rate is None else f'{result.hit_rate * 100:.2f}%'}")
        w(f"    days traded / flat     {result.n_traded_days}/{result.n_flat_days}"
          f"   of {result.n_trading_days}")
        w(f"    BREAK-EVEN one-way     {_fmt(result.breakeven_one_way_bps, '+.4f')} bp")
        w(f"    DSR by N               "
          f"{json.dumps({str(k): v for k, v in result.dsr_by_n.items()})}")
        w(f"    preservation_score     {result.preservation['preservation_score']:.6f}"
          f"   (no_stab {result.preservation['preservation_score_no_stab']:.6f})")
    w("")
    w("-" * 78)
    w("8. DSR LADDER -- best NON-CONTROL spec on the verdict arm")
    w("-" * 78)
    w(f"best non-control spec: {best.spec_id}   net Sharpe {best.sharpe_annualized:+.4f}")
    w(f"n_local = {summary.n_local} (pre-registered {PRE_REGISTERED_N_LOCAL})   "
      f"ladder = {summary.denominators}")
    w(f"realized sigma_SR across the {len(summary.baseline_results())} specs = "
      f"{summary.sigma_sr_annualized:.6f}")
    w("")
    w(f"{'N':>6}{'DSR':>14}{'>=0.95?':>10}{'>=0.50?':>10}")
    for n in summary.denominators:
        value = best.dsr_by_n.get(n)
        shown = "None" if value is None else f"{value:.6f}"
        w(f"{n:>6}{shown:>14}"
          f"{('PASS' if value is not None and value >= VALIDATED_EDGE_BAR else 'FAIL'):>10}"
          f"{('PASS' if value is not None and value >= SCREENING_FLOOR else 'FAIL'):>10}")
    w("")
    w(f"screen verdict @0.95: {verdict}  --  {rationale}")
    w(f"screen verdict @0.50: {summary.verdict(SCREENING_FLOOR)[0]}")
    w("")
    w("-" * 78)
    w("9. POWER (read from POWER_BLOCK.md / power_block.json, computed and committed")
    w("   BEFORE this run -- NOT recomputed here)")
    w("-" * 78)
    w(f"sigma(y) = {power['inputs']['sigma_y_daily']:.8f}   "
      f"mean |r_open->15:30| = {power['inputs']['mean_abs_r']:.8f}")
    w(f"Tuzun's claim, applied linearly: {power['inputs']['expected_gross_daily_return_full'] * 1e4:.4f} bp/day gross "
      f"(full), {power['inputs']['expected_gross_daily_return_half'] * 1e4:.4f} bp (50%),")
    w(f"against a {power['inputs']['round_trip_cost'] * 1e4:.1f} bp round trip charged inside the series.")
    for name in ("full_tuzun", "half_tuzun"):
        arm = power["arms"][name]
        cell = arm["sigma_sr_declared__bar_0.95"]
        w(f"  {name:<12} claimed net Sharpe {arm['claimed_net_sharpe_annualized']:+.4f}   "
          f"power@0.95 = {cell['power_at_claimed_sharpe']:.4f}   "
          f"required observed SR {cell['required_observed_sharpe']:.4f}")
    w("")
    w(f"PRE-REGISTERED DECLARATION (section 4.3, made in advance): UNDERPOWERED = "
      f"{power['PRE_REGISTERED_DECISION']['declared_underpowered_in_advance']}")
    w("At half strength -- the strength Ivanov & Lenkey's Table III actually measures")
    w("once investor flows are counted -- the pre-registered cost arm consumes 72% of")
    w("the entire claimed effect before detection is even in question.")
    w("")
    w("-" * 78)
    w("10. SCALING OMISSION (PREREGISTRATION section 2; evidence in")
    w("    SCALING_OMISSION_EVIDENCE.json)")
    w("-" * 78)
    w(f"as of {omission['as_of']}, in units of AUM x (L^2-L):")
    w("")
    w(f"{'under':<8}{'K included':>18}{'omitted 1x':>16}{'omitted Direxion':>20}{'included %':>13}")
    for underlying, info in omission["per_underlying"].items():
        w(
            f"{underlying:<8}{info['K_included_usd']:>18,.0f}"
            f"{info['K_omitted_proshares_1x_usd']:>16,.0f}"
            f"{info['K_omitted_direxion_usd_current_day_only']:>20,.0f}"
            f"{info['included_share_of_measurable_total'] * 100:>12.1f}%"
        )
    w("")
    w("K's own time variation over the sample (this is what C1 was meant to isolate):")
    for underlying, info in omission["per_underlying"].items():
        w(f"  {underlying}: {info['K_first_session']:,.0f} -> {info['K_last_session']:,.0f}   "
          f"x{info['K_growth_multiple_over_sample']:.2f}")
    w("")
    w("The Direxion column is a CURRENT-DAY third-party figure only; no free daily")
    w("Direxion AUM history exists, which is exactly why the pre-registration scopes K")
    w("to ProShares. It does NOT tell us the share in, say, 2018. The -1x column is")
    w("exact, from the pinned snapshot, and is omitted by the pre-registration's")
    w("twelve-fund list rather than by data availability. K as built is a strict LOWER")
    w("BOUND; a strictly positive rescaling changes no position's sign and neither the")
    w("sign nor the t of b.")
    w("")
    w("-" * 78)
    w("11. DEVIATIONS FROM SOURCE")
    w("-" * 78)
    for deviation in DEVIATIONS_FROM_SOURCE:
        w("")
        for chunk in [deviation[i : i + 76] for i in range(0, len(deviation), 76)]:
            w("  " + chunk)
    w("")
    w("-" * 78)
    w("12. PERSISTENCE")
    w("-" * 78)
    w(f"database:  {describe_configured_database()}")
    w(f"family_key {FAMILY_KEY}   run_tag {RUN_TAG}")
    w(f"rows written {written}, read back {read_back} (verify_persisted_trial_results)")
    w("Rows are the VERDICT arm only. The other arms are reported here and on the")
    w("scorecard; persisting one arm keeps the multiple-testing pool counting this")
    w("family once per spec rather than three times.")
    w("")
    w("-" * 78)
    w("13. WHAT IS AND IS NOT CLAIMED")
    w("-" * 78)
    w("NOTHING IS REGISTERED FOR FORWARD VALIDATION and NO LIVE REGISTRATION IS")
    w("TOUCHED (CLAUDE.md rule 6). This run recommends only; the owner decides.")
    w("")
    w("UNVERIFIED, listed together:")
    w("  1. Cheng & Madhavan (2009) itself. SSRN 403s automated retrieval and the one")
    w("     indexed copy found was a corrupt PDF. The formula is taken from Ivanov &")
    w("     Lenkey Eq. (6) and Shum et al. Eq. (1), both read in full, which state it")
    w("     independently.")
    w("  2. Any EXHAUSTIVE sweep of US LETFs on these three indices. stockanalysis'")
    w("     screener needs JavaScript and direxion.com 403s automated fetch, so the")
    w("     scaling-omission list is a set of pages that WERE read, not a swept")
    w("     universe. Leveraged ETNs and recent launches by unchecked issuers are")
    w("     UNKNOWN, not shown absent.")
    w("  3. Any HISTORY of Direxion AUM -- current-day third-party figures only.")
    w("  4. Whether ProShares' and Direxion's S&P 500 funds track an identical index")
    w("     calculation. Both say 'S&P 500'; the prospectuses were not read.")
    w("  5. Restatements in the ProShares history. The file is the issuer's current")
    w("     record; one snapshot cannot detect a revision. The sha256 is pinned so a")
    w("     later fetch that differs is visibly a different file.")
    w("  6. The reversal specs hold OVERNIGHT and the pre-registered cost arms charge")
    w("     no borrow, so those three specs' costs are understated. Disclosed, not")
    w("     corrected -- the arms were fixed before any result existed.")
    w("")

    report = "\n".join(lines) + "\n"
    (OUT_DIR / "RUN_REPORT.txt").write_text(report)
    print(report)

    payload = {
        "run_tag": RUN_TAG,
        "family_key": FAMILY_KEY,
        "sample": {
            "first_session": str(summary.panel["date"].min().date()),
            "last_session": str(summary.panel["date"].max().date()),
            "n_panel_sessions": audit.n_panel_sessions,
            "n_panel_rows": len(summary.panel),
            "periods_per_year": summary.periods_per_year,
            "per_ticker_calendar_sessions": audit.per_ticker_sessions,
            "per_ticker_usable_sessions": audit.per_ticker_usable,
            "dropped_too_few_bars": {t: len(v) for t, v in audit.dropped_too_few_bars.items()},
            "dropped_late_bar": {t: len(v) for t, v in audit.dropped_late_bar.items()},
            "dropped_incomplete_blocks": {
                t: len(v) for t, v in audit.dropped_incomplete_blocks.items()
            },
            "dropped_missing_window_bar": {
                t: v for t, v in audit.dropped_missing_window_bar.items()
            },
            "dropped_not_common_to_all": audit.dropped_not_common_to_all,
            "dropped_no_previous": audit.dropped_no_previous,
            "n_dropped_short_trailing": len(audit.dropped_short_trailing),
        },
        "aum_snapshot": {
            "filename": manifest["snapshot_filename"],
            "sha256": manifest["sha256"],
            "bytes": manifest["bytes"],
            "identity_check_whole_file": {
                k: v for k, v in manifest["aum_identity_check"].items() if k != "worst_rows"
            },
            "identity_check_sample_range": {
                k: v
                for k, v in manifest["aum_identity_check_sample_range"].items()
                if k != "worst_rows"
            },
        },
        "feed_check": feed,
        "scaling_omission": omission,
        "n_local": summary.n_local,
        "pre_registered_n_local": PRE_REGISTERED_N_LOCAL,
        "denominators": summary.denominators,
        "sigma_sr_annualized": summary.sigma_sr_annualized,
        "mechanism_gate": {
            "passes": summary.mechanism_gate_passes(),
            "min_t": MECHANISM_GATE_MIN_T,
            "estimates": {
                r.label: {
                    "window": r.window,
                    "b": r.b,
                    "b_t": r.b_t,
                    "b_se": r.b_se,
                    "c": r.c,
                    "c_t": r.c_t,
                    "a": r.a,
                    "r_squared_pct": r.r_squared_pct,
                    "n_observations": r.n_observations,
                    "n_clusters": r.n_clusters,
                    "is_placebo": r.is_placebo,
                }
                for r in (
                    summary.mechanism,
                    summary.mechanism_secondary,
                    summary.reversal,
                    summary.mechanism_placebo,
                )
            },
            "tuzun_table_iv_panel_a": TUZUN_TABLE_IV_PANEL_A,
            "tuzun_table_vi_panel_a": TUZUN_TABLE_VI_PANEL_A,
        },
        "degenerate_controls": summary.degenerate_controls(),
        "best_candidate_spec_id": best.spec_id,
        "best_control_spec_id": control.spec_id,
        "verdict_at_0.95": summary.verdict(VALIDATED_EDGE_BAR),
        "verdict_at_0.50": summary.verdict(SCREENING_FLOOR),
        "power_block": power["PRE_REGISTERED_DECISION"],
        "arms": {
            arm.key: {
                "one_way_bps": arm.one_way_bps,
                "specs": {
                    r.spec_id: {
                        "kind": r.kind,
                        "window": r.window,
                        "is_control": r.is_control,
                        "sharpe_annualized": r.sharpe_annualized,
                        "gross_sharpe_annualized": r.gross_sharpe_annualized,
                        "annualized_return": r.annualized_return,
                        "annualized_volatility": r.annualized_volatility,
                        "hit_rate": r.hit_rate,
                        "n_trading_days": r.n_trading_days,
                        "n_traded_days": r.n_traded_days,
                        "n_flat_days": r.n_flat_days,
                        "breakeven_one_way_bps": r.breakeven_one_way_bps,
                        "dsr_by_n": {str(k): v for k, v in r.dsr_by_n.items()},
                        "preservation": r.preservation,
                    }
                    for r in summary.results_by_arm[arm.key]
                },
            }
            for arm in COST_ARMS
        },
        "deviations_from_source": list(DEVIATIONS_FROM_SOURCE),
        "persistence": {"rows_written": written, "rows_read_back": read_back},
    }
    (OUT_DIR / "run_output.json").write_text(json.dumps(payload, indent=2, default=str))
    print(f"wrote {OUT_DIR / 'RUN_REPORT.txt'} and {OUT_DIR / 'run_output.json'}")


if __name__ == "__main__":
    main()
