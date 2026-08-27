"""Independent re-check of the scout's Alpaca delisted-ticker claim, using a
FRESH sample of real S&P 500 departures (M&A delistings) drawn from
sp500_membership_history.py's own vendored event data, distinct from
whatever S&P 600 sample the scout checked tonight.

Each ticker below is a real company whose stock stopped trading because of
an acquisition -- known independently (not just from the membership file's
own comments) -- with the acquisition's real close date noted for the
spot-check. removed_event_date is the S&P 500 index-removal effective date
recorded in sp500_membership_history.py, which for an M&A removal is
typically the deal-close date or within a day or two of it.
"""

import sys
from datetime import date, timedelta

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")

from app.services.market_data.alpaca_provider import AlpacaProvider, AlpacaError  # noqa: E402

SAMPLE = [
    # ticker, company, real acquirer, real deal-close date (independent knowledge), index-removal event date
    ("PCP",  "Precision Castparts",          "Berkshire Hathaway", date(2016, 1, 29), date(2016, 2, 1)),
    ("CAM",  "Cameron International",        "Schlumberger",       date(2016, 4, 1),  date(2016, 4, 4)),
    ("BRCM", "Broadcom Corp",                "Avago Technologies", date(2016, 2, 1),  date(2016, 2, 1)),
    ("SIAL", "Sigma-Aldrich",                "Merck KGaA",         date(2015, 11, 18), date(2015, 11, 18)),
    ("FDO",  "Family Dollar",                "Dollar Tree",        date(2015, 7, 6),  date(2015, 7, 7)),
    ("DTV",  "DirecTV",                      "AT&T",               date(2015, 7, 24), date(2015, 7, 27)),
    ("ARG",  "Airgas",                       "Air Liquide",        date(2016, 5, 23), date(2016, 5, 23)),
    ("GAS",  "AGL Resources",                "Southern Company",   date(2016, 7, 1),  date(2016, 7, 1)),
    ("TE",   "TECO Energy",                  "Emera",              date(2016, 7, 1),  date(2016, 7, 1)),
    ("BXLT", "Baxalta",                      "Shire",              date(2016, 6, 3),  date(2016, 6, 3)),
    ("SNI",  "Scripps Networks Interactive", "Discovery Comm.",    date(2018, 3, 6),  date(2018, 3, 7)),
    ("WFM",  "Whole Foods Market",           "Amazon",             date(2017, 8, 28), date(2017, 8, 28)),
    ("RAI",  "Reynolds American",            "British American Tobacco", date(2017, 7, 25), date(2017, 7, 25)),
    ("MON",  "Monsanto",                     "Bayer",              date(2018, 6, 7),  date(2018, 6, 7)),
    ("ESRX", "Express Scripts",              "Cigna",              date(2018, 12, 20), date(2018, 12, 21)),
    ("AET",  "Aetna",                        "CVS Health",         date(2018, 11, 28), date(2018, 11, 29)),
    ("COL",  "Rockwell Collins",             "United Technologies", date(2018, 11, 26), date(2018, 11, 27)),
    ("SCG",  "SCANA Corp",                   "Dominion Energy",    date(2019, 1, 1),  date(2019, 1, 2)),
    ("MXIM", "Maxim Integrated",             "Analog Devices",     date(2021, 8, 26), date(2021, 8, 30)),
    ("KSU",  "Kansas City Southern",         "Canadian Pacific",   date(2021, 12, 14), date(2021, 12, 14)),
]

provider = AlpacaProvider()

results = []
for ticker, company, acquirer, close_date, removed_event in SAMPLE:
    start = close_date - timedelta(days=730)
    end = close_date + timedelta(days=90)
    try:
        bars_by_ticker, missing = provider.get_stock_bars([ticker], "1Day", start, end)
    except AlpacaError as exc:
        results.append((ticker, company, close_date, None, f"ERROR: {exc}"))
        continue

    if ticker in missing or ticker not in bars_by_ticker or bars_by_ticker[ticker].empty:
        results.append((ticker, company, close_date, None, "NO DATA RETURNED"))
        continue

    frame = bars_by_ticker[ticker]
    last_date = frame.index[-1].date()
    first_date = frame.index[0].date()
    n_bars = len(frame)
    delta_days = (last_date - close_date).days
    results.append((ticker, company, close_date, last_date, f"first={first_date} n={n_bars} delta_vs_close={delta_days:+d}d"))

print(f"{'TICKER':6} {'COMPANY':30} {'DEAL_CLOSE':11} {'LAST_BAR':11} DETAIL")
resolved = 0
for ticker, company, close_date, last_date, detail in results:
    status = "OK" if last_date is not None else "MISS"
    if last_date is not None:
        resolved += 1
    print(f"{ticker:6} {company:30} {close_date.isoformat():11} {str(last_date):11} {detail}")

print()
print(f"Resolved: {resolved}/{len(SAMPLE)}")
