"""INDEPENDENT verification of short_interest_borrow_composition_2026-09-05.

Nothing here calls the runner. Every rule it checks is retyped from the SOURCE
it comes from, and compared against the persisted artifact:

  * the leg cutoff        -> cross_sectional.select_leg_tickers' documented rule
                             (max(1, floor(n * rank_fraction)), descending sort,
                             ties broken alphabetically), retyped
  * the tail rule         -> borrow_cost.BorrowSchedule.rate_for_percentiles'
                             documented rule (pct <= 0.10 or >= 0.90 -> 430,
                             else 34, NaN -> 34), retyped
  * the hedged net weights-> _target_weights' documented arithmetic, retyped:
                             long weights minus 1/N on every eligible name
  * the DSR              -> Bailey/Lopez de Prado's two formulas, retyped from
                             deflated_sharpe.py's own source (scipy.stats.norm
                             only; deflated_sharpe is NOT imported)

Run from backend/ with the venv python.
"""

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

import app

if Path(app.__file__).resolve().parent.parent != BACKEND:
    raise SystemExit(
        f"REFUSING TO RUN: `app` resolved to {app.__file__}, outside this worktree ({BACKEND}). "
        "The verification would have checked another checkout's code."
    )

from app.services.market_data.edgar_xbrl_provider import EdgarXbrlProvider
from app.services.market_data.finra_short_interest_provider import (
    FinraShortInterestProvider,
)
from app.services.market_data.sec_shares_outstanding_provider import (
    SecSharesOutstandingProvider,
)
from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.cross_sectional_short_interest import (
    SHARES_MAX_STALENESS_DAYS,
    SHORT_INTEREST_CYCLE_FETCH_START,
    build_point_in_time_share_count_frame,
    build_short_interest_panels,
)
from app.services.research_lab.sp500_membership_history import (
    get_universe_over,
    was_member,
)

ART = BACKEND / "data/research_runs/short_interest_borrow_composition_2026-09-05.json"
art = json.loads(ART.read_text())

START, END = date(2018, 1, 12), date(2026, 9, 1)
PADDED = START - timedelta(days=30)
GC, HTB, TAIL = 34.0, 430.0, 0.10
RANK_FRACTION = 0.05

universe = sorted(get_universe_over(START, END))
frames, _missing = YFinanceProvider().get_daily_ohlcv(universe, PADDED, END)
close = frames["close"]
priced = list(close.columns)

si_obs, _d = FinraShortInterestProvider().fetch_observations_for_tickers(
    priced, SHORT_INTEREST_CYCLE_FETCH_START, END
)
cik_map = EdgarXbrlProvider().get_ticker_cik_map()
resolvable = {t: cik_map[t] for t in priced if t in cik_map}
share_obs, _sd = SecSharesOutstandingProvider().fetch_share_counts(
    resolvable, PADDED, END, missing_from_map=[t for t in priced if t not in cik_map]
)
share_frame, _ns = build_point_in_time_share_count_frame(
    close, share_obs, max_staleness_days=SHARES_MAX_STALENESS_DAYS
)
ratio_frame, _dtc, _pd_ = build_short_interest_panels(close, si_obs, share_frame)


def hand_rate(pct):
    """borrow_cost's documented rule, retyped. NaN -> GC (its S&P 500 default)."""
    if pct is None or (isinstance(pct, float) and np.isnan(pct)):
        return GC
    return HTB if (pct <= TAIL or pct >= 1.0 - TAIL) else GC


def hand_leg(signal: pd.Series, fraction: float):
    """select_leg_tickers' rule, retyped: drop NaN/non-finite, leg size
    max(1, floor(n*fraction)), sort by ticker then by value descending with a
    stable sort, take the head and the tail."""
    clean = signal.dropna()
    clean = clean[np.isfinite(clean)]
    n = len(clean)
    if n == 0:
        return [], []
    n_leg = max(1, int(n * fraction))
    ordered = clean.sort_index().sort_values(ascending=False, kind="mergesort")
    return list(ordered.index[:n_leg]), list(ordered.index[-n_leg:])


# ---------------------------------------------------------------------------
# 1. THE HEDGED (REGISTERED) BOOK, formation by formation
# ---------------------------------------------------------------------------
#
# For a hedged formation whose every long name is genuinely net long, the
# borrow charge is completely independent of the long-leg WEIGHTING:
#   net weight of a non-long eligible name is exactly -1/N
#   gross = 2 * (1 - n_long/N)  and  short notional = (1 - n_long/N)
#   => implied financing = mean(rate over the non-long eligible names) / 2
# This is derived here from _target_weights' arithmetic, not taken from the
# runner, and it needs none of _leg_weights/_apply_weight_cap.

