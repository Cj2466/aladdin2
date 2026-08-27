"""THE real production screening of the Bonds family against live yfinance
data. Reports EVERY spec, never just the best one."""
import sys
from datetime import date

import numpy as np
import pandas as pd

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/wf_9fd00b72-30a-6/backend")

from app.services.market_data.yfinance_provider import YFinanceProvider  # noqa: E402
from app.services.research_lab.cross_sectional import (  # noqa: E402
    fixed_universe_membership,
    run_cross_sectional_backtest,
)
from app.services.research_lab.cross_sectional_bonds import (  # noqa: E402
    BONDS_COMMON_HISTORY_START,
    BONDS_FAMILY,
    BONDS_UNIVERSE,
    default_bonds_config,
    run_bonds_screening,
)

provider = YFinanceProvider()

# Pick a start at which EVERY one of the eight has a full 252-day lookback,
# so all 18 specs are on identical footing and their sibling Sharpes (which
# feed the DSR's sigma_sr) are comparable rather than apples-to-oranges.
probe_tr, _probe_px, _missing = provider.get_total_and_price_return_closes(
    list(BONDS_UNIVERSE), date(2006, 1, 1), date(2026, 8, 27)
)
common = probe_tr.dropna(axis=0, how="any")
print(f"common clean window: {common.index[0].date()} .. {common.index[-1].date()}  rows={len(common)}")
assert common.index[0].date() == BONDS_COMMON_HISTORY_START, common.index[0]
start = common.index[252].date()
end = date(2026, 8, 27)
print(f"production formation_start = {start} (row 252 of the common window: every ETF fully warm)")
print(f"production end             = {end}")

summary = run_bonds_screening(start=start, end=end, provider=provider)

print()
print("=" * 108)
print("EVERY SPEC IN THE 18-DEFINITION FAMILY (sorted by Sharpe; nothing omitted)")
print("=" * 108)
header = (
    f"{'pattern_id':<30}{'Sharpe':>9}{'DSR':>9}{'PSR>0':>9}{'days':>7}{'form':>6}"
    f"{'skip':>6}{'leg':>6}{'tradeCost':>11}{'finCost':>10}"
)
print(header)
print("-" * len(header))
for r in summary.results:
    dsr = r.deflated_sharpe
    dsr_s = f"{dsr.dsr:.3f}" if dsr.dsr is not None else "n/a"
    psr_s = f"{dsr.psr_vs_zero:.3f}" if dsr.psr_vs_zero is not None else "n/a"
    print(
        f"{r.pattern_id:<30}{r.sharpe_annualized:>+9.3f}{dsr_s:>9}{psr_s:>9}"
        f"{r.n_trading_days:>7}{r.n_formations:>6}{r.n_skipped_formations:>6}"
        f"{r.avg_names_per_leg:>6.1f}{r.total_cost_drag:>11.4f}{r.total_financing_drag:>10.4f}"
    )

print(f"\nspecs returned: {len(summary.results)} of {len(BONDS_FAMILY)} declared "
      f"(n_trials stays {BONDS_FAMILY[0] and len(BONDS_FAMILY)} regardless)")
if summary.results:
    n_trials = {r.deflated_sharpe.n_trials for r in summary.results}
    print(f"n_trials actually used by the DSR: {n_trials}")
    floor_met = {r.deflated_sharpe.dsr_floor_met for r in summary.results}
    print(f"dsr_floor_met: {floor_met}")
    print(f"\nbest raw Sharpe : {summary.results[0].pattern_id} {summary.results[0].sharpe_annualized:+.3f}")
    print(f"worst raw Sharpe: {summary.results[-1].pattern_id} {summary.results[-1].sharpe_annualized:+.3f}")
    sharpes = [r.sharpe_annualized for r in summary.results]
    print(f"mean Sharpe {np.mean(sharpes):+.3f}   median {np.median(sharpes):+.3f}   "
          f"sd {np.std(sharpes, ddof=1):.3f}   n>0: {sum(1 for s in sharpes if s > 0)}/{len(sharpes)}")
    best_dsr = max((r for r in summary.results if r.deflated_sharpe.dsr is not None),
                   key=lambda r: r.deflated_sharpe.dsr, default=None)
    if best_dsr is not None:
        print(f"best DSR        : {best_dsr.pattern_id} dsr={best_dsr.deflated_sharpe.dsr:.4f}")
        print(f"\ninterpretation for the best-DSR spec:\n  {best_dsr.deflated_sharpe.interpretation}")

