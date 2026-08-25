from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date

# Point-in-time S&P 500 membership: which tickers were ACTUALLY index
# members on a given historical date, as opposed to ticker_universe.py's
# SCREENING_UNIVERSE, which is a single snapshot of TODAY. Applying today's
# snapshot across a multi-year lookback window is survivorship bias —
# companies that left the index during that window (acquired, failed,
# downgraded out) are silently never considered, and companies that joined
# it partway through are treated as though they had always been eligible.
#
# SOURCE: github.com/fja05680/sp500, "S&P 500 Historical Components &
# Changes (Updated).csv" — full constituent snapshots at every change date
# from 1996-01-02 to 2026-06-30, maintained from Wikipedia plus manual
# per-event research. That repo's own README is explicit that Wikipedia's
# "Selected changes" table is not complete enough to reconstruct history
# from on its own; independently confirmed 2026-08-25 that Wikipedia's
# List of S&P 500 companies article no longer carries a changes table at
# all, only the current constituents plus a per-company "Date added"
# column — so Wikipedia alone cannot serve this purpose today.
#
# Vendored as a base snapshot + chronological add/remove events rather than
# the raw 5.3 MB CSV: 368 of the 604 post-2015 snapshot rows are identical
# repeats of the previous row's membership, i.e. the CSV is ~99% redundant
# storage, and a checked-in literal has no network dependency at import
# time (same reasoning as SCREENING_UNIVERSE being a literal, not a fetch).
# Reconstruction was verified to reproduce the source file's own final
# 2026-06-30 row exactly, 503/503 tickers.
#
# EMPIRICALLY VERIFIED 2026-08-25, three independent ways:
#  (1) Thirteen index events whose real dates are independently well known
#      all match exactly: the FB -> META ticker change on 2022-06-09;
#      SIVB and SBNY both removed 2023-03-15 (both banks failed over the
#      preceding weekend); FRC removed 2023-05-04 (seized 2023-05-01);
#      XLNX removed 2022-02-15 (AMD closed the deal 02-14); CERN removed
#      2022-06-08 (Oracle closed the deal that day); ATVI removed
#      2023-10-18 (Microsoft closed 10-13); TWTR removed 2022-11-01;
#      TSLA added 2020-12-21; KVUE added 2023-08-25; ABNB added
#      2023-09-18; VLTO added 2023-10-02; PLTR added 2024-09-23.
#  (2) Reconstructing 2026-06-30 and diffing against ticker_universe.py's
#      independently-sourced 2026-08-24 snapshot agrees on 500/503
#      tickers, and the 6-ticker difference is exactly the real index
#      drift over those eight weeks (+FERG +RDDT +VMRK / -AVB -EA -EQR).
#  (3) Every current member's implied addition date was cross-checked
#      against Wikipedia's separately-maintained per-company "Date added"
#      column: 461/498 agree exactly (counting a pre-window member
#      censored at MEMBERSHIP_DATA_START as agreement). Of the 37 that
#      differ, 29 are ticker RENAMES (this data is ticker-keyed,
#      Wikipedia is company-keyed — corrected below by
#      _EARLIEST_MEMBERSHIP_OVERRIDES), 6 are 1-4 calendar-day
#      announcement-vs-effective differences, and 1 (ECHO) is genuine
#      ~3-month source lag. No case was found in which this data claims a
#      membership that never happened.
#
# KNOWN LIMITS — read these before trusting anything built on this module:
#  * Ticker-keyed, not company-keyed. A ticker change reads as a removal
#    plus an addition on the same date. _EARLIEST_MEMBERSHIP_OVERRIDES
#    repairs the *earliest* membership date for current members, which is
#    what the inclusion-bias disclosure below actually needs; it does not
#    stitch the two tickers into one continuous interval. One current
#    member is affected in its interior: Fiserv renamed FISV -> FI in
#    2023 and back to FISV in 2025, so was_member("FISV", d) is False for
#    d in [2023-06-07, 2025-11-11) even though the company never left the
#    index. Renames among FORMER members are not corrected at all.
#  * The VENDORED literals below stop at MEMBERSHIP_DATA_AS_OF and never
#    move — a checked-in file, not a live feed. What does move is the
#    optional EXTENSION overlay applied at runtime by
#    sp500_membership_refresh.py (re-fetching the same upstream file plus
#    two independent live constituent sources); read
#    membership_coverage_end() rather than MEMBERSHIP_DATA_AS_OF anywhere
#    the current end of coverage matters. With no extension applied — the
#    default, and the state in every test that does not explicitly apply
#    one — the two are equal and this module behaves exactly as vendored.
#  * This module answers WHO WAS A MEMBER. It does not, and with this
#    project's free data cannot, make a survivorship-free backtest
#    possible. Empirically verified 2026-08-25: of the 105 tickers that
#    were S&P 500 members at some point in the trailing 5 years but are
#    not members today, yfinance returns NO price history for 50 (48%) —
#    and those 50 are precisely the acquired/failed names (ATVI, TWTR,
#    SIVB, SBNY, FRC, XLNX, CERN, PXD, ANSS, JNPR, ABMD, CTXS, ...) whose
#    absence inflates a backtest most. Worse, 3 of the 55 that DO resolve
#    are RECYCLED tickers now belonging to a different company (yfinance
#    history for FB starts 2025-06-26, for SBNY 2024-08-15, for INFO
#    2024-10-10 — all long after those index members ceased to exist),
#    which is silently wrong data rather than a visible failure. Any
#    caller that fetches prices for a former member MUST intersect the
#    result with that ticker's membership interval — see was_member().
#    Actually closing the survivorship gap needs a delisted-securities
#    price vendor (Norgate, CRSP, Sharadar); this project has none.

