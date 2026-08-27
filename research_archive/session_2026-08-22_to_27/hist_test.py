import yfinance as yf, pandas as pd, warnings
warnings.filterwarnings('ignore')
tk=yf.Ticker('SPY'); exps=tk.options
# pick a ~1yr out expiry, liquid ATM contract
import datetime as dt
exp=[e for e in exps if e>='2026-12-01'][0]
oc=tk.option_chain(exp); c=oc.calls
spot=tk.history(period='5d')['Close'].iloc[-1]
c['d']=(c.strike-spot).abs(); row=c.nsmallest(1,'d').iloc[0]
sym=row.contractSymbol
print("spot",round(spot,2),"exp",exp,"ATM contract",sym,"OI",row.openInterest)
h=yf.Ticker(sym).history(period='6mo')
print("contract history rows:",len(h))
if len(h): print(h[['Open','High','Low','Close','Volume']].head(3).to_string()); print("...");print(h.tail(2).to_string())
# does option_chain accept a historical asof?
try:
    import inspect; print("option_chain sig:",inspect.signature(tk.option_chain))
except Exception as e: print(e)
