import numpy as np
import pandas as pd

def get_weights_ffd(d, threshold=1e-4, max_width=2000):
    w = [1.0]
    k = 1
    while k < max_width:
        w_k = -w[-1] / k * (d - k + 1)
        if abs(w_k) < threshold:
            break
        w.append(w_k)
        k += 1
    return np.array(w)  # w[0]=weight on lag 0 (current), w[1]=lag1, ... (NOT reversed)

def frac_diff_ffd(series: np.ndarray, d: float, threshold=1e-4) -> np.ndarray:
    """Causal, fixed-width-window fractional differentiation (Lopez de
    Prado, AFML ch.5). output[i] uses series[i], series[i-1], ..., series[i-width]
    only -- no lookahead. First `width` entries are NaN (burn-in)."""
    w = get_weights_ffd(d, threshold)
    width = len(w) - 1
    n = len(series)
    out = np.full(n, np.nan)
    if width >= n:
        return out
    # out[i] = sum_k w[k] * series[i-k]  for k=0..width
    for i in range(width, n):
        out[i] = np.dot(w, series[i - np.arange(len(w))])
    return out