# 2015-01-07 is the first snapshot row at or after 2015-01-01, not an
# arbitrary cut. The source covers 1996 onward, but its own README says
# everything before 2019 came from a third party's file that the
# maintainer only cleans, not verifies, and a spot check found Lehman
# Brothers carried as its post-bankruptcy OTC ticker LEHMQ rather than
# LEH — i.e. the deep history has known ticker-hygiene artifacts. Eleven
# years comfortably covers every lookback this system runs (the longest
# default is DEFAULT_LOOKBACK_YEARS = 5) and keeps the vendored data
# inside the era actually spot-verified above.
MEMBERSHIP_DATA_START = date(2015, 1, 7)
MEMBERSHIP_DATA_AS_OF = date(2026, 6, 30)

# The 499 constituents on MEMBERSHIP_DATA_START. Dual-share-class tickers
# are translated to yfinance's dash convention (BRK-B, BF-B) here, exactly
# as ticker_universe.py already does, so both modules speak one symbology.
_BASE_UNIVERSE: tuple[str, ...] = (
    "A", "AABA", "AAPL", "ABBV", "ABC", "ABT", "ACN", "ADBE", "ADI", "ADM", "ADP", "ADS", "ADSK",
    "ADT", "AEE", "AEP", "AES", "AET", "AFL", "AGN", "AIG", "AIV", "AIZ", "AKAM", "ALL", "ALLE",
    "ALTR", "ALXN", "AMAT", "AME", "AMG", "AMGN", "AMP", "AMT", "AMZN", "AN", "ANDV", "ANTM", "AON",
    "APA", "APC", "APD", "APH", "APTV", "ARG", "ARNC", "ATI", "AVB", "AVGO", "AVP", "AVY", "AXP",
    "AZO", "BA", "BAC", "BAX", "BBBY", "BBT", "BBY", "BCR", "BDX", "BEN", "BF-B", "BHGE", "BIIB",
    "BK", "BKNG", "BLK", "BLL", "BMY", "BRCM", "BRK-B", "BSX", "BWA", "BXP", "C", "CA", "CAG",
    "CAH", "CAM", "CAT", "CB", "CBRE", "CBS", "CCE", "CCI", "CCL", "CELG", "CERN", "CF", "CFN",
    "CHK", "CHRW", "CI", "CINF", "CL", "CLX", "CMA", "CMCSA", "CME", "CMG", "CMI", "CMS", "CNP",
    "CNX", "COF", "COG", "COL", "COP", "COST", "COV", "CPB", "CRM", "CSCO", "CSX", "CTAS", "CTL",
    "CTSH", "CTXS", "CVC", "CVS", "CVX", "D", "DAL", "DD", "DE", "DFS", "DG", "DGX", "DHI", "DHR",
    "DIS", "DISCA", "DISCK", "DLTR", "DNB", "DNR", "DO", "DOV", "DOW", "DRI", "DTE", "DTV", "DUK",
    "DVA", "DVN", "DXC", "EA", "EBAY", "ECL", "ED", "EFX", "EIX", "EL", "EMC", "EMN", "EMR", "EOG",
    "EQR", "EQT", "ES", "ESRX", "ESS", "ESV", "ETFC", "ETN", "ETR", "EW", "EXC", "EXPD", "EXPE",
    "F", "FAST", "FB", "FCX", "FDO", "FDX", "FE", "FFIV", "FIS", "FISV", "FITB", "FLIR", "FLR",
    "FLS", "FMC", "FOSL", "FOXA", "FSLR", "FTI", "FTR", "GAS", "GD", "GE", "GGP", "GILD", "GIS",
    "GLW", "GM", "GMCR", "GME", "GNW", "GOOG", "GOOGL", "GPC", "GPS", "GRMN", "GS", "GT", "GWW",
    "HAL", "HAR", "HAS", "HBAN", "HCBK", "HCP", "HD", "HES", "HIG", "HOG", "HON", "HOT", "HP",
    "HPQ", "HRB", "HRL", "HRS", "HSP", "HST", "HSY", "HUM", "IBM", "ICE", "IFF", "INTC", "INTU",
    "IP", "IPG", "IR", "IRM", "ISRG", "ITW", "IVZ", "JCI", "JEC", "JEF", "JNJ", "JNPR", "JOY",
    "JPM", "JWN", "K", "KDP", "KEY", "KIM", "KLAC", "KMB", "KMI", "KMX", "KO", "KORS", "KR", "KRFT",
    "KSS", "KSU", "L", "LB", "LEG", "LEN", "LH", "LLL", "LLTC", "LLY", "LM", "LMT", "LNC", "LO",
    "LOW", "LRCX", "LUV", "LVLT", "LYB", "M", "MA", "MAC", "MAR", "MAS", "MAT", "MCD", "MCHP",
    "MCK", "MCO", "MDLZ", "MDT", "MET", "MHK", "MJN", "MKC", "MLM", "MMC", "MMM", "MNK", "MNST",
    "MO", "MON", "MOS", "MPC", "MRK", "MRO", "MS", "MSFT", "MSI", "MTB", "MU", "MUR", "MWV", "MYL",
    "NAVI", "NBL", "NBR", "NDAQ", "NE", "NEE", "NEM", "NFLX", "NFX", "NI", "NKE", "NLSN", "NOC",
    "NOV", "NRG", "NSC", "NTAP", "NTRS", "NUE", "NVDA", "NWL", "NWSA", "OI", "OKE", "OMC", "ORCL",
    "ORLY", "OXY", "PAYX", "PBCT", "PBI", "PCAR", "PCG", "PCL", "PCP", "PDCO", "PEG", "PEP", "PETM",
    "PFE", "PFG", "PG", "PGR", "PH", "PHM", "PKI", "PLD", "PLL", "PM", "PNC", "PNR", "PNW", "POM",
    "PPG", "PPL", "PRGO", "PRU", "PSA", "PSX", "PVH", "PWR", "PX", "PXD", "QCOM", "QEP", "R", "RAI",
    "RCL", "REGN", "RF", "RHI", "RHT", "RIG", "RL", "ROK", "ROP", "ROST", "RRC", "RSG", "RTN",
    "SBUX", "SCG", "SCHW", "SE", "SEE", "SHW", "SIAL", "SJM", "SLB", "SNA", "SNDK", "SNI", "SO",
    "SPG", "SPGI", "SPLS", "SRCL", "SRE", "STI", "STJ", "STT", "STX", "STZ", "SWK", "SWN", "SWY",
    "SYK", "SYMC", "SYY", "T", "TAP", "TDC", "TE", "TEG", "TEL", "TGNA", "TGT", "THC", "TIF", "TJX",
    "TMK", "TMO", "TPR", "TRIP", "TROW", "TRV", "TSCO", "TSN", "TSS", "TWC", "TWX", "TXN", "TXT",
    "UAA", "UHS", "UNH", "UNM", "UNP", "UPS", "URBN", "URI", "USB", "UTX", "V", "VAR", "VFC",
    "VIAB", "VLO", "VMC", "VNO", "VRSN", "VRTX", "VTR", "VZ", "WAT", "WBA", "WDC", "WEC", "WELL",
    "WFC", "WFM", "WHR", "WIN", "WM", "WMB", "WMT", "WU", "WY", "WYND", "WYNN", "XEC", "XEL", "XL",
    "XLNX", "XOM", "XRAY", "XRX", "XYL", "YUM", "ZBH", "ZION", "ZTS"
)

