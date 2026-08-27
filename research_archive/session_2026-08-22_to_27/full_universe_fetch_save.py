import sys, time
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
from datetime import date, timedelta
import yfinance as yf
import pandas as pd
from app.services.research_lab.ticker_universe import SCREENING_UNIVERSE

end = date.today()
start = end - timedelta(days=760)
raw = yf.download(SCREENING_UNIVERSE, start=start, end=end, auto_adjust=True, progress=False)
close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
close = close.dropna(axis=1, how="all")
close.to_pickle("/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/prices_full503_760d.pkl")
print("saved", close.shape)
