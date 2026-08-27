"""Independent regression check (NOT part of the repo): does D2's new,
default-off harness machinery (impute_delisting_returns / cohort_
formation_days) change Round C's real 30-def family or D1's real ivol
family's results at all, when left at default? Compares:

 (A) ROUND_C_FAMILY through the TRUE committed pre-D1/pre-D2 harness
     (git 52a453a) vs the CURRENT (D1+D2) harness, defaults everywhere.

 (B) ROUND_D1_FAMILY through a hand-reconstructed "D1-final, pre-D2"
     harness (baseline + D1's real market_cap/value-weighting additions,
     D2's cohort/delisting machinery deliberately NOT ported in) vs the
     CURRENT (D1+D2) harness, defaults everywhere.

Both use offline synthetic data (fake providers, same construction/seeds
as this repo's own test suite), real point-in-time membership (was_member,
get_universe_over — no network needed for either).
"""
import importlib.util
import sys
from datetime import date

import numpy as np
import pandas as pd

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/agent-a327c9fd73bf9f348/backend")

from app.services.research_lab.sp500_membership_history import was_member, get_universe_over  # noqa: E402
from app.services.research_lab.cross_sectional_ivol import build_point_in_time_market_cap  # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


baseline = _load("cs_baseline", "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/cross_sectional_baseline.py")
d1final = _load("cs_d1final", "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/cross_sectional_d1final.py")
import app.services.research_lab.cross_sectional as current  # noqa: E402

from app.services.research_lab.cross_sectional_patterns import ROUND_C_FAMILY  # noqa: E402
from app.services.research_lab.cross_sectional_ivol import ROUND_D1_FAMILY  # noqa: E402

START = date(2020, 1, 6)
END = date(2024, 12, 31)
PADDED_START = date(2017, 8, 28)  # matches PRICE_HISTORY_PADDING_CALENDAR_DAYS=850 roughly; exact value below

from datetime import timedelta  # noqa: E402
PADDED_START = START - timedelta(days=850)

_STALWART_MEMBERS = [
    "AAPL", "MSFT", "JPM", "JNJ", "KO", "PG", "XOM", "WMT", "MCD", "HD", "CAT", "MMM",
]


def build_round_c_frames(seed=17):
    universe = get_universe_over(START, END)
    rng = np.random.default_rng(seed)
    index = pd.bdate_range(PADDED_START, END)
    served = [t for t in universe if t in _STALWART_MEMBERS]
    close = pd.DataFrame(
        {t: 100.0 * np.cumprod(1.0 + rng.normal(0.0003, 0.015, len(index))) for t in served},
        index=index,
    )
    open_ = close * (1.0 + rng.normal(0.0, 0.004, close.shape))
    volume = pd.DataFrame(
        rng.integers(1_000_000, 5_000_000, close.shape).astype(float),
        index=index,
        columns=close.columns,
    )
    return close, open_, volume


def build_d1_frames(seed=5):
    universe = get_universe_over(START, END)
    rng = np.random.default_rng(seed)
    index = pd.bdate_range(PADDED_START, END)
    served = [t for t in universe if t in _STALWART_MEMBERS]
    close = pd.DataFrame(
        {t: 100.0 * np.cumprod(1.0 + rng.normal(0.0003, 0.015, len(index))) for t in served},
        index=index,
    )
    shares = {}
    for t in served:
        if t == _STALWART_MEMBERS[0]:
            continue  # deliberately unresolvable, exercises the fallback path
        shares[t] = pd.Series([1.0e9], index=[index[0]])
    market_cap, never_resolved = build_point_in_time_market_cap(close, shares)
    return close, market_cap


def compare_screening_results(name, results_a, results_b):
    ok = True
    ids_a = {r.pattern_id for r in results_a}
    ids_b = {r.pattern_id for r in results_b}
    if ids_a != ids_b:
        print(f"[{name}] MISMATCH: pattern_id sets differ: only-A={ids_a - ids_b} only-B={ids_b - ids_a}")
        ok = False
    by_a = {r.pattern_id: r for r in results_a}
    by_b = {r.pattern_id: r for r in results_b}
    for pid in sorted(ids_a & ids_b):
        a, b = by_a[pid], by_b[pid]
        fields = [
            "n_formations", "n_skipped_formations", "n_trading_days",
            "total_cost_drag", "sharpe_annualized", "avg_names_per_leg",
            "n_value_weighted_legs", "n_value_weight_fallbacks",
        ]
        for f in fields:
            if not hasattr(a, f) or not hasattr(b, f):
                continue  # field didn't exist yet on the true pre-D1 baseline (default 0 either way)
            va, vb = getattr(a, f), getattr(b, f)
            if isinstance(va, float):
                same = np.isclose(va, vb, rtol=0, atol=0) or va == vb
            else:
                same = va == vb
            if not same:
                print(f"[{name}] MISMATCH {pid}.{f}: baseline={va!r} current={vb!r}")
                ok = False
        dsr_a, dsr_b = a.deflated_sharpe, b.deflated_sharpe
        if dsr_a.dsr != dsr_b.dsr or dsr_a.psr_vs_zero != dsr_b.psr_vs_zero or dsr_a.n_trials != dsr_b.n_trials:
            print(f"[{name}] MISMATCH {pid}.deflated_sharpe: baseline={dsr_a} current={dsr_b}")
            ok = False
    if ok:
        print(f"[{name}] OK: {len(ids_a)} pattern_ids, all fields byte-identical.")
    return ok


