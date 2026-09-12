# Whole-market Alpaca price panel — 2026-09-12

Store: `/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend/data/price_store_alpaca/v1`
Window: 2016-01-04 .. 2026-09-11

- symbols attempted: 14509
- symbols with >=1 bar: 14451
- symbols with zero bars: 58
- total rows: 20,345,521
- on-disk size: 289.42 MB
- dead names retained (last bar >30 days before window end): 1817

Note: universe.csv has 14,737 rows but 228 duplicate symbols (same ticker
string reused by two distinct Alpaca asset records, e.g. a delisted company
and a later company that took the same ticker) collapse to 14,509 distinct
symbols once deduplicated by symbol — this script measures by distinct
symbol, since the store is keyed by ticker string, not by asset id.

## Breadth by year (symbols with >=200 bars that year)

| year | symbols with >=200 bars |
|---|---|
| 2016 | 5218 |
| 2017 | 5662 |
| 2018 | 6125 |
| 2019 | 6358 |
| 2020 | 6491 |
| 2021 | 6814 |
| 2022 | 7374 |
| 2023 | 7810 |
| 2024 | 8484 |
| 2025 | 9554 |

## Dead names retained — examples

| ticker | last bar date | gap (days) |
|---|---|---|
| ARMO | 2018-06-21 | 3004 |
| ALOG | 2018-06-22 | 3003 |
| CLNS | 2018-06-22 | 3003 |
| FHY | 2018-06-22 | 3003 |
| SPLX | 2018-06-22 | 3003 |
| UBM | 2018-06-22 | 3003 |
| BSWN | 2018-06-25 | 3000 |
| LSVX | 2018-06-25 | 3000 |
| MLPS | 2018-06-25 | 3000 |
| UBC | 2018-06-25 | 3000 |

## Median daily dollar volume, by SEC company_tickers membership

- in SEC company_tickers.json: {"n": 7141, "median": 1110422.44, "q1": 99210.56839999999, "q3": 15025318.325}
- NOT in SEC company_tickers.json: {"n": 7310, "median": 230626.7356, "q1": 33024.7231, "q3": 1772030.88125}

## EDGAR facts store coverage

- CIKs in edgar_facts_store: 163
- of those, resolved to a ticker via SEC company_tickers.json: 162
- of those, covered by this panel: 141