# (effective date, tickers added that date, tickers removed that date), in
# chronological order. Derived by diffing consecutive snapshot rows in the
# source CSV, which is why a rename shows up as a same-date remove+add
# pair (FB out / META in on 2022-06-09) — see the KNOWN LIMITS above.
_MEMBERSHIP_EVENTS: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("2015-01-27", ("ENDP", "HCA"), ("COV", "SWY")),
    ("2015-03-12", ("SWKS",), ("PETM",)),
    ("2015-03-17", (), ("CFN",)),
    ("2015-03-18", ("HSIC",), ()),
    ("2015-03-23", ("AAL", "EQIX", "HBI", "SLG"), ("AVP", "DNR", "NBR")),
    ("2015-04-07", ("O",), ("WIN",)),
    ("2015-06-12", ("QRVO",), ("LO",)),
    ("2015-06-30", (), ("TEG",)),
    ("2015-07-01", ("BXLT", "JBHT"), ("QEP",)),
    ("2015-07-02", ("CPGX", "WRK"), ("ATI", "MWV")),
    ("2015-07-06", ("KHC",), ("KRFT",)),
    ("2015-07-07", (), ("FDO",)),
    ("2015-07-09", ("AAP",), ()),
    ("2015-07-20", ("PYPL",), ("NE",)),
    ("2015-07-27", (), ("DTV",)),
    ("2015-07-29", ("SIG",), ()),
    ("2015-08-31", ("ATVI",), ("PLL",)),
    ("2015-09-03", ("UAL",), ("HSP",)),
    ("2015-09-21", ("CMCSK", "FOX", "NWS"), ()),
    ("2015-10-08", ("VRSK",), ("JOY",)),
    ("2015-11-02", ("HPE",), ("HCBK",)),
    ("2015-11-10", ("FCPT",), ()),
    ("2015-11-17", (), ("FCPT",)),
    ("2015-11-18", ("SYF",), ("GNW", "SIAL")),
    ("2015-11-19", ("ILMN",), ()),
    ("2015-11-30", ("CSRA",), ()),
    ("2015-12-01", (), ("DXC",)),
    ("2015-12-14", (), ("CMCSK",)),
    ("2015-12-28", (), ("ALTR",)),
    ("2015-12-29", ("CHD",), ()),
    ("2016-01-04", ("CCEP", "CPRI"), ()),
    ("2016-01-05", ("WLTW",), ("FOSL",)),
    ("2016-01-19", ("EXR",), ()),
    ("2016-02-01", ("CFG", "FRT"), ("BRCM", "PCP")),
    ("2016-02-22", ("CXO",), ("PCL",)),
    ("2016-03-03", (), ("GMCR",)),
    ("2016-03-04", ("AWK",), ("CNX",)),
    ("2016-03-07", ("UDR",), ()),
    ("2016-03-24", (), ("POM",)),
    ("2016-03-30", ("CNC", "HOLX"), ("ESV",)),
    ("2016-04-04", ("FL",), ("CAM",)),
    ("2016-04-08", ("UA",), ()),
    ("2016-04-18", ("ULTA",), ("THC",)),
    ("2016-04-25", ("GPN",), ("GME",)),
    ("2016-05-02", (), ("ADT",)),
    ("2016-05-03", ("AYI",), ()),
    ("2016-05-12", (), ("SNDK",)),
    ("2016-05-13", ("ALK",), ()),
    ("2016-05-18", ("DLR",), ("TWC",)),
    ("2016-05-23", ("LKQ",), ("ARG",)),
    ("2016-05-31", ("AJG",), ("CCE", "CCEP")),
    ("2016-06-03", ("TDG",), ("BXLT",)),
    ("2016-06-21", (), ("CVC",)),
    ("2016-06-24", ("FBHS",), ()),
    ("2016-07-01", ("ALB", "LNT"), ("CPGX", "GAS", "TE")),
    ("2016-07-05", ("FTV",), ()),
    ("2016-09-06", ("MTD",), ()),
    ("2016-09-07", (), ("EMC",)),
    ("2016-09-08", ("CHTR",), ()),
    ("2016-09-23", ("COO",), ("HOT",)),
    ("2016-10-03", ("COTY",), ("DO",)),
    ("2016-12-02", ("EVHC", "MAA"), ("LM", "OI")),
    ("2017-01-05", ("IDXX",), ("STJ",)),
    ("2017-02-27", (), ("SE",)),
    ("2017-02-28", ("INCY",), ()),
    ("2017-03-01", ("CBOE",), ("PBI",)),
    ("2017-03-02", ("REG",), ("ENDP",)),
    ("2017-03-13", ("DISH",), ("HAR", "LLTC")),
    ("2017-03-16", ("SNPS",), ()),
    ("2017-03-20", ("AMD", "ARE", "RJF"), ("FSLR", "FTR", "URBN")),
    ("2017-04-04", ("DXC",), ("SWN",)),
    ("2017-04-05", ("IT",), ("DNB",)),
    ("2017-06-02", ("INFO",), ("TGNA",)),
    ("2017-06-15", (), ("MJN",)),
    ("2017-06-19", ("ALGN", "ANSS", "HLT", "RE"), ("AABA", "R", "TDC")),
    ("2017-07-25", (), ("RAI",)),
    ("2017-07-26", ("AOS", "DRE", "MGM", "PKG", "RMD"), ("BBBY", "MNK", "MUR", "RIG")),
    ("2017-08-07", ("BHF",), ()),
    ("2017-08-08", (), ("AN",)),
    ("2017-08-28", (), ("WFM",)),
    ("2017-08-29", ("IQV",), ()),
    ("2017-09-01", ("DWDP", "SBAC"), ("DD", "DOW")),
    ("2017-09-13", (), ("SPLS",)),
    ("2017-09-18", ("CDNS",), ()),
    ("2017-10-13", ("NCLH",), ("LVLT",)),
    ("2017-12-29", (), ("BCR",)),
    ("2018-01-03", ("HII",), ()),
    ("2018-03-07", ("IPGP",), ("SNI",)),
    ("2018-03-19", ("NKTR", "SIVB", "TTWO"), ("CHK", "PDCO", "SIG")),
    ("2018-04-04", ("MSCI",), ("CSRA",)),
    ("2018-05-31", ("ABMD",), ("WYND",)),
    ("2018-06-05", ("EVRG",), ("NAVI",)),
    ("2018-06-07", ("TWTR",), ("MON",)),
    ("2018-06-15", (), ("TWX",)),
    ("2018-06-18", ("BR", "HFC"), ("AYI", "RRC")),
    ("2018-06-20", ("FLT",), ()),
    ("2018-07-02", ("CPRT",), ("KDP",)),
    ("2018-08-28", ("ANET",), ("GGP",)),
    ("2018-09-12", (), ("XL",)),
    ("2018-09-17", ("WCG",), ()),
    ("2018-09-19", (), ("KORS",)),
    ("2018-10-01", ("ROL",), ("ANDV",)),
    ("2018-10-11", ("FTNT",), ("EVHC",)),
    ("2018-10-31", (), ("PX",)),
    ("2018-11-06", ("KEYS", "LIN"), ("CA",)),
    ("2018-11-13", ("JKHY",), ("EQT",)),
    ("2018-11-27", (), ("COL",)),
    ("2018-11-29", (), ("AET",)),
    ("2018-12-03", ("FANG", "LW", "MXIM"), ("SRCL",)),
    ("2018-12-21", (), ("ESRX",)),
    ("2018-12-24", ("CE",), ()),
    ("2019-01-02", ("FRC",), ("SCG",)),
    ("2019-01-18", ("TFX",), ("PCG",)),
    ("2019-02-15", ("ATO",), ("NFX",)),
    ("2019-02-27", ("WAB",), ("GT",)),
    ("2019-04-02", ("DOW",), ("BHF",)),
    ("2019-06-01", ("LHX",), ("HRS",)),
    ("2019-06-03", ("CTVA", "DD"), ("DWDP", "FLR")),
    ("2019-06-07", ("AMCR",), ("MAT",)),
    ("2019-07-01", ("MKTX",), ("LLL",)),
    ("2019-07-15", ("TMUS",), ("RHT",)),
    ("2019-08-08", ("GL",), ("TMK",)),
    ("2019-08-09", ("IEX", "LDOS"), ("APC", "FL")),
    ("2019-09-23", ("CDW",), ("TSS",)),
    ("2019-09-26", ("NVR",), ("JEF",)),
    ("2019-10-03", ("LVS",), ("NKTR",)),
    ("2019-10-18", ("BKR",), ("BHGE",)),
    ("2019-11-05", ("NLOK", "PEAK"), ("HCP", "SYMC")),
    ("2019-11-21", ("NOW",), ("CELG",)),
    ("2019-12-05", ("VIAC", "WRB"), ("CBS", "VIAB")),
    ("2019-12-09", ("ODFL", "TFC"), ("BBT", "STI")),
    ("2019-12-10", ("J",), ("JEC",)),
    ("2019-12-23", ("LYV", "STE", "ZBRA"), ("AMG", "MAC", "TRIP")),
    ("2020-01-28", ("PAYC",), ("WCG",)),
    ("2020-03-03", ("TT",), ("XEC",)),
    ("2020-04-03", ("CARR", "OTIS", "RTX"), ("UTX",)),
    ("2020-04-06", ("HWM",), ("ARNC", "M", "RTN")),
    ("2020-05-12", ("DPZ", "DXCM"), ("AGN", "CPRI")),
    ("2020-05-22", ("WST",), ("HP",)),
    ("2020-06-22", ("BIO", "TDY", "TYL"), ("ADS", "HOG", "JWN")),
    ("2020-09-18", ("LUMN",), ("CTL",)),
    ("2020-09-21", ("CTLT", "ETSY", "TER"), ("COTY", "HRB", "KSS")),
    ("2020-10-07", ("POOL",), ("ETFC",)),
    ("2020-10-12", ("VNT",), ("NBL",)),
    ("2020-11-17", ("VTRS",), ("MYL",)),
    ("2020-12-21", ("TSLA",), ("AIV",)),
    ("2021-01-07", ("ENPH",), ("TIF",)),
    ("2021-01-21", ("TRMB",), ("CXO",)),
    ("2021-02-12", ("MPWR",), ("FTI",)),
    ("2021-03-22", ("CZR", "GNRC", "NXPI", "PENN"), ("FLS", "SLG", "VNT", "XRX")),
    ("2021-04-20", ("PTC",), ("VAR",)),
    ("2021-05-14", ("CRL",), ("FLIR",)),
    ("2021-06-04", ("OGN",), ("HFC",)),
    ("2021-07-21", ("MRNA",), ("ALXN",)),
    ("2021-08-03", ("BBWI",), ("LB",)),
    ("2021-08-30", ("TECH",), ("MXIM",)),
    ("2021-09-20", ("BRO", "CDAY", "MTCH"), ("NOV", "PRGO", "UNM")),
    ("2021-10-04", ("CTRA",), ("COG",)),
    ("2021-12-14", ("EPAM",), ("KSU",)),
    ("2021-12-20", ("FDS", "SBNY", "SEDG"), ("HBI", "LEG", "WU")),
    ("2022-01-10", ("WTW",), ("WLTW",)),
    ("2022-02-02", ("CEG",), ("GPS",)),
    ("2022-02-15", ("NDSN",), ("XLNX",)),
    ("2022-02-17", ("PARA",), ("VIAC",)),
    ("2022-03-02", ("MOH",), ("INFO",)),
    ("2022-04-04", ("CPT",), ("PBCT",)),
    ("2022-04-11", ("WBD",), ("DISCA", "DISCK")),
    ("2022-05-10", ("BALL",), ("BLL",)),
    ("2022-06-08", ("VICI",), ("CERN",)),
    ("2022-06-09", ("META",), ("FB",)),
    ("2022-06-21", ("KDP", "ON"), ("IPGP", "UA", "UAA")),
    ("2022-06-28", ("ELV",), ("ANTM",)),
    ("2022-09-19", ("CSGP", "INVH"), ("PENN", "PVH")),
    ("2022-10-03", ("EQT", "PCG"), ("CTXS", "DRE")),
    ("2022-10-12", ("TRGP",), ("NLSN",)),
    ("2022-11-01", ("ACGL",), ("TWTR",)),
    ("2022-11-08", ("GEN",), ("NLOK",)),
    ("2022-12-19", ("FSLR",), ("FBHS",)),
    ("2022-12-22", ("STLD",), ("ABMD",)),
    ("2023-01-04", ("GEHC",), ("VNO",)),
    ("2023-03-15", ("BG", "PODD"), ("SBNY", "SIVB")),
    ("2023-03-20", ("FICO",), ("LUMN",)),
    ("2023-05-04", ("AXON",), ("FRC",)),
    ("2023-05-16", ("RVTY",), ("PKI",)),
    ("2023-06-07", ("FI",), ("FISV",)),
    ("2023-06-20", ("PANW",), ("DISH",)),
    ("2023-07-10", ("EG",), ("RE",)),
    ("2023-08-25", ("KVUE",), ("AAP",)),
    ("2023-08-30", ("COR",), ("ABC",)),
    ("2023-09-18", ("ABNB", "BX"), ("LNC", "NWL")),
    ("2023-10-02", ("VLTO",), ("DXC",)),
    ("2023-10-18", ("HUBB", "LULU"), ("ATVI", "OGN")),
    ("2023-12-18", ("BLDR", "JBL", "UBER"), ("ALK", "SEDG", "SEE")),
    ("2024-02-01", ("DAY",), ("CDAY",)),
    ("2024-03-04", ("DOC",), ("PEAK",)),
    ("2024-03-18", ("DECK", "SMCI"), ("WHR", "ZION")),
    ("2024-03-25", ("CPAY",), ("FLT",)),
    ("2024-04-01", ("SOLV",), ("VFC",)),
    ("2024-04-02", ("GEV",), ("XRAY",)),
    ("2024-05-08", ("VST",), ("PXD",)),
    ("2024-06-24", ("CRWD", "GDDY", "KKR"), ("CMA", "ILMN", "RHI")),
    ("2024-07-08", ("SW",), ("WRK",)),
    ("2024-09-23", ("DELL", "ERIE", "PLTR"), ("AAL", "BIO", "ETSY")),
    ("2024-09-30", ("AMTM",), ()),
    ("2024-10-01", (), ("BBWI",)),
    ("2024-11-26", ("TPL",), ("MRO",)),
    ("2024-12-23", ("APO", "LII", "WDAY"), ("AMTM", "CTLT", "QRVO")),
    ("2025-03-24", ("DASH", "EXE", "TKO", "WSM"), ("BWA", "CE", "FMC", "TFX")),
    ("2025-05-19", ("COIN",), ("DFS",)),
    ("2025-07-09", ("DDOG",), ("JNPR",)),
    ("2025-07-18", ("TTD",), ("ANSS",)),
    ("2025-07-23", ("XYZ",), ("HES",)),
    ("2025-08-08", ("PSKY",), ("PARA",)),
    ("2025-08-28", ("IBKR",), ("WBA",)),
    ("2025-09-22", ("APP", "EME", "HOOD"), ("CZR", "ENPH", "MKTX")),
    ("2025-10-30", ("SOLS",), ()),
    ("2025-10-31", (), ("KMX",)),
    ("2025-11-03", ("Q",), ()),
    ("2025-11-04", (), ("EMN",)),
    ("2025-11-11", ("FISV",), ("FI",)),
    ("2025-11-28", ("SNDK",), ("IPG",)),
    ("2025-12-11", ("ARES",), ("K",)),
    ("2025-12-22", ("CRH", "CVNA", "FIX"), ("LKQ", "MHK", "SOLS")),
    ("2026-01-14", ("MRSH",), ("MMC",)),
    ("2026-02-09", ("CIEN",), ("DAY",)),
    ("2026-03-23", ("COHR", "LITE", "SATS", "VRT"), ("LW", "MOH", "MTCH", "PAYC")),
    ("2026-04-09", ("CASY",), ("HOLX",)),
    ("2026-05-07", ("VEEV",), ("CTRA",)),
    ("2026-05-21", ("BNY",), ("BK",)),
    ("2026-06-01", ("FDXF",), ()),
    ("2026-06-02", (), ("EPAM",)),
    ("2026-06-22", ("FLEX", "MRVL"), ("CPB", "POOL")),
    ("2026-06-24", ("ECHO",), ("SATS",)),
    ("2026-06-29", ("HONA",), ()),
    ("2026-06-30", (), ("CAG",)),
)

