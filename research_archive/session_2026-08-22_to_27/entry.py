from datetime import date, timedelta
from app.services.research_lab.cross_sectional_index_removal import *
from app.services.research_lab.cross_sectional_index_removal import (
    list_index_removal_events, build_removal_event_book, MEMBERSHIP_DATA_START,
    REMOVAL_PRICE_HISTORY_PADDING_CALENDAR_DAYS)
from app.services.market_data.yfinance_provider import YFinanceProvider
ev,_ = list_index_removal_events()
ev = [e for e in ev if MEMBERSHIP_DATA_START <= e.effective_date <= date(2026,6,30)]
p = YFinanceProvider()
fr,_ = p.get_daily_ohlcv(sorted({e.ticker for e in ev}),
    MEMBERSHIP_DATA_START-timedelta(days=REMOVAL_PRICE_HISTORY_PADDING_CALENDAR_DAYS), date(2026,6,30))
close = fr["close"]
entered,_ = build_removal_event_book(close, ev)
bad = [(e.ticker,e.effective_date,e.entry_date) for e in entered if e.entry_date <= e.effective_date]
print("entered",len(entered),"ON-OR-BEFORE-EFFECTIVE:",len(bad))
gaps=[(e.entry_date-e.effective_date).days for e in entered]
print("gap days min/max", min(gaps), max(gaps))
# verify entry_position row is strictly after effective in the index
idx=close.index
n_off=[e.entry_position - int(idx.searchsorted(__import__('pandas').Timestamp(e.effective_date),side='right')) for e in entered]
print("offset beyond last<=eff row (should all be 0):", set(n_off))
