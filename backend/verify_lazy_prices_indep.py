"""Independent verification of the Lazy Prices point-in-time discipline,
against the REAL production data (cached EDGAR documents), not fixtures.

Checks three things the unit tests can only check on synthetic input:
  1. No panel cell is non-NaN before the filing that produced it was ACCEPTED
     by EDGAR — the look-ahead guard, on real acceptance timestamps.
  2. Every observation's availability date strictly postdates its own fiscal
     period end, and by how much (the measured filing lag).
  3. Every scored pair is same-form (10-K vs 10-K), on the real filing index.

Run from backend/ with the production cache already populated.
"""

import sys

import numpy as np
import pandas as pd

from app.services.market_data.edgar_filing_text_provider import (
    EdgarFilingTextProvider,
    availability_date,
)
from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.cross_sectional_lazy_prices import (
    LAZY_PRICES_FORMS,
    build_similarity_observations,
    build_similarity_panel,
    pair_same_type_filings,
)

TICKERS = [
    "AAPL", "MSFT", "JNJ", "KO", "BA", "GE", "XOM", "WMT",
    "CAT", "NVDA", "PG", "T", "JPM", "AMZN", "MRK",
]
START = pd.Timestamp("2015-01-07").date()
END = pd.Timestamp("2026-08-31").date()

prov = EdgarFilingTextProvider()
index, report = prov.build_filing_index(TICKERS, forms=LAZY_PRICES_FORMS)
print(f"indexed {report.n_tickers_indexed} tickers, {report.n_filings_listed} filings")

# --- check 3: same-form pairing on the REAL index --------------------------
n_pairs = 0
for ticker, filings in index.items():
    for previous, current in pair_same_type_filings(filings):
        n_pairs += 1
        if previous.form != current.form:
            print(f"FAIL cross-type pair {ticker}: {previous.form} -> {current.form}")
            sys.exit(1)
print(f"CHECK 3 PASS: all {n_pairs} real pairs are same-form")

# --- check 2: the filing lag, and EDGAR's own reportDate anomalies ---------
# NOT a pass/fail gate on the pipeline: this module never reads report_date for
# a visibility decision, so a bad one cannot hurt it. The check exists to
# MEASURE the lag a period-end-keyed design would have wrongly claimed, and to
# count how often EDGAR's own reportDate is untrustworthy.
lags = []
anomalies = []
for ticker, filings in index.items():
    for f in filings:
        if f.report_date:
            lag = (availability_date(f) - f.report_date).days
            lags.append(lag)
            if lag <= 0:
                anomalies.append((ticker, f.accession, f.report_date, availability_date(f)))
lags.sort()
print(f"CHECK 2: {len(lags)} filings, availability-minus-period-end "
      f"min={lags[0]}d p50={lags[len(lags)//2]}d max={lags[-1]}d "
      f"— a signal keyed to the period end would have led the truth by the median.")
print(f"  EDGAR reportDate anomalies (lag <= 0): {len(anomalies)}")
for ticker, accession, report, avail in anomalies:
    print(f"    {ticker} {accession}: reportDate={report} == availability={avail} "
          "(EDGAR recorded the filing date as the period end; this module is "
          "immune because visibility comes from acceptanceDateTime)")

# --- check 1: the panel is NaN before acceptance ---------------------------
yf = YFinanceProvider()
frames, missing = yf.get_daily_ohlcv(TICKERS, START, END)
close = frames["close"]
observations, sim_report = build_similarity_observations(
    prov, {t: index[t] for t in index}, metrics=("cosine",), scopes=("full",)
)
by_ticker = observations[("cosine", "full")]
panel, ages, unusable = build_similarity_panel(close, by_ticker)

violations = 0
checked = 0
for ticker, obs in by_ticker.items():
    if ticker not in panel.columns:
        continue
    first_available = min(o.available for o in obs)
    column = panel[ticker]
    before = column.loc[column.index < pd.Timestamp(first_available)]
    checked += 1
    bad = int(np.isfinite(before.to_numpy(dtype=float)).sum())
    if bad:
        violations += bad
        print(f"FAIL {ticker}: {bad} non-NaN cells before first availability {first_available}")
print(f"CHECK 1 {'PASS' if violations == 0 else 'FAIL'}: {checked} tickers, "
      f"{violations} cells visible before their filing was accepted")

# CHECK 1b: rebuild the expected step panel FROM SCRATCH, sharing no code with
# build_point_in_time_factor_frame, and require an exact match.
#
# A first version of this check matched observations to panel cells by VALUE
# with np.isclose, and reported a violation that turned out to be the check's
# own bug, not the pipeline's: Walmart's 2022 and 2024 similarities are
# 0.9933533706 and 0.9933615778 — equal to five decimals, so the default
# rtol=1e-5 collided them and matched the 2024 observation against the 2022
# cell. (That two consecutive Walmart 10-Ks score that close is itself a real
# datum about how stable its filings are.) Reconstructing the whole series is
# immune to value collisions and is a stronger check anyway.
step_violations = 0
for ticker, obs in by_ticker.items():
    if ticker not in panel.columns:
        continue
    kept = []
    for event in sorted(obs, key=lambda o: (o.available, o.end)):
        if kept and event.end <= kept[-1].end:
            continue  # a stale period arriving after a fresher one
        kept.append(event)
    expected = []
    for stamp in panel.index:
        day = stamp.date()
        live = [o for o in kept if o.available <= day]
        if not live:
            expected.append(np.nan)
            continue
        latest = live[-1]
        age = (day - latest.available).days
        expected.append(latest.value if age <= 455 else np.nan)
    got = panel[ticker].to_numpy(dtype=float)
    want = np.asarray(expected, dtype=float)
    mismatch = int((~((np.isnan(got) & np.isnan(want)) | (got == want))).sum())
    if mismatch:
        step_violations += mismatch
        print(f"FAIL {ticker}: {mismatch} rows differ from the from-scratch reconstruction")
print(f"CHECK 1b {'PASS' if step_violations == 0 else 'FAIL'}: from-scratch panel "
      f"reconstruction differs on {step_violations} cells")

print(f"\nsection coverage on these tickers: {sim_report.n_pairs_scored} scored, "
      f"{sim_report.n_pairs_section_missing} section-missing")
sys.exit(0 if violations == 0 and step_violations == 0 else 1)