# The ticker-rename correction layer. For every CURRENT member whose first
# appearance in _MEMBERSHIP_EVENTS is later than MEMBERSHIP_DATA_START,
# Wikipedia's company-level "Date added" is recorded here when it is
# earlier — because the company was in the index all along under its old
# ticker. Taking the earlier of the two sources is robust in the safe
# direction: an erroneously LATE Wikipedia date is ignored (the event data
# already covers it), and an erroneously EARLY one only makes the
# inclusion-bias warning more conservative. All 29 entries were checked
# individually on 2026-08-25; 23 are confirmed renames whose predecessor
# ticker was removed on exactly the successor's addition date (META/FB,
# ELV/ANTM, COR/ABC, RVTY/PKI, GEN/NLOK, WTW/WLTW, EG/RE, DOC/PEAK,
# CPAY/FLT, BALL/BLL, PSKY/PARA, MRSH/MMC, BNY/BK, ECHO/SATS, RTX/UTX,
# HWM/ARNC, VTRS/MYL, TFC/BBT, LHX/HRS, GL/TMK, BKR/BHGE, J/JEC), LIN/PX
# is the same pattern with a 6-day gap (Praxair-Linde closed 2018-10-31),
# TT is a genuine two-company ticker swap left uncorrected in the event
# data, and the remaining 5 (HSIC, EQIX, NWS, CFG, FTV) are 1-4 day
# announcement-vs-effective differences, harmless either way.
_EARLIEST_MEMBERSHIP_OVERRIDES: dict[str, str] = {
    "BALL": "1984-10-31",
    "BKR": "2017-07-07",
    "BNY": "1995-03-31",
    "CFG": "2016-01-29",
    "COR": "2001-08-30",
    "CPAY": "2018-06-20",
    "DOC": "2008-03-31",
    "ECHO": "2026-03-23",
    "EG": "2017-06-19",
    "ELV": "2002-07-25",
    "EQIX": "2015-03-20",
    "FTV": "2016-07-01",
    "GEN": "2003-03-25",
    "GL": "1989-04-30",
    "HSIC": "2015-03-17",
    "HWM": "2016-10-21",
    "J": "2007-10-26",
    "LHX": "2008-09-22",
    "LIN": "1992-07-01",
    "META": "2013-12-23",
    "MRSH": "1987-08-31",
    "NWS": "2015-09-18",
    "PSKY": "1994-09-30",
    "RTX": "1957-03-04",
    "RVTY": "1985-05-31",
    "TFC": "1997-12-04",
    "TT": "2010-11-17",
    "VTRS": "2004-04-23",
    "WTW": "2016-01-05",
}


