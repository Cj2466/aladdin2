import sys
from datetime import date

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
from app.services.market_data.alpaca_provider import AlpacaProvider  # noqa: E402

provider = AlpacaProvider()

print("=== Coverage floor check (still-active ticker, wide window) ===")
bars, missing = provider.get_stock_bars(["AAPL"], "1Day", date(2000, 1, 1), date(2016, 12, 31))
if "AAPL" in bars:
    f = bars["AAPL"]
    print("AAPL first bar:", f.index[0].date(), "n=", len(f))
print("missing:", missing)

print()
print("=== MON extended window past known 2018-06-07 Bayer deal close ===")
bars, missing = provider.get_stock_bars(["MON"], "1Day", date(2018, 1, 1), date(2019, 12, 31))
if "MON" in bars:
    f = bars["MON"]
    print("MON first bar:", f.index[0].date(), "last bar:", f.index[-1].date(), "n=", len(f))
    print(f.tail(10))
else:
    print("MON missing in this window:", missing)

print()
print("=== SIAL / FDO / DTV / TE: any data at all, any era ===")
for t in ["SIAL", "FDO", "DTV", "TE"]:
    bars, missing = provider.get_stock_bars([t], "1Day", date(2010, 1, 1), date(2026, 1, 1))
    if t in bars:
        f = bars[t]
        print(t, "HAS DATA:", f.index[0].date(), "to", f.index[-1].date(), "n=", len(f))
    else:
        print(t, "NO DATA AT ALL (any era 2010-2026)")
