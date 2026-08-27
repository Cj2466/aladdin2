"""Profile run_pattern_backtest per-bar cost at 15Min (window 60) and
1Min (window 400) on real AAPL bars, to size Phase B's screen honestly."""

import pickle
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")

from app.services.market_data.alpaca_provider import AlpacaProvider
from app.services.research_lab.engine import WalkForwardConfig, run_walk_forward
from app.services.research_lab.intraday_patterns import (
    INTRADAY_COST_BPS,
    PATTERN_FAMILY,
    _make_fit_fn,
    apply_pattern_signal_rule,
    build_pattern_raw_data,
    realize_pattern_return,
)

CACHE = Path("/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/bars_cache")


def load_bars(ticker, timeframe, start, end):
    p = CACHE / f"{ticker}_{timeframe}.pkl"
    if p.exists():
        return pickle.loads(p.read_bytes())
    bars, _ = AlpacaProvider().get_stock_bars([ticker], timeframe, start, end)
    p.write_bytes(pickle.dumps(bars[ticker]))
    return bars[ticker]


def bench(raw, fit_window, spec, n_note):
    config = WalkForwardConfig(fit_window_days=fit_window, entry_z=0.0, exit_z=0.0, cost_bps=INTRADAY_COST_BPS)
    t0 = time.time()
    result = run_walk_forward(
        raw, config, _make_fit_fn(spec.fire_fn), realize_pattern_return,
        decide_position_fn=apply_pattern_signal_rule, direction_labels=("long", "short"),
    )
    dt = time.time() - t0
    steps = len(raw) - fit_window
    print(f"{n_note:34s} {spec.pattern_id[:44]:44s} steps={steps:7d} secs={dt:7.2f} us/step={dt/steps*1e6:7.1f} trades={len(result.trades)}")
    return dt / steps


by_id = {p.pattern_id: p for p in PATTERN_FAMILY}
picks = [
    "orb_continuation_open_0.0010",           # gated, cheap early exit most bars
    "vwap_reversion_typical_midday_0.004",    # same-day mask work
    "rsi_extreme_14_70_30_midday",            # rolling closes
    "ma_crossover_5_13",                      # ungated, rolling means every bar
    "day_of_week_monday_long",                # trade-heavy
    "engulfing_midday",                       # candlestick
]

m15 = build_pattern_raw_data(load_bars("AAPL", "15Min", date(2021, 1, 4), date(2026, 8, 24)))
print(f"15Min AAPL: {len(m15)} bars")
rates15 = [bench(m15, 60, by_id[i], "15Min/window60") for i in picks]

m1 = build_pattern_raw_data(load_bars("AAPL", "1Min", date(2024, 8, 26), date(2026, 8, 24)))
print(f"1Min AAPL: {len(m1)} bars")
# subset: first 40k bars to keep the profile quick
m1s = m1.iloc[:40000]
rates1 = [bench(m1s, 400, by_id[i], "1Min/window400") for i in picks[:4]]

avg15 = sum(rates15) / len(rates15)
avg1 = sum(rates1) / len(rates1)
print(f"\navg us/step 15Min/w60: {avg15*1e6:.1f}   1Min/w400: {avg1*1e6:.1f}")