# Parsed once at import — 235 fromisoformat calls, cheaper than parsing
# ISO strings on every lookup, and keeps the literals above readable and
# diffable as plain dates rather than date(YYYY, M, D) constructor calls.
_EVENTS: tuple[tuple[date, tuple[str, ...], tuple[str, ...]], ...] = tuple(
    (date.fromisoformat(effective), added, removed)
    for effective, added, removed in _MEMBERSHIP_EVENTS
)


class PointInTimeUniverseError(ValueError):
    """Raised when a requested date falls outside this vendored data's
    coverage. Deliberately a hard error rather than a silent clamp to the
    nearest covered date — a backtest quietly told "the 2009 index looked
    exactly like the 2015 index" is worse than one that fails loudly, and
    silently-plausible wrong answers are the whole failure mode this
    module exists to remove."""


@dataclass(frozen=True)
class MembershipExtension:
    """Everything sp500_membership_refresh.py is allowed to add on top of
    the vendored literals, and nothing more. Purely ADDITIVE by
    construction: there is no field here that can retract, re-date, or
    overwrite a vendored event, so a refresh — however wrong its inputs
    turn out to be — can never regress the hand-verified 2015-01-07 ->
    MEMBERSHIP_DATA_AS_OF window. The worst a bad extension can do is add
    wrong events AFTER that window, which is why the refresh module gates
    every field below behind its own validation.

    coverage_end
        New end of DATED point-in-time coverage, from the upstream
        point-in-time file. Must be >= MEMBERSHIP_DATA_AS_OF; equal to it
        means "upstream has published nothing new".
    events
        Add/remove events strictly after MEMBERSHIP_DATA_AS_OF, same shape
        as _EVENTS. Two kinds live here: dated upstream events (<=
        coverage_end) and additions dated from the live constituent
        sources (> coverage_end) — the latter are deliberately NOT allowed
        to advance coverage_end, because the live sources can date an
        addition exactly but cannot date a removal at all.
    earliest_overrides
        Same role as _EARLIEST_MEMBERSHIP_OVERRIDES: a current member whose
        company was in the index under a previous ticker. Only ever moves
        a first-membership date EARLIER, never later.
    live_members / live_as_of
        The cross-validated current constituent set and the date it speaks
        to. Used only for the undated "no longer in the live index"
        disclosure in build_membership_warnings — never to synthesize a
        removal event, because no free live source publishes a removal's
        effective date.
    """

    coverage_end: date
    events: tuple[tuple[date, tuple[str, ...], tuple[str, ...]], ...] = ()
    earliest_overrides: tuple[tuple[str, date], ...] = ()
    live_members: frozenset[str] | None = None
    live_as_of: date | None = None
    sources: tuple[str, ...] = ()


