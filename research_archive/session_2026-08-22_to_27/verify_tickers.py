import json, sys, warnings
warnings.filterwarnings("ignore")
import yfinance as yf
import pandas as pd

TICKERS = ["STI","FOXA","FOX","BNY","IR","PARA","COL","DFS","CMA","SRCL","AIV","CNX"]
START, END = "2013-12-01", "2026-08-27"
out = {}

# price: batched chart endpoint, exactly like get_price_history
px = yf.download(TICKERS, start=START, end=END, auto_adjust=False, progress=False, group_by="column", threads=True)
close = px["Close"] if isinstance(px.columns, pd.MultiIndex) else px[["Close"]]

for t in TICKERS:
    rec = {}
    try:
        s = close[t].dropna() if t in close.columns else pd.Series(dtype=float)
    except Exception:
        s = pd.Series(dtype=float)
    rec["n_price_rows"] = int(len(s))
    rec["price_first"] = str(s.index[0].date()) if len(s) else None
    rec["price_last"] = str(s.index[-1].date()) if len(s) else None
    # shares: per-ticker fundamentals endpoint
    try:
        sh = yf.Ticker(t).get_shares_full(start=START, end=END)
        if sh is not None and len(sh):
            sh = sh[~sh.index.duplicated(keep="last")].sort_index()
            rec["n_share_rows"] = int(len(sh))
            rec["shares_first_date"] = str(pd.Timestamp(sh.index[0]).date())
            rec["shares_first_val"] = float(sh.iloc[0])
            rec["shares_last_date"] = str(pd.Timestamp(sh.index[-1]).date())
            rec["shares_last_val"] = float(sh.iloc[-1])
            rec["shares_min"] = float(sh.min()); rec["shares_max"] = float(sh.max())
            # biggest step
            r = sh.astype(float)
            ratio = (r / r.shift(1)).dropna()
            if len(ratio):
                i = ratio.abs().idxmax()
                rec["max_step_date"] = str(pd.Timestamp(i).date())
                rec["max_step_ratio"] = float(ratio.loc[i])
        else:
            rec["n_share_rows"] = 0
    except Exception as e:
        rec["shares_error"] = repr(e)[:200]
    try:
        info = yf.Ticker(t).info
        rec["info_name"] = info.get("longName") or info.get("shortName")
        rec["info_shares"] = info.get("sharesOutstanding")
    except Exception as e:
        rec["info_error"] = repr(e)[:150]
    out[t] = rec
    print(t, json.dumps(rec), flush=True)

json.dump(out, open("/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/ticker_facts.json","w"), indent=1)
