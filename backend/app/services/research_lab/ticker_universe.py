# A point-in-time curated snapshot as of 2026-08-24, empirically confirmed
# 100% resolved via a live yf.download call at that date — NOT a live
# index-membership feed, and deliberately not called "S&P 500" since it
# isn't one (it's a hand-picked 108-ticker cross-section for screening
# purposes). Individual tickers will delist/rename/merge over time — this
# is expected, not a bug: treat future resolution failures as ordinary
# "missing" entries (ScreeningRunner already does), not something requiring
# a code change. Re-verify periodically with the empirical check described
# in the Phase 1.75 plan rather than assuming this list stays accurate
# forever.

SCREENING_UNIVERSE: list[str] = [
    # Tech (22)
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AVGO", "CSCO", "ACN",
    "ADBE", "CRM", "NFLX", "INTC", "TXN", "ORCL", "QCOM", "IBM", "AMD", "NOW",
    "INTU", "MU",
    # Healthcare (16)
    "JNJ", "MRK", "ABBV", "PFE", "TMO", "ABT", "DHR", "UNH", "GILD", "ISRG",
    "SYK", "MDT", "VRTX", "REGN", "ZTS", "BSX",
    # Financials (16)
    "JPM", "V", "MA", "BAC", "WFC", "GS", "SCHW", "C", "BLK", "SPGI",
    "AXP", "USB", "PNC", "TFC", "MS", "COF",
    # Consumer (22)
    "PG", "HD", "MCD", "WMT", "COST", "NKE", "SBUX", "DIS", "PEP", "KO",
    "CL", "KMB", "CLX", "GIS", "HSY", "MDLZ", "TGT", "DG", "ROST", "LULU",
    "YUM", "CMG",
    # Industrials (16)
    "HON", "UPS", "CAT", "MMM", "RTX", "LMT", "GE", "BA", "DE", "EMR",
    "ETN", "ITW", "ROK", "CSX", "UNP", "FDX",
    # Energy (8)
    "XOM", "CVX", "EOG", "SLB", "OXY", "COP", "MPC", "PSX",
    # Utilities/REITs (8)
    "SO", "DUK", "NEE", "EQIX", "O", "PSA", "AVB", "WELL",
]
