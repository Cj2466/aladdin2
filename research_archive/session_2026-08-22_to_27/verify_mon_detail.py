import sys
from datetime import date

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
from app.services.market_data.alpaca_provider import AlpacaProvider  # noqa: E402

provider = AlpacaProvider()
bars, missing = provider.get_stock_bars(["MON"], "1Day", date(2018, 5, 1), date(2018, 7, 15))
f = bars["MON"]
print(f.to_string())

print()
print("=== MON far future check: does flat data persist to today? ===")
bars2, missing2 = provider.get_stock_bars(["MON"], "1Day", date(2024, 1, 1), date(2026, 8, 26))
if "MON" in bars2:
    f2 = bars2["MON"]
    print("still has data:", f2.index[0].date(), "to", f2.index[-1].date(), "n=", len(f2))
    print(f2.head(5))
    print(f2.tail(5))
else:
    print("no MON data in 2024-2026 window; missing:", missing2)