@dataclass(frozen=True)
class _MembershipState:
    """One immutable bundle of everything derived from vendored data plus
    the current extension. Rebound as a single global so a reader can
    never observe a half-applied refresh: the runner builds a whole new
    state off to the side and swaps it in with one assignment."""

    extension: MembershipExtension | None
    events: tuple[tuple[date, tuple[str, ...], tuple[str, ...]], ...]
    intervals: dict[str, list[tuple[date, date | None]]] = field(repr=False, default_factory=dict)
    coverage_end: date = MEMBERSHIP_DATA_AS_OF


def _build_membership_intervals(
    events: tuple[tuple[date, tuple[str, ...], tuple[str, ...]], ...],
    extra_overrides: tuple[tuple[str, date], ...] = (),
) -> dict[str, list[tuple[date, date | None]]]:
    """Replays the events once into per-ticker [start, end) intervals, end
    None meaning "still a member at the end of coverage". A ticker can
    legitimately have several intervals — genuine index re-entries
    (DXC, FSLR, DD, DOW, KDP, EQT, PCG, SNDK) plus the one rename artifact
    documented at the top of this module (FISV)."""
    open_since: dict[str, date] = {ticker: MEMBERSHIP_DATA_START for ticker in _BASE_UNIVERSE}
    intervals: dict[str, list[tuple[date, date | None]]] = {}
    for effective, added, removed in events:
        for ticker in removed:
            started = open_since.pop(ticker, None)
            if started is not None:
                intervals.setdefault(ticker, []).append((started, effective))
        for ticker in added:
            if ticker not in open_since:
                open_since[ticker] = effective
    for ticker, started in open_since.items():
        intervals.setdefault(ticker, []).append((started, None))

    overrides: list[tuple[str, date]] = [
        (ticker, date.fromisoformat(iso_date)) for ticker, iso_date in _EARLIEST_MEMBERSHIP_OVERRIDES.items()
    ]
    overrides.extend(extra_overrides)
    for ticker, corrected in overrides:
        spans = intervals.get(ticker)
        if not spans:
            continue
        spans.sort()
        first_start, first_end = spans[0]
        if corrected < first_start:
            spans[0] = (corrected, first_end)

    return {ticker: sorted(spans) for ticker, spans in intervals.items()}


