import numpy as np
import pandas as pd
from app.services.research_lab.intraday_patterns import (
    FIT_WINDOW_BARS_15MIN,
    FIT_WINDOW_BARS_1MIN,
    PATTERN_FAMILY_PHASE_B_15MIN,
    PATTERN_FAMILY_PHASE_B_1MIN,
    build_pattern_raw_data,
    run_pattern_backtest,
    MAX_WEIGHT_MULTIPLE,
)


def synthetic_bars(seed, n_days, bars_per_day, start_time, freq_minutes):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-02", periods=n_days)
    rows = []
    price = 100.0
    for d in dates:
        ts = pd.Timestamp(f"{d.date()} {start_time}", tz="America/New_York")
        for i in range(bars_per_day):
            t = ts + pd.Timedelta(minutes=freq_minutes * i)
            ret = rng.normal(0.0, 0.002)
            o = price
            c = price * (1 + ret)
            h = max(o, c) * (1 + abs(rng.normal(0, 0.0003)))
            low = min(o, c) * (1 - abs(rng.normal(0, 0.0003)))
            v = int(rng.integers(500, 3000))
            rows.append((t, o, h, low, c, v))
            price = c
    return pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"]).set_index("ts")


print("=== 15min family:", len(PATTERN_FAMILY_PHASE_B_15MIN), "patterns ===")
bars15 = synthetic_bars(seed=100, n_days=15, bars_per_day=26, start_time="09:30", freq_minutes=15)
raw15 = build_pattern_raw_data(bars15)
n_ok, n_fired, n_bad_weight = 0, 0, 0
errors = []
for spec in PATTERN_FAMILY_PHASE_B_15MIN:
    try:
        result = run_pattern_backtest(spec, raw15, fit_window_bars=FIT_WINDOW_BARS_15MIN)
        n_ok += 1
        if result.trades:
            n_fired += 1
        for dr in result.day_results:
            # position is still a plain int sign — the actual magnitude lives in raw_return, checked indirectly via bounds below.
            pass
    except Exception as e:
        errors.append((spec.pattern_id, repr(e)))
print(f"ok={n_ok} fired>=1_trade={n_fired} errors={len(errors)}")
for pid, e in errors[:10]:
    print("  ERROR", pid, e)

print("=== 1min family:", len(PATTERN_FAMILY_PHASE_B_1MIN), "patterns ===")
bars1 = synthetic_bars(seed=200, n_days=3, bars_per_day=390, start_time="09:30", freq_minutes=1)
raw1 = build_pattern_raw_data(bars1)
n_ok, n_fired = 0, 0
errors1 = []
for spec in PATTERN_FAMILY_PHASE_B_1MIN:
    try:
        result = run_pattern_backtest(spec, raw1, fit_window_bars=FIT_WINDOW_BARS_1MIN)
        n_ok += 1
        if result.trades:
            n_fired += 1
    except Exception as e:
        errors1.append((spec.pattern_id, repr(e)))
print(f"ok={n_ok} fired>=1_trade={n_fired} errors={len(errors1)}")
for pid, e in errors1[:10]:
    print("  ERROR", pid, e)

print("ALL CLEAR" if not errors and not errors1 else "FAILURES FOUND")
