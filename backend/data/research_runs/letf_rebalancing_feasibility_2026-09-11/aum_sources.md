# Q3 — Historical daily AUM / shares-outstanding sources

Feasibility question: can `A_t` (the LETF's NAV/AUM at the prior close) be
obtained POINT-IN-TIME, i.e. reconstructed for any past date, for free? This
matters because Cheng & Madhavan's `RA_t = NAV_{t-1} * (x^2 - x) * r_t`
requires yesterday's NAV, not today's.

## ProShares — YES, a real free daily historical series exists

ProShares publishes a "Historical NAVs" CSV, linked from its own
`Data Downloads` page:

  Landing page (confirmed live, fetched 2026-09-10 via WebFetch):
  https://www.proshares.com/resources/data-downloads

  Direct file (confirmed live, fetched via `curl` 2026-09-10, HTTP 200,
  52,552,331 bytes with `--max-time 120`; NOTE a first attempt at
  `--max-time 30` silently truncated to 22,574,487 bytes and produced a
  WRONG-looking ticker list — always verify size against a second fetch
  before trusting this endpoint):
  https://accounts.profunds.com/etfdata/historical_nav.csv

Columns, verbatim header row: `Date, ProShares Name, Ticker, NAV, Prior NAV,
NAV Change (%), NAV Change ($), Shares Outstanding (000), Assets Under
Management`. AUM (the last column) is exactly the `A_t` this candidate needs,
already computed by the issuer as NAV * shares outstanding, daily, one row
per fund per trading day.

Coverage measured directly against the fetched file (2026-09-10) for the 12
ProShares tickers this feasibility pass targets:

| Ticker | Rows | First date in file | Fund's own inception (per its page, Q2) |
|---|---|---|---|
| SSO  | 5,088 | 2008-01-02 | 2006-06-19 |
| SDS  | 5,073 | 2008-01-02 | 2006-07-11 |
| UPRO | 4,330 | 2013-01-02 | 2009-06-23 |
| SPXU | 4,330 | 2013-01-02 | 2009-06-23 |
| QLD  | 5,088 | 2008-01-02 | 2006-06-19 |
| QID  | 5,073 | 2008-01-02 | 2006-07-11 |
| TQQQ | 4,171 | 2013-01-02 | 2010-02-09 |
| SQQQ | 4,171 | 2013-01-02 | 2010-02-09 |
| UWM  | 4,939 | 2008-01-02 | 2007-01-23 |
| TWM  | 4,939 | 2008-01-02 | 2007-01-23 |
| URTY | 4,171 | 2013-01-02 | 2010-02-09 |
| SRTY | 4,171 | 2013-01-02 | 2010-02-09 |

A trimmed evidence sample (first 2 + last 2 rows per ticker, real data, not
fabricated) is committed at `proshares_nav_history_sample.csv` in this
directory. The full 52.5MB file was NOT committed (too large for the repo
and easily re-fetched by URL); re-download with the exact `curl` command
above (note the `--max-time` warning) to reproduce.

**Honest gap**: the file's coverage does NOT reach every fund's actual
inception date — UPRO/SPXU/TQQQ/SQQQ/URTY/SRTY are all missing 3-4 years of
their early life (e.g. TQQQ inception 2010-02-09 but data here starts
2013-01-02). Whether ProShares has an older archive elsewhere, or whether
this is a genuine hard floor on what's free, is UNVERIFIED — not checked
further in this feasibility pass.

**Also unverified**: whether this endpoint is authenticated/rate-limited in
a way that would break a scheduled daily puller, and whether its historical
rows are point-in-time-correct (i.e., not later-restated) — ProShares does
not document a "filed/observed" split the way this project's own EDGAR
stores do. Treat every row as "issuer's current historical record", not
"what was known that day", until checked further.

## Direxion — NOT VERIFIED, likely no free historical series

`direxion.com` returned **HTTP 403 to every automated fetch attempt** made
in this session — both `WebFetch` and `curl` with multiple realistic
User-Agent strings, on the fund-listing page and every individual product
page tried (`/product/daily-sp-500-bull-3x-etf`,
`/product/daily-semiconductor-bull-bear-3x-etfs`,
`/product/daily-sp-biotech-bull-bear-3x-etfs`,
`/product/daily-junior-gold-miners-index-bull-bear-2x-etfs`). This is very
likely bot-detection (Cloudflare or similar) rather than the site being
down — plausible given ProShares' own JS-shell listing page also blocked
`curl` while individual ProShares fund pages did not. **A general web
search for "Direxion daily NAV shares outstanding historical download"
found no evidence of an issuer-hosted free historical NAV/shares-outstanding
CSV analogous to ProShares'.** Current-day AUM for Direxion funds in
`letf_universe.csv` was sourced from the third-party aggregator
stockanalysis.com (which itself gives no indication of offering a free
historical time series either, only current snapshots), NOT from Direxion
directly.

**This is a material, disclosed gap**: half the underlyings this candidate
would need (semiconductors, biotech, gold miners, and one of the two S&P 500
issuer families) currently have NO confirmed free point-in-time AUM history.
Options not explored in this feasibility pass: (a) retry Direxion with a
headless browser (the `browser-automation` skill) rather than raw HTTP, (b)
SEC N-PORT (below) as an issuer-agnostic backstop, (c) contacting Direxion
directly, (d) a paid aggregator (ETFdb, YCharts, Bloomberg).

## SEC N-PORT — issuer-agnostic backstop, monthly and lagged, not daily

Confirmed via search (not independently fetched/parsed in this pass): SEC
Form N-PORT requires registered funds, ETFs included, to report portfolio
data (including AUM) monthly, but only the fiscal-quarter-end month's filing
is made public; the other two months of each quarter are confidential when
filed and only become public with a delay. This project's own
`cross_sectional_nport_flow.py` and `cross_sectional_firesale_pressure.py`
already build on N-PORT bulk data (see those modules' docstrings, read
directly in this session, for the project's established N-PORT ingestion
pattern) — so N-PORT parsing machinery already exists in this repo and could
in principle backstop Direxion's daily-AUM gap, but only at MONTHLY
frequency with a real lag, which is a poor substitute for the daily `A_t`
the rebalancing-demand formula needs. **Not independently verified in this
pass** whether N-PORT's disclosed AUM field is clean enough, or arrives
fast enough, to be useful here — flagged as an open question, not answered.

## Conclusion for Q3

- ProShares: a real, free, daily, multi-year historical AUM/shares-outstanding
  series exists and was independently fetched and verified in this session.
  Sufficient to backtest ProShares-only formation from ~2008/2013 (fund-
  dependent) forward.
- Direxion: no free historical series confirmed; current-day-only via a
  third-party aggregator. This blocks any historical formation on the
  Direxion-only underlyings (semiconductors, biotech, gold miners) unless a
  further source is found. GOING FORWARD collection (starting today) is
  possible for Direxion the same way the project's price/EDGAR stores already
  do it — an ongoing point-in-time store would need to be built.