per_formation = {r["date"]: r for r in art["composition"]["si_ratio_hedged_h21"]["per_formation"]}
index = close.index
lookback = None
# formation positions: the runner walks range(first_formation, n-1, holding).
# Re-derived here from the artifact's own formation DATES instead, so this
# check does not depend on reproducing the cadence rule.
checked, worst = 0, 0.0
worst_row = None
for iso, row in per_formation.items():
    if not row.get("sir_covered"):
        continue
    ts = pd.Timestamp(iso)
    i = index.get_loc(ts)
    day = ts.date()
    prices = close.iloc[i]
    eligible = [t for t in close.columns if was_member(t, day) and np.isfinite(prices[t])]
    assert len(eligible) == row["n_eligible"], (iso, len(eligible), row["n_eligible"])

    # the family's signal: -SIR, NaN where unobservable
    sir = ratio_frame.iloc[i].reindex(eligible).astype(float)
    signal = (-sir).where(np.isfinite(-sir))
    long_leg, _bottom = hand_leg(signal, RANK_FRACTION)
    assert len(long_leg) == row["n_long"], (iso, len(long_leg), row["n_long"])

    # percentiles WITHIN the eligible names carrying a SIR
    cs = sir.dropna()
    pct = cs.rank(method="average", pct=True)
    non_long = [t for t in eligible if t not in set(long_leg)]
    rates = [hand_rate(pct.get(t, float("nan"))) for t in non_long]
    hand_financing = float(np.mean(rates)) / 2.0

    got = row["implied_financing_bps_per_year"]
    gap = abs(hand_financing - got)
    if gap > worst:
        worst, worst_row = gap, (iso, hand_financing, got)
    checked += 1

print(f"[1] hedged si_ratio_hedged_h21: {checked} formations re-derived from primitives")
print(f"    worst |hand implied financing - artifact| = {worst:.3e}   {worst_row}")

# and the run-level mean the report quotes
hand_mean = float(
    np.mean([r["implied_financing_bps_per_year"] for r in per_formation.values() if r.get("sir_covered")])
)
print(f"    mean over formations: hand {hand_mean:.6f} vs report "
      f"{art['measured_financing_bps_per_year']['registered_hedged_book']}")

# ---------------------------------------------------------------------------
# 2. THE LONG_SHORT (UNREGISTERED) BOOK: is the short leg really 100% tail?
# ---------------------------------------------------------------------------
ls = {r["date"]: r for r in art["composition"]["si_ratio_ls_h21"]["per_formation"]}
n_all_tail, n_checked = 0, 0
for iso, row in ls.items():
    if not row.get("sir_covered"):
        continue
    ts = pd.Timestamp(iso)
    i = index.get_loc(ts)
    day = ts.date()
    prices = close.iloc[i]
    eligible = [t for t in close.columns if was_member(t, day) and np.isfinite(prices[t])]
    sir = ratio_frame.iloc[i].reindex(eligible).astype(float)
    signal = (-sir).where(np.isfinite(-sir))
    _top, short_leg = hand_leg(signal, RANK_FRACTION)
    cs = sir.dropna()
    pct = cs.rank(method="average", pct=True)
    rates = [hand_rate(pct.get(t, float("nan"))) for t in short_leg]
    n_checked += 1
    if all(r == HTB for r in rates):
        n_all_tail += 1
print(f"[2] long_short si_ratio_ls_h21: {n_all_tail}/{n_checked} formations have EVERY short-leg "
      f"name at the specials rate (expected: all of them)")

# ---------------------------------------------------------------------------
# 3. DSR, formulas retyped from their sources (deflated_sharpe NOT imported)
# ---------------------------------------------------------------------------
#    SR0  = sigma_sr * [ (1-g) * Phi^-1(1 - 1/N) + g * Phi^-1(1 - 1/(N e)) ]
#    PSR  = Phi( (SR - SR0) * sqrt(n-1) / sqrt(1 - skew*SR + (kurt-1)/4 * SR^2) )
g = np.euler_gamma
worst_dsr = 0.0
n_dsr = 0
for arm in art["arms"]:
    for v in arm["specs"].values():
        sigma_ann = v["sigma_sr_annualized"]
        sr_d = v["sharpe_net_daily"]
        for n_str, reported in v["dsr_by_n"].items():
            if reported is None:
                continue
            N = int(n_str)
            sigma_d = sigma_ann / np.sqrt(252.0)
            sr0 = sigma_d * ((1 - g) * norm.ppf(1 - 1 / N) + g * norm.ppf(1 - 1 / (N * np.e)))
            denom = 1 - v["skewness"] * sr_d + ((v["kurtosis"] - 1) / 4) * sr_d**2
            z = (sr_d - sr0) * np.sqrt(v["n_observations"] - 1) / np.sqrt(denom)
            hand = float(norm.cdf(z))
            worst_dsr = max(worst_dsr, abs(hand - reported))
            n_dsr += 1
print(f"[3] DSR retyped from the published equations: {n_dsr} values, worst "
      f"|hand - artifact| = {worst_dsr:.3e}")

# ---------------------------------------------------------------------------
# 4. The report's headline deltas, recomputed
# ---------------------------------------------------------------------------
base = art["arms"][0]["specs"]["si_ratio_hedged_h21"]
after = art["arms"][1]["specs"]["si_ratio_hedged_h21"]
print(f"[4] Sharpe {base['sharpe_annualized']:.6f} -> {after['sharpe_annualized']:.6f} "
      f"({after['sharpe_annualized'] - base['sharpe_annualized']:+.6f})")
for n in ("12", "481", "857"):
    print(f"    DSR@{n:<4s} {base['dsr_by_n'][n]:.6f} -> {after['dsr_by_n'][n]:.6f} "
          f"({after['dsr_by_n'][n] - base['dsr_by_n'][n]:+.6f})")