def _build_state(extension: MembershipExtension | None) -> _MembershipState:
    if extension is None:
        return _MembershipState(
            extension=None,
            events=_EVENTS,
            intervals=_build_membership_intervals(_EVENTS),
            coverage_end=MEMBERSHIP_DATA_AS_OF,
        )
    # Vendored events always sort first (every extension event is strictly
    # after MEMBERSHIP_DATA_AS_OF — enforced by the refresh module's own
    # validation, re-asserted here so a hand-built extension in a test
    # cannot quietly reorder verified history).
    for effective, _added, _removed in extension.events:
        if effective <= MEMBERSHIP_DATA_AS_OF:
            raise PointInTimeUniverseError(
                f"Extension event {effective.isoformat()} is inside the vendored window "
                f"(ends {MEMBERSHIP_DATA_AS_OF.isoformat()}); extensions may only ever add events after it."
            )
    events = _EVENTS + tuple(sorted(extension.events))
    return _MembershipState(
        extension=extension,
        events=events,
        intervals=_build_membership_intervals(events, extension.earliest_overrides),
        coverage_end=max(extension.coverage_end, MEMBERSHIP_DATA_AS_OF),
    )


_STATE: _MembershipState = _build_state(None)


def apply_membership_extension(extension: MembershipExtension) -> None:
    """Swap in a validated forward extension. Called only by
    sp500_membership_refresh.py, and only after that module's own
    validation has passed — this function deliberately does NOT re-derive
    that judgement, it just enforces the one invariant it can check
    locally (nothing inside the vendored window) and rebinds the state."""
    global _STATE
    _STATE = _build_state(extension)


def clear_membership_extension() -> None:
    """Fall back to vendored-only data. The refresh module never calls
    this on failure — a failed refresh keeps the last known-good
    extension — it exists so tests can restore the default state."""
    global _STATE
    _STATE = _build_state(None)


def get_membership_extension() -> MembershipExtension | None:
    return _STATE.extension


def vendored_events() -> tuple[tuple[date, tuple[str, ...], tuple[str, ...]], ...]:
    """The hand-verified events exactly as checked in, never affected by an
    extension. Exists so sp500_membership_refresh.py can diff a freshly
    fetched upstream file against them and SAY SO when upstream has
    retroactively re-dated something inside the verified window, instead
    of either silently adopting the change or silently ignoring it."""
    return _EVENTS


def membership_coverage_end() -> date:
    """The last date this module can answer get_universe_as_of for. Equal
    to MEMBERSHIP_DATA_AS_OF until a refresh extends it. Read this, not
    the constant, wherever "how current is this data" matters."""
    return _STATE.coverage_end


def get_live_membership() -> tuple[frozenset[str], date] | None:
    """The cross-validated live constituent set and the date it speaks to,
    or None when no refresh has succeeded yet. Strictly fresher than
    membership_coverage_end() but UNDATED as to when each change happened
    — see MembershipExtension.live_members."""
    extension = _STATE.extension
    if extension is None or extension.live_members is None or extension.live_as_of is None:
        return None
    return extension.live_members, extension.live_as_of


def get_universe_as_of(target_date: date) -> list[str]:
    """The S&P 500's actual constituents on `target_date`, sorted. Raises
    PointInTimeUniverseError outside [MEMBERSHIP_DATA_START,
    membership_coverage_end()] — including for dates after the data ends,
    where ticker_universe.SCREENING_UNIVERSE is the right answer instead.
    Removals are applied before additions within a single effective date;
    the two sets are disjoint by construction (they come from a set
    difference), so the order is defensive, not load-bearing."""
    state = _STATE
    if target_date < MEMBERSHIP_DATA_START or target_date > state.coverage_end:
        raise PointInTimeUniverseError(
            f"No point-in-time S&P 500 membership data for {target_date.isoformat()}; "
            f"coverage is {MEMBERSHIP_DATA_START.isoformat()} to {state.coverage_end.isoformat()}."
        )
    universe = set(_BASE_UNIVERSE)
    for effective, added, removed in state.events:
        if effective > target_date:
            break
        universe.difference_update(removed)
        universe.update(added)
    return sorted(universe)


