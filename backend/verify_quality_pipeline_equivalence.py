"""THE claim that matters most in item 1: does each new adapter hand the
forward ticker EXACTLY the CrossSectionalData that the family's own
production entry point hands screen_cross_sectional_universe?

Method: drive run_quality_screening / run_noa_neutral_screening and the new
build_*_live_panel with the SAME fake providers, intercept the real
screen_cross_sectional_universe to capture the CrossSectionalData and
membership_fn it was actually given, and compare the two element-wise. This
does not read the adapter's docstring or the builder's tests for its answer.
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.services.market_data.edgar_xbrl_provider import LineItemExtraction, SicHistory
from app.services.research_lab import cross_sectional_forward_registry as reg
from app.services.research_lab import cross_sectional_quality as q
from app.services.research_lab import cross_sectional_quality_neutral as qn
from app.services.research_lab.cross_sectional_quality import build_quality_sample
from app.services.research_lab.sp500_membership_history import (
    MEMBERSHIP_DATA_AS_OF,
    MEMBERSHIP_DATA_START,
    was_member,
)

TODAY = date.today()
N = 40

sample, _size = build_quality_sample(MEMBERSHIP_DATA_START, MEMBERSHIP_DATA_AS_OF)
tickers = [t for t in sample if was_member(t, TODAY)][:N]
assert len(tickers) == N, len(tickers)
print(f"{len(tickers)} live members drawn from the families' own seeded sample")

dates = pd.bdate_range(end=pd.Timestamp(TODAY) - pd.Timedelta(days=1), periods=140)
rng = np.random.default_rng(7)
CLOSE = pd.DataFrame(
    {t: 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.01, len(dates)))) for t in tickers},
    index=dates,
)

SIC_FOR_BUCKET = {
    "reit": 6798, "financial": 6021, "tech": 7372, "healthcare": 2834,
    "energy_utility": 4911, "telecom_media": 4813, "consumer": 5812, "industrial": 3714,
}


def _resolved(v, filed):
    from app.services.market_data.edgar_xbrl_provider import ResolvedItem

    return ResolvedItem(value=v, filed=filed, tag="synthetic:Tag", tier=0)


def _extraction(i: int) -> LineItemExtraction:
    """Three consecutive fiscal years of every line item _ITEM_RESOLVERS
    produces, gapped inside the family's 250..480-day annual-pair window."""
    last_end = TODAY - timedelta(days=240)
    ends = [last_end - timedelta(days=730), last_end - timedelta(days=365), last_end]
    flat = {
        "assets": 1000.0, "revenue": 500.0, "cogs": 250.0 + 2.0 * i, "sga": 50.0,
        "cash_and_short_term_investments": 100.0, "common_equity": 300.0 + 10.0 * i,
        "short_term_debt": 50.0, "long_term_debt": 200.0,
        "minority_interest": 0.0, "preferred_stock": 0.0,
        "receivables": 40.0, "inventory": 30.0, "prepaid": 10.0,
        "deferred_revenue": 20.0, "accounts_payable": 25.0, "accrued_expenses": 15.0,
    }
    return LineItemExtraction(
        items={n: {e: _resolved(v, e + timedelta(days=60)) for e in ends} for n, v in flat.items()}
    )


EXTRACTIONS = {t: _extraction(i) for i, t in enumerate(tickers)}
SIC_HISTORIES = {
    t: SicHistory(
        cik=1000 + i,
        events=[(TODAY - timedelta(days=3000), SIC_FOR_BUCKET[qn.SECTOR_BUCKETS[i % 8]])],
        current_sic=SIC_FOR_BUCKET[qn.SECTOR_BUCKETS[i % 8]],
    )
    for i, t in enumerate(tickers)
}


class FakeYF:
    def __init__(self):
        self.calls = []

    def get_price_history(self, tks, start, end):
        self.calls.append((list(tks), start, end))
        return CLOSE.copy(), [t for t in tks if t not in CLOSE.columns]


class FakeEdgar:
    def __init__(self):
        self.calls = []

    def fetch_line_items_for_tickers(self, tks):
        self.calls.append(("line_items", list(tks)))
        return {t: e for t, e in EXTRACTIONS.items() if t in set(tks)}, \
            sorted(t for t in tks if t not in EXTRACTIONS), []

    def fetch_sic_history_for_tickers(self, tks):
        self.calls.append(("sic", list(tks)))
        return {t: h for t, h in SIC_HISTORIES.items() if t in set(tks)}, [], []


captured = []
real_screen = q.screen_cross_sectional_universe


def _capture(data, specs, config, *a, **kw):
    captured.append({"data": data, "specs": specs, "config": config,
                     "membership_fn": kw.get("membership_fn"), "kwargs": dict(kw)})
    return []  # skip the (slow) backtests; we only need what was handed in


def compare(label, a: pd.DataFrame, b: pd.DataFrame) -> bool:
    if a is None or b is None:
        print(f"  {'PASS' if a is b else '**FAIL**'} {label}: both None? {a is None}/{b is None}")
        return a is b
    same = a.equals(b)
    if not same:
        same = a.shape == b.shape and list(a.columns) == list(b.columns) \
            and a.index.equals(b.index) and np.allclose(
                a.to_numpy(dtype=float), b.to_numpy(dtype=float), equal_nan=True)
    print(f"  {'PASS' if same else '**FAIL**'} {label}  shape={a.shape} vs {b.shape}")
    return same


fails = 0

print()
print("=" * 78)
print("CbOP: run_quality_screening vs build_cbop_live_panel")
print("=" * 78)
q.screen_cross_sectional_universe = _capture
try:
    yf1, ed1 = FakeYF(), FakeEdgar()
    q.run_quality_screening(end=TODAY, provider=yf1, edgar=ed1)
