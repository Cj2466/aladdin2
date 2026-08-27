import yfinance as yf, warnings
warnings.filterwarnings('ignore')
# EXPIRED contracts (expiries already passed as of 2026-08-27)
expired=['SPY260619C00600000','SPY260320C00580000','SPY251219C00600000','AAPL260116C00220000','SPY250117C00500000']
print("--- EXPIRED CONTRACTS ---")
for s in expired:
    try:
        h=yf.Ticker(s).history(period='max')
        print(f"{s} rows={len(h)}"+(f" {h.index[0].date()}..{h.index[-1].date()}" if len(h) else " <- NO DATA"))
    except Exception as e: print(s,"ERR",type(e).__name__)
print("--- LIVE LEAPS: how deep is retained history? ---")
tk=yf.Ticker('SPY')
for exp in ['2027-12-17','2028-01-21','2028-12-15']:
    try:
        c=tk.option_chain(exp).calls
        r=c.nlargest(1,'openInterest').iloc[0]
        h=yf.Ticker(r.contractSymbol).history(period='max')
        print(f"{exp} {r.contractSymbol} OI={r.openInterest} rows={len(h)}"+(f" from {h.index[0].date()}" if len(h) else ""))
    except Exception as e: print(exp,"ERR",type(e).__name__,e)