def get_universe_over(start: date, end: date) -> list[str]:
    """Every ticker that was an index member on ANY day in [start, end],
    sorted — the right primitive for a lookback WINDOW, as opposed to
    get_universe_as_of's single-day answer. A walk-forward replay over
    [start, end] could have held anything that was a member at any point
    in it, so the union (not the intersection, and not the end-date
    snapshot) is what a survivorship-free candidate pool means.

    `end` is CLAMPED to membership_coverage_end() rather than rejected:
    the natural call passes end=today, and refusing that would make the
    function unusable for its only real use. The cost is that members
    added after coverage are missing — union the result with
    ticker_universe.SCREENING_UNIVERSE if the caller needs today's
    members too. `start` is NOT clamped: a start before the data begins
    means the caller is asking about a period this module genuinely
    cannot speak to, which must fail loudly."""
    if start > end:
        raise PointInTimeUniverseError(f"start {start.isoformat()} is after end {end.isoformat()}.")
    if start < MEMBERSHIP_DATA_START:
        raise PointInTimeUniverseError(
            f"No point-in-time S&P 500 membership data for {start.isoformat()}; "
            f"coverage starts {MEMBERSHIP_DATA_START.isoformat()}."
        )
    state = _STATE
    capped_end = min(end, state.coverage_end)
    members = set(get_universe_as_of(start))
    for effective, added, _removed in state.events:
        if effective > capped_end:
            break
        if effective > start:
            members.update(added)
    return sorted(members)


def get_membership_intervals(ticker: str) -> list[tuple[date, date | None]]:
    """This ticker's [start, end) index-membership intervals in
    chronological order, end None meaning "still a member at the end of
    coverage". Empty list for a ticker that was never an index member in
    the covered window — an ETF, an ADR, a small cap, or simply a member
    whose entire tenure predates MEMBERSHIP_DATA_START. Callers must not
    read an empty list as "definitely never in the S&P 500"; it means "no
    membership recorded in this window."""
    return list(_STATE.intervals.get(ticker, ()))


def was_member(ticker: str, on: date) -> bool:
    """Whether `ticker` was an S&P 500 constituent on `on`. False outside
    the covered window too — a caller that needs to distinguish "no" from
    "unknown" should compare against MEMBERSHIP_DATA_START /
    MEMBERSHIP_DATA_AS_OF itself, which is exactly what
    build_membership_warnings does below."""
    for started, ended in _STATE.intervals.get(ticker, ()):
        if started <= on and (ended is None or on < ended):
            return True
    return False


def earliest_membership_date(ticker: str) -> date | None:
    """The first date this ticker is known to have been an index member,
    or None if it was never one in the covered window. Equal to
    MEMBERSHIP_DATA_START for anything already in the index when the data
    begins — that is a censored lower bound, not a real addition date."""
    spans = _STATE.intervals.get(ticker)
    return spans[0][0] if spans else None


def _as_dates(values: Iterable[object]) -> list[date]:
    """Accepts pandas Timestamps, datetimes, or plain dates — the replay
    index handed in by the strategy modules is a DatetimeIndex, but the
    membership logic itself is pure stdlib and must not import pandas
    just for this."""
    return [value.date() if hasattr(value, "date") else value for value in values]  # type: ignore[misc]


def build_membership_warnings(ticker: str, replay_dates: Iterable[object]) -> list[str]:
    """Point-in-time universe disclosure for a backward-looking backtest:
    given the trading days a walk-forward run actually replayed, say
    plainly which of them fall outside the ticker's real S&P 500
    membership.

    This is deliberately a WARNING and not a filter. Clipping the replay
    to the membership interval would destroy genuine out-of-sample price
    history for a ticker the user can trade today regardless of index
    membership, and would silently invalidate every stored backtest and
    forward-validation state. What is actually wrong today is the silent
    part: the CANDIDATE was drawn from today's index (screening_runner.py
    screens ticker_universe.SCREENING_UNIVERSE) while the RESULT is
    measured over years in which it may not have been a member at all.
    Disclosing that, rather than quietly changing the number, is the same
    convention screening.py already follows for its HAC and HMM tags and
    deflated_sharpe.py for its multiple-comparisons correction.

    Returns [] for a ticker with no recorded membership: no S&P 500 claim
    is being made about it, so there is nothing to disclose."""
    state = _STATE
    spans = state.intervals.get(ticker)
    dates = sorted(_as_dates(replay_dates))
    if not spans or not dates:
        return []

    warnings: list[str] = []
    total = len(dates)

    uncovered = sum(1 for d in dates if d < MEMBERSHIP_DATA_START)
    if uncovered:
        warnings.append(
            f"Point-in-time S&P 500 membership data starts "
            f"{MEMBERSHIP_DATA_START.isoformat()}; {uncovered} of the {total} replayed trading days "
            f"precede it and were not checked for index membership."
        )

    joined = spans[0][0]
    if joined > MEMBERSHIP_DATA_START:
        n_before = sum(1 for d in dates if d < joined)
        if n_before:
            warnings.append(
                f"{ticker} joined the S&P 500 on {joined.isoformat()}; {n_before} of the {total} "
                f"replayed trading days precede that date, a period this system's own screening "
                f"universe would never have surfaced it in. Treat the result as inclusion-biased "
                f"(index additions follow strong prior performance), not a clean out-of-sample estimate."
            )

    left = spans[-1][1]
    if left is not None:
        n_after = sum(1 for d in dates if d >= left)
        if n_after:
            warnings.append(
                f"{ticker} left the S&P 500 on {left.isoformat()}; {n_after} of the {total} replayed "
                f"trading days follow that date and fall outside the screening universe."
            )
    else:
        # Still an open interval in the DATED data, but the live
        # constituent sources say the ticker is no longer in the index.
        # Deliberately dateless: no free live source publishes a removal's
        # effective date (see sp500_membership_refresh.py), and inventing
        # one — "removed the day we happened to notice" — would be exactly
        # the silently-plausible wrong answer this module exists to
        # remove. Saying "we know it is out, we do not yet know when" is
        # strictly more information than the alternative of saying nothing
        # until upstream catches up months later.
        live = get_live_membership()
        if live is not None and ticker not in live[0]:
            live_as_of = live[1]
            warnings.append(
                f"{ticker} is not an S&P 500 constituent as of {live_as_of.isoformat()}, but this "
                f"system's dated point-in-time membership data only runs through "
                f"{state.coverage_end.isoformat()}, so its removal date is not known yet and none of "
                f"the {total} replayed trading days could be attributed to a post-removal period. "
                f"An unknown number of the most recent ones fall outside the screening universe."
            )

    return warnings