print()
print("=" * 108)
print("TERM-PREMIUM DECOMPOSITION: is any of this alpha, or just duration?")
print("=" * 108)
print(f"{'pattern_id':<30}{'Sharpe':>9}{'rateBeta':>10}{'alpha/yr':>11}{'t(alpha)':>10}{'neutralSharpe':>15}")
print("-" * 85)
for r in summary.results:
    e = summary.rate_exposure[r.pattern_id]
    print(
        f"{e.pattern_id:<30}{e.sharpe:>+9.3f}{e.rate_beta:>+10.3f}"
        f"{e.alpha_annualized:>+11.3%}{e.alpha_t_stat:>+10.2f}{e.rate_neutralized_sharpe:>+15.3f}"
    )
ts = [summary.rate_exposure[r.pattern_id].alpha_t_stat for r in summary.results]
alphas = [summary.rate_exposure[r.pattern_id].alpha_annualized for r in summary.results]
print(f"\n  max t(alpha) across all {len(ts)} specs: {max(ts):+.2f}")
print(f"  specs with POSITIVE alpha: {sum(1 for a in alphas if a > 0)}/{len(alphas)}")
print(f"  specs with t(alpha) > 2.0: {sum(1 for t in ts if t > 2.0)}/{len(ts)}")

print()
print("=" * 108)
print("PER-MECHANISM DIAGNOSTICS (measured from the real replayed return streams)")
print("=" * 108)
for d in summary.mechanism_diagnostics:
    print(
        f"  {d.mechanism:<16} specs={d.n_specs_replayed:<3} meanSharpe={d.mean_sharpe:+.3f}  "
        f"bookVol={d.realized_book_volatility:.2%}  rateBeta={d.realized_rate_beta:+.3f}  "
        f"neutralSharpe={d.rate_neutralized_sharpe:+.3f}  t(alpha)={d.alpha_t_stat:+.2f}"
    )
print("\n  cross-mechanism return-stream correlations (are these independent axes?):")
for (a, b), c in sorted(summary.mechanism_correlations.items()):
    print(f"    corr({a}, {b}) = {c:+.3f}")

print()
print("=" * 108)
print("COST DISCLOSURE")
print("=" * 108)
print(summary.disclosure)

print()
print("=" * 108)
print("REALIZED COST DRAG, computed from the run's OWN volatility (not the design estimate)")
print("=" * 108)
config = default_bonds_config()
config.formation_start = start
tr, px, _ = provider.get_total_and_price_return_closes(list(BONDS_UNIVERSE), date(2006, 1, 1), end)
from app.services.research_lab.cross_sectional import CrossSectionalData  # noqa: E402

data = CrossSectionalData(close=tr, price_only_close=px)
membership = fixed_universe_membership(BONDS_UNIVERSE)
spec_by_id = {s.pattern_id: s for s in BONDS_FAMILY}
print(f"{'pattern_id':<30}{'annVol':>9}{'costs/yr':>10}{'fin/yr':>9}{'total/yr':>10}{'SharpeDrag':>12}")
print("-" * 80)
for r in sorted(summary.results, key=lambda x: x.pattern_id):
    replay = run_cross_sectional_backtest(data, spec_by_id[r.pattern_id], config, membership)
    series = replay.daily_returns
    years = len(series) / 252.0
    vol = float(series.std(ddof=1) * np.sqrt(252))
    cost_yr = r.total_cost_drag / years
    fin_yr = r.total_financing_drag / years
    drag = (cost_yr + fin_yr) / vol if vol > 0 else float("nan")
    print(f"{r.pattern_id:<30}{vol:>9.2%}{cost_yr:>10.4%}{fin_yr:>9.4%}{(cost_yr+fin_yr):>10.4%}{drag:>12.3f}")

print()
print("=" * 108)
print("LEG COMPOSITION (what each mechanism actually traded)")
print("=" * 108)
for pattern_id in ("bonds_curve_carry_l252_h126", "bonds_butterfly_l252_h126", "bonds_credit_hedged_l252_h126"):
    replay = run_cross_sectional_backtest(data, spec_by_id[pattern_id], config, membership)
    formed = [f for f in replay.formations if f.skipped_reason is None]
    longs, shorts = {}, {}
    for f in formed:
        longs[tuple(sorted(f.long_tickers))] = longs.get(tuple(sorted(f.long_tickers)), 0) + 1
        shorts[tuple(sorted(f.short_tickers))] = shorts.get(tuple(sorted(f.short_tickers)), 0) + 1
    print(f"\n  {pattern_id}  ({len(formed)} formed, {len(replay.formations)-len(formed)} skipped)")
    print("    long leg :", ", ".join(f"{'+'.join(k)}x{v}" for k, v in sorted(longs.items(), key=lambda kv: -kv[1])[:6]))
    print("    short leg:", ", ".join(f"{'+'.join(k)}x{v}" for k, v in sorted(shorts.items(), key=lambda kv: -kv[1])[:6]))

print()
print("missing price data:", summary.missing_price_data)