finally:
    q.screen_cross_sectional_universe = real_screen

prod_cbop = captured[0]  # first screen call is CBOP_FAMILY
print(f"  production screened family: {prod_cbop['specs'][0].family}")
assert prod_cbop["specs"][0].family == "cash_operating_profitability"

yf2, ed2 = FakeYF(), FakeEdgar()
panel = reg.build_cbop_live_panel(TODAY, provider=yf2, edgar=ed2)

fails += not compare("close panel identical", prod_cbop["data"].close, panel.data.close)
fails += not compare("fundamental_signal identical",
                     prod_cbop["data"].fundamental_signal, panel.data.fundamental_signal)
ok = prod_cbop["data"].leg_weight_basis is None and panel.data.leg_weight_basis is None
print(f"  {'PASS' if ok else '**FAIL**'} both leg_weight_basis None")
fails += not ok
ok = prod_cbop["kwargs"].get("membership_fn") is None and panel.membership_fn is was_member
print(f"  {'PASS' if ok else '**FAIL**'} production passes membership_fn=None (-> harness default "
      f"was_member); adapter installs was_member itself")
fails += not ok
ok = ed1.calls[0][1] == ed2.calls[0][1] == sample
print(f"  {'PASS' if ok else '**FAIL**'} both asked EDGAR for the identical 200-name seeded sample")
fails += not ok
ok = yf1.calls[0][0] == yf2.calls[0][0] and yf1.calls[0][1] == yf2.calls[0][1]
print(f"  {'PASS' if ok else '**FAIL**'} identical price request (tickers + padded start): "
      f"start={yf2.calls[0][1]} end={yf2.calls[0][2]}")
fails += not ok
ok = [c[0] for c in ed2.calls] == ["line_items"]
print(f"  {'PASS' if ok else '**FAIL**'} CbOP adapter makes NO SIC call (the sibling's step, "
      f"correctly absent): {[c[0] for c in ed2.calls]}")
fails += not ok

print()
print("=" * 78)
print("NOA-neutral: run_noa_neutral_screening vs build_noa_neutral_live_panel")
print("=" * 78)
captured.clear()
qn.screen_cross_sectional_universe = _capture
try:
    yf3, ed3 = FakeYF(), FakeEdgar()
    qn.run_noa_neutral_screening(end=TODAY, provider=yf3, edgar=ed3)
finally:
    qn.screen_cross_sectional_universe = real_screen

prod_noa = captured[0]
print(f"  production screened family: {prod_noa['specs'][0].family}")
print(f"  production n_trials_override: {prod_noa['kwargs'].get('n_trials_override')}")
ok = prod_noa["kwargs"].get("n_trials_override") == 18 == reg.get_family_adapter(
    "quality_noa_industry_neutral").n_trials
print(f"  {'PASS' if ok else '**FAIL**'} the adapter's n_trials IS the override the production "
      f"screening actually applied (18, not the family's own 9 = {qn.NOA_NEUTRAL_N_TRIALS})")
fails += not ok

reg._QUALITY_PANEL_MEMO.clear()
reg._LIVE_NOA_NEUTRAL_BUCKET_FRAME = None
yf4, ed4 = FakeYF(), FakeEdgar()
panel_n = reg.build_noa_neutral_live_panel(TODAY, provider=yf4, edgar=ed4)

fails += not compare("close panel identical", prod_noa["data"].close, panel_n.data.close)
fails += not compare("fundamental_signal (NOA) identical",
                     prod_noa["data"].fundamental_signal, panel_n.data.fundamental_signal)

# The bucket frame the production run bound its specs to, vs the one the
# adapter published for build_noa_neutral_live_specs to bind to.
prod_bucket = prod_noa["specs"][0].signal_fn.keywords["bucket_frame"]
live_bucket = reg._LIVE_NOA_NEUTRAL_BUCKET_FRAME
ok = prod_bucket.equals(live_bucket)
print(f"  {'PASS' if ok else '**FAIL**'} the PUBLISHED bucket panel equals the one the production "
      f"screening bound its specs to  {prod_bucket.shape} vs {live_bucket.shape}")
fails += not ok

bound = reg.build_noa_neutral_live_specs()
target = next(s for s in bound if s.pattern_id == "noa_neutral_ls_h126_median")
ok = target.signal_fn.keywords["bucket_frame"] is live_bucket
print(f"  {'PASS' if ok else '**FAIL**'} resolve_spec AFTER build_live_panel binds the spec to the "
      f"panel that build actually published (not the identity-only frame)")
fails += not ok
ok = target.signal_fn.keywords["statistic"] == "median"
print(f"  {'PASS' if ok else '**FAIL**'} ...and to the registered 'median' statistic")
fails += not ok
ok = ed4.calls[1][1] == ed3.calls[1][1]
print(f"  {'PASS' if ok else '**FAIL**'} SIC history requested for the identical ticker list "
      f"(sample minus missing-CIK), {len(ed4.calls[1][1])} names")
fails += not ok
ok = sorted(c[0] for c in ed4.calls) == sorted(c[0] for c in ed3.calls) == ["line_items", "sic"]
print(f"  {'PASS' if ok else '**FAIL**'} same set of EDGAR calls; ORDER differs (prod "
      f"{[c[0] for c in ed3.calls]} vs adapter {[c[0] for c in ed4.calls]}) but the SIC fetch's "
      f"only input is missing_cik from the line-item fetch, so the order is not load-bearing")
fails += not ok

print()
print("=" * 78)
print(f"{'ALL EQUIVALENCE CHECKS PASSED' if not fails else f'{fails} EQUIVALENCE CHECK(S) FAILED'}")
print("=" * 78)
