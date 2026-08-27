import sys
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/agent-a327c9fd73bf9f348/backend")
import numpy as np
import pandas as pd
from app.services.research_lab.cross_sectional_ivol import signal_idiosyncratic_volatility
from app.services.research_lab.cross_sectional import CrossSectionalData

np.random.seed(7)
n = 40
tickers = ["A","B","C","D","E"]
dates = pd.bdate_range("2024-01-02", periods=n+1)
rets = pd.DataFrame(np.random.normal(0, 0.01, size=(n, len(tickers))), columns=tickers)
close = pd.DataFrame(index=dates, columns=tickers, dtype=float)
close.iloc[0] = 100.0
for i in range(1, n+1):
    close.iloc[i] = close.iloc[i-1].to_numpy() * (1 + rets.iloc[i-1].to_numpy())

view = CrossSectionalData(close=close)
result = signal_idiosyncratic_volatility(view, lookback_days=n)

# Independent re-derivation via numpy.polyfit, market = mean of OTHER tickers'
# returns for each ticker (matching the module's own stated "mean of the whole
# eligible cross-section" -- note: includes itself in the mean, per the code
# `returns.mean(axis=1)` over ALL columns incl. the ticker itself).
returns = close.pct_change(fill_method=None).iloc[1:]
market = returns.mean(axis=1)
expected = {}
for t in tickers:
    y = returns[t].to_numpy()
    x = market.to_numpy()
    beta, alpha = np.polyfit(x, y, 1)
    resid = y - (alpha + beta * x)
    expected[t] = -float(np.std(resid, ddof=1))

print("module result:", dict(result))
print("independent polyfit result:", expected)
for t in tickers:
    diff = abs(result[t] - expected[t])
    print(f"{t}: module={result[t]:.10f} polyfit={expected[t]:.10f} diff={diff:.2e}")
    assert diff < 1e-9, f"MISMATCH for {t}"
print("\nIVOL regression math independently verified via numpy.polyfit: MATCH.")

# Also verify raw_vol=True path
result_raw = signal_idiosyncratic_volatility(view, lookback_days=n, raw_vol=True)
for t in tickers:
    expected_raw = -float(returns[t].std(ddof=1))
    diff = abs(result_raw[t] - expected_raw)
    assert diff < 1e-9, f"raw_vol MISMATCH for {t}: {result_raw[t]} vs {expected_raw}"
print("raw_vol=True path independently verified: MATCH.")

# Sign convention check: manufacture a ticker with a KNOWN, deliberately tiny
# residual (near-zero idiosyncratic vol) vs one with deliberately huge residual,
# confirm the near-zero-vol ticker gets the LARGER (least negative) signal value
# -- i.e. ranks into the LONG leg, per AHXZ direction.
close2 = close.copy()
close2["LOWVOL"] = close2["A"]  # will overwrite with market-tracking series below
# Build a ticker that's an exact linear function of the mean market return (zero residual)
mkt_ret = market
lowvol_close = [100.0]
for r in mkt_ret:
    lowvol_close.append(lowvol_close[-1] * (1 + r))
close2["LOWVOL"] = lowvol_close
view2 = CrossSectionalData(close=close2)
sig2 = signal_idiosyncratic_volatility(view2, lookback_days=n)
print("\nLOWVOL (zero-idio-vol, tracks market exactly) signal:", sig2["LOWVOL"], " vs others:", dict(sig2.drop("LOWVOL")))
assert sig2["LOWVOL"] == max(sig2), "LOWVOL should have the LARGEST (least negative) signal -> long leg"
print("Sign convention confirmed: near-zero-IVOL ticker gets the largest signal value -> ranks into LONG leg (AHXZ direction).")
