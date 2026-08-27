import yfinance as yf, pandas as pd, datetime as dt
pd.set_option('display.width',200)
for t in ['SPY','AAPL','TSLA','XOM']:
    try:
        tk=yf.Ticker(t)
        exps=tk.options
        print(f"=== {t}: n_expirations={len(exps)}")
        if not exps: continue
        print("  first5",exps[:5],"last3",exps[-3:])
        oc=tk.option_chain(exps[1] if len(exps)>1 else exps[0])
        c=oc.calls
        print("  calls rows",len(c),"cols",list(c.columns))
        sub=c[['strike','lastPrice','bid','ask','volume','openInterest','impliedVolatility','lastTradeDate']].head(4)
        print(sub.to_string())
        print("  IV nonnull frac", c['impliedVolatility'].notna().mean(), "IV>0 frac",(c['impliedVolatility']>0.0001).mean())
        print("  bid/ask both>0 frac",((c['bid']>0)&(c['ask']>0)).mean())
        print("  OI sum",c['openInterest'].sum())
    except Exception as e:
        print(t,"ERR",type(e).__name__,e)
