import pandas as pd
from app.services.research_lab.intraday_patterns import (
    _fire_rsi_extreme, _signal_weight_magnitude, PATTERN_FAMILY,
)

spec = next(p for p in PATTERN_FAMILY if p.family == "rsi_extreme_wilder1978" and "_70_30_" in p.pattern_id)
print("spec:", spec.pattern_id, "strength_scale=", spec.strength_scale, "is_margin=", spec.strength_is_margin)


def make_window(ups, downs):
    closes = [100.0]
    for d in ups + downs:
        closes.append(closes[-1] + d)
    return pd.DataFrame({"close": closes})


def rsi_for_ratio(period, gain, loss):
    n_up = period // 2
    n_down = period - n_up
    ups = [gain] * n_up
    downs = [-loss] * n_down
    w = make_window(ups, downs)
    closes = w["close"]
    deltas = closes.diff().dropna()
    avg_gain = deltas.clip(lower=0).mean()
    avg_loss = (-deltas.clip(upper=0)).mean()
    rsi = 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
    return rsi, w


for gain in [0.5, 1.0, 1.5, 2.0, 3.0, 5.0]:
    rsi, w = rsi_for_ratio(14, gain, 1.0)
    sig = _fire_rsi_extreme(w, period=14, overbought=70.0, oversold=30.0)
    ratio = _signal_weight_magnitude(sig, spec) if sig else None
    print(f"gain={gain:.2f} rsi={rsi:.3f} signal={sig} weight_ratio={ratio}")
