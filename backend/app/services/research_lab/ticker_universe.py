# S&P 500 constituent snapshot as of 2026-08-24, sourced from
# datasets/s-and-p-500-companies (github.com/datasets/s-and-p-500-companies,
# mirroring Wikipedia's List of S&P 500 companies) and independently
# empirically confirmed 503/503 resolved via a live yf.download call at
# that date. Dual-share-class tickers (BRK.B, BF.B) are translated to
# yfinance's dash convention (BRK-B, BF-B). NOT a live index-membership
# feed — this is a point-in-time snapshot that will drift as the real
# index's constituents change (additions, removals, ticker changes).
# Individual tickers will delist/rename/merge over time — this is
# expected, not a bug: treat future resolution failures as ordinary
# "missing" entries (ScreeningRunner already does), not something
# requiring a code change. Re-verify periodically with the empirical
# check described in the Phase 3 plan rather than assuming this list
# stays accurate forever.

SCREENING_UNIVERSE: list[str] = [
    # Communication Services (24)
    "APP", "CHTR", "CMCSA", "DIS", "ECHO", "FOX", "FOXA", "GOOG", "GOOGL", "LYV",
    "META", "NFLX", "NWS", "NWSA", "OMC", "PSKY", "RDDT", "T", "TKO", "TMUS",
    "TTD", "TTWO", "VZ", "WBD",
    # Consumer Discretionary (47)
    "ABNB", "AMZN", "APTV", "AZO", "BBY", "BKNG", "CCL", "CMG", "CVNA", "DASH",
    "DECK", "DHI", "DPZ", "DRI", "EBAY", "EXPE", "F", "GM", "GPC", "GRMN",
    "HAS", "HD", "HLT", "LEN", "LOW", "LULU", "LVS", "MAR", "MCD", "MGM",
    "NCLH", "NKE", "NVR", "ORLY", "PHM", "RCL", "RL", "ROST", "SBUX", "TJX",
    "TPR", "TSCO", "TSLA", "ULTA", "WSM", "WYNN", "YUM",
    # Consumer Staples (34)
    "ADM", "BF-B", "BG", "CASY", "CHD", "CL", "CLX", "COST", "DG", "DLTR",
    "EL", "GIS", "HRL", "HSY", "KDP", "KHC", "KMB", "KO", "KR", "KVUE",
    "MDLZ", "MKC", "MNST", "MO", "PEP", "PG", "PM", "SJM", "STZ", "SYY",
    "TAP", "TGT", "TSN", "WMT",
    # Energy (21)
    "APA", "BKR", "COP", "CVX", "DVN", "EOG", "EQT", "EXE", "FANG", "HAL",
    "KMI", "MPC", "OKE", "OXY", "PSX", "SLB", "TPL", "TRGP", "VLO", "WMB",
    "XOM",
    # Financials (76)
    "ACGL", "AFL", "AIG", "AIZ", "AJG", "ALL", "AMP", "AON", "APO", "ARES",
    "AXP", "BAC", "BEN", "BLK", "BNY", "BRK-B", "BRO", "BX", "C", "CB",
    "CBOE", "CFG", "CINF", "CME", "COF", "COIN", "CPAY", "EG", "ERIE", "FDS",
    "FIS", "FISV", "FITB", "GL", "GPN", "GS", "HBAN", "HIG", "HOOD", "IBKR",
    "ICE", "IVZ", "JKHY", "JPM", "KEY", "KKR", "L", "MA", "MCO", "MET",
    "MRSH", "MS", "MSCI", "MTB", "NDAQ", "NTRS", "PFG", "PGR", "PNC", "PRU",
    "PYPL", "RF", "RJF", "SCHW", "SPGI", "STT", "SYF", "TFC", "TROW", "TRV",
    "USB", "V", "WFC", "WRB", "WTW", "XYZ",
    # Health Care (59)
    "A", "ABBV", "ABT", "ALGN", "AMGN", "BAX", "BDX", "BIIB", "BMY", "BSX",
    "CAH", "CI", "CNC", "COO", "COR", "CRL", "CVS", "DGX", "DHR", "DVA",
    "DXCM", "ELV", "EW", "GEHC", "GILD", "HCA", "HSIC", "HUM", "IDXX", "INCY",
    "IQV", "ISRG", "JNJ", "LH", "LLY", "MCK", "MDT", "MRK", "MRNA", "MTD",
    "PFE", "PODD", "REGN", "RMD", "RVTY", "SOLV", "STE", "SYK", "TECH", "TMO",
    "UHS", "UNH", "VEEV", "VRTX", "VTRS", "WAT", "WST", "ZBH", "ZTS",
    # Industrials (83)
    "ADP", "ALLE", "AME", "AOS", "AXON", "BA", "BLDR", "BR", "CARR", "CAT",
    "CHRW", "CMI", "CPRT", "CSX", "CTAS", "DAL", "DD", "DE", "DOV", "EFX",
    "EME", "EMR", "ETN", "EXPD", "FAST", "FDX", "FDXF", "FERG", "FIX", "FTV",
    "GD", "GE", "GEV", "GNRC", "GWW", "HII", "HON", "HONA", "HUBB", "HWM",
    "IEX", "IR", "ITW", "J", "JBHT", "JCI", "LDOS", "LHX", "LII", "LMT",
    "LUV", "MAS", "MMM", "NDSN", "NOC", "NSC", "ODFL", "OTIS", "PAYX", "PCAR",
    "PH", "PNR", "PWR", "ROK", "ROL", "RSG", "RTX", "SNA", "SWK", "TDG",
    "TT", "TXT", "UAL", "UBER", "UNP", "UPS", "URI", "VLTO", "VRSK", "VRT",
    "WAB", "WM", "XYL",
    # Information Technology (73)
    "AAPL", "ACN", "ADBE", "ADI", "ADSK", "AKAM", "AMAT", "AMD", "ANET", "APH",
    "AVGO", "CDNS", "CDW", "CIEN", "COHR", "CRM", "CRWD", "CSCO", "CTSH", "DDOG",
    "DELL", "FFIV", "FICO", "FLEX", "FSLR", "FTNT", "GDDY", "GEN", "GLW", "HPE",
    "HPQ", "IBM", "INTC", "INTU", "IT", "JBL", "KEYS", "KLAC", "LITE", "LRCX",
    "MCHP", "MPWR", "MRVL", "MSFT", "MSI", "MU", "NOW", "NTAP", "NVDA", "NXPI",
    "ON", "ORCL", "PANW", "PLTR", "PTC", "Q", "QCOM", "ROP", "SMCI", "SNDK",
    "SNPS", "STX", "SWKS", "TDY", "TEL", "TER", "TRMB", "TXN", "TYL", "VRSN",
    "WDAY", "WDC", "ZBRA",
    # Materials (25)
    "ALB", "AMCR", "APD", "AVY", "BALL", "CF", "CRH", "CTVA", "DOW", "ECL",
    "FCX", "IFF", "IP", "LIN", "LYB", "MLM", "MOS", "NEM", "NUE", "PKG",
    "PPG", "SHW", "STLD", "SW", "VMC",
    # Real Estate (30)
    "AMT", "ARE", "BXP", "CBRE", "CCI", "CPT", "CSGP", "DLR", "DOC", "EQIX",
    "ESS", "EXR", "FRT", "HST", "INVH", "IRM", "KIM", "MAA", "O", "PLD",
    "PSA", "REG", "SBAC", "SPG", "UDR", "VICI", "VMRK", "VTR", "WELL", "WY",
    # Utilities (31)
    "AEE", "AEP", "AES", "ATO", "AWK", "CEG", "CMS", "CNP", "D", "DTE",
    "DUK", "ED", "EIX", "ES", "ETR", "EVRG", "EXC", "FE", "LNT", "NEE",
    "NI", "NRG", "PCG", "PEG", "PNW", "PPL", "SO", "SRE", "VST", "WEC",
    "XEL",
]