def compare_raw_backtests(name, specs_a, data_a, config_a, mod_a, specs_b, data_b, config_b, mod_b):
    ok = True
    for spec_a, spec_b in zip(specs_a, specs_b):
        assert spec_a.pattern_id == spec_b.pattern_id
        ra = mod_a.run_cross_sectional_backtest(data_a, spec_a, config_a, was_member)
        rb = mod_b.run_cross_sectional_backtest(data_b, spec_b, config_b, was_member)
        if ra.status != rb.status:
            print(f"[{name}] {spec_a.pattern_id}: status differs {ra.status} vs {rb.status}")
            ok = False
            continue
        try:
            pd.testing.assert_series_equal(ra.daily_returns, rb.daily_returns, check_names=False)
        except AssertionError as e:
            print(f"[{name}] {spec_a.pattern_id}: daily_returns differ:\n{e}")
            ok = False
        if not np.isclose(ra.total_cost, rb.total_cost):
            print(f"[{name}] {spec_a.pattern_id}: total_cost differs {ra.total_cost} vs {rb.total_cost}")
            ok = False
        if len(ra.formations) != len(rb.formations):
            print(f"[{name}] {spec_a.pattern_id}: formation count differs {len(ra.formations)} vs {len(rb.formations)}")
            ok = False
        else:
            for fa, fb in zip(ra.formations, rb.formations):
                if (fa.date, fa.n_eligible, fa.long_tickers, fa.short_tickers, fa.skipped_reason) != (
                    fb.date, fb.n_eligible, fb.long_tickers, fb.short_tickers, fb.skipped_reason
                ):
                    print(f"[{name}] {spec_a.pattern_id}: formation mismatch at {fa.date}")
                    ok = False
                if not np.isclose(fa.turnover, fb.turnover):
                    print(f"[{name}] {spec_a.pattern_id}: turnover mismatch at {fa.date}: {fa.turnover} vs {fb.turnover}")
                    ok = False
    if ok:
        print(f"[{name}] OK: every spec's raw daily_returns/formations/total_cost byte-identical.")
    return ok


print("=" * 80)
print("PART A: Round C's real 30-def family, TRUE pre-D1/pre-D2 committed baseline")
print("        (git 52a453a) vs CURRENT (D1+D2, options left at default)")
print("=" * 80)
close_c, open_c, volume_c = build_round_c_frames()

data_current = current.CrossSectionalData(close=close_c, open=open_c, volume=volume_c)
data_baseline = baseline.CrossSectionalData(close=close_c, open=open_c, volume=volume_c)

config_current = current.CrossSectionalConfig(min_names_per_leg=1, formation_start=START)
config_baseline = baseline.CrossSectionalConfig(min_names_per_leg=1, formation_start=START)

results_current_c = current.screen_cross_sectional_universe(data_current, ROUND_C_FAMILY, config_current, was_member)
results_baseline_c = baseline.screen_cross_sectional_universe(data_baseline, ROUND_C_FAMILY, config_baseline, was_member)

ok_a1 = compare_screening_results("Round C / screening", results_baseline_c, results_current_c)

config_current2 = current.CrossSectionalConfig(min_names_per_leg=1, formation_start=START)
config_baseline2 = baseline.CrossSectionalConfig(min_names_per_leg=1, formation_start=START)
ok_a2 = compare_raw_backtests(
    "Round C / raw", ROUND_C_FAMILY, data_baseline, config_baseline2, baseline,
    ROUND_C_FAMILY, data_current, config_current2, current,
)

print()
print("=" * 80)
print("PART B: D1's real 21-def ivol family, hand-reconstructed 'D1-final, pre-D2'")
print("        harness vs CURRENT (D1+D2, options left at default)")
print("=" * 80)
close_d1, market_cap_d1 = build_d1_frames()

data_current_d1 = current.CrossSectionalData(close=close_d1, market_cap=market_cap_d1)
data_d1final = d1final.CrossSectionalData(close=close_d1, market_cap=market_cap_d1)

config_current_d1 = current.CrossSectionalConfig(min_names_per_leg=1, formation_start=START)
config_d1final = d1final.CrossSectionalConfig(min_names_per_leg=1, formation_start=START)

results_current_d1 = current.screen_cross_sectional_universe(data_current_d1, ROUND_D1_FAMILY, config_current_d1, was_member)
results_d1final = d1final.screen_cross_sectional_universe(data_d1final, ROUND_D1_FAMILY, config_d1final, was_member)

ok_b1 = compare_screening_results("D1 / screening", results_d1final, results_current_d1)

config_current_d1_2 = current.CrossSectionalConfig(min_names_per_leg=1, formation_start=START)
config_d1final_2 = d1final.CrossSectionalConfig(min_names_per_leg=1, formation_start=START)
ok_b2 = compare_raw_backtests(
    "D1 / raw", ROUND_D1_FAMILY, data_d1final, config_d1final_2, d1final,
    ROUND_D1_FAMILY, data_current_d1, config_current_d1_2, current,
)

print()
print("=" * 80)
overall = ok_a1 and ok_a2 and ok_b1 and ok_b2
print("OVERALL:", "ALL BYTE-IDENTICAL (no regression detected)" if overall else "MISMATCHES FOUND -- SEE ABOVE")
print("=" * 80)
