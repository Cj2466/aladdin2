"""Measure the REAL usable index-removal sample from live yfinance data."""
import sys, warnings, pickle
sys.path.insert(0, '/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/wf_16c9f152-b0d-1/backend')
warnings.filterwarnings('ignore')
import yfinance as yf, pandas as pd, numpy as np
from datetime import date
from app.services.research_lab import sp500_membership_history as m

ev = m.vendored_events()
removals = [(d, t) for d, a, r in ev for t in r]
tickers = sorted({t for _, t in removals})
print(f'removal events: {len(removals)}, distinct removed tickers: {len(tickers)}')

frames = []
CH = 40
for i in range(0, len(tickers), CH):
    chunk = tickers[i:i+CH]
    raw = yf.download(chunk, start='2014-01-01', end='2026-08-27',
                      auto_adjust=True, progress=False, threads=True)
    if raw is None or raw.empty:
        print(f'  chunk {i}: EMPTY'); continue
    try:
        c = raw['Close']
    except Exception:
        print(f'  chunk {i}: no Close'); continue
    c = c.dropna(axis=1, how='all')
    frames.append(c)
    print(f'  chunk {i//CH}: requested {len(chunk)}, resolved {c.shape[1]}')

close = pd.concat(frames, axis=1).sort_index()
close = close.loc[:, ~close.columns.duplicated()]
print(f'\nRESOLVED {close.shape[1]} / {len(tickers)} removed tickers  ({close.shape[1]/len(tickers):.1%})')
with open('/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/removed_close.pkl','wb') as f:
    pickle.dump(close, f)
print('saved.')
