# Thai market — free-data probe (2026-09-12)

Everything in this file was produced by the four scripts committed beside it, run on
`backend/venv/bin/python` (yfinance 1.6.0, Python 3.12.14). No credentials, no secrets, no DB
writes. The raw stdout of each run is committed verbatim; the tables below are transcriptions of
those files, not re-typed estimates.

| script | output | what it answers |
|---|---|---|
| `probe_thai_yfinance.py` | `thai_probe_output.txt`, `thai_yfinance_probe.json` | what the Yahoo `.BK` universe contains; whether bars come back; how far back; how thin |
| `probe_thai_boards.py` | `thai_boards_output.txt` | do the foreign board (`-F`) and NVDR (`-R`) lines exist; is `-R` a usable series; are dead names in the live universe |
| `probe_thai_foreign_board.py` | `thai_foreign_board_output.txt` | the `-F` vs main-board premium, and how often `-F` actually trades |
| `thai_window_power_threshold.py` | `thai_window_power_threshold_output.txt` | what claimed net Sharpe a candidate needs on the Thai window, via the project's existing `sourcing_power_check` |

## 1. Where the symbol list came from

SET's own JSON endpoints are **blocked to a script**: `https://www.set.or.th/api/set/stock/list?language=en`
returns **HTTP 403** with an Imperva/Incapsula interstitial even with a browser `User-Agent`,
`Referer: https://www.set.or.th/en/market/get-quote/stock` and `Accept: application/json`;
`https://www.settrade.com/api/set/stock/list` likewise (both probed 2026-09-12, ~10:10 Bangkok).
SET's **HTML** pages return 200 but render their tables client-side.

The universe was therefore enumerated from **Yahoo's own screener endpoint** through
`yfinance.screen(EquityQuery("eq", ["region","th"]))`, paging 250 at a time. That is the right
source for this question anyway: the brief asks what yfinance's `.BK` coverage *actually is*, and
this enumerates exactly that, rather than checking a third-party list against it.

## 2. Universe (stage 1)

```
screener total=2281  rows_fetched=2281  fetched_at=2026-09-12T03:13:10Z
symbol classes:   ordinary 884 | NVDR (-R) 836 | DW/DR (digit suffix) 561
exchange field: {'SET': 2281}      quoteType field: {'EQUITY': 2281}
```

Yahoo tags **every** Thai line `exchange = SET` — there is **no mai flag** in the feed, so SET vs
mai cannot be separated from Yahoo alone (a real limitation for any small-cap work; the split would
have to come from SET's own listing pages).

First-trade dates of the 884 ordinary lines: min **1983-08-26**, p10 2000-01-04, median
2012-09-21, p90 2023-05-09, max 2026-09-01. The year histogram shows **190 names starting exactly
on 2000-01-04** — that is Yahoo's history floor for this market, not 190 simultaneous listings.
Usable calendar window: **2000-01-04 → 2026-09-11 = 26.69 years.**

## 3. Bar availability and thinness (stage 2, seeded sample n=200, seed 20260912)

```
symbols with >=1 daily bar: 200/200   zero bars: 0  errors: 0
first bar: min=1983-08-26 p25=2003-03-11 median=2011-07-28 p75=2019-03-13 max=2025-10-06
last  bar: min=2026-09-10 p25=2026-09-11 median=2026-09-11 max=2026-09-11
bars:      min=233 median=3732 max=10883
median daily turnover THB: p10=179,733 p25=461,968 median=1,519,123 p75=8,141,739 p90=43,368,031
symbols whose LAST bar is before 2026-08-01 (candidate delisted/halted): 0
```

Free daily OHLCV for the listed Thai market is **complete and current** on the names Yahoo lists.
It is also **thin**: median THB 1.52m/day ≈ USD 46k at 33.2 THB/USD (the rate implied by SET's own
August 2026 figure of THB 75.05bn ≈ USD 2.26bn).

## 4. Survivorship (stage 3 + screener membership)

Twelve symbols were chosen as *candidates* for dead/suspended SET names. Their SET status was
**not** independently verified — what is measured here is bar availability and screener membership,
nothing more.

| symbol | bars from Yahoo | in live screener universe |
|---|---|---|
| SSI, MAX, EARTH, PACE, NMG, STARK, IFEC, DTAC | **0 bars each** | no |
| POLAR | 4,020 bars, 2008-08-01 → **2025-01-27** | no |
| MORE | 3,343 bars → 2026-09-11 | yes |
| JAS | 6,616 bars, 2000-01-04 → 2026-09-11 | yes |
| TRUE | 6,616 bars, 2000-01-04 → 2026-09-11 | yes |

8 of 12 return **nothing**; 9 of 12 are absent from the live universe. The free Thai universe is
effectively a **survivor list**. Quantifying the bias needs a real SET delisting list (measurement
M3 in the review).

## 5. The three boards

Thailand quotes the same company on up to three lines: main (local), foreign (`-F`), and NVDR
(`-R`). Both suffixed lines exist on Yahoo.

**NVDR (`-R`) — unusable as a price series.** Median volume **0** on all five probed
(`ADVANC-R`, `BBL-R`, `KBANK-R`, `PTT-R`, `SCB-R`). `PTT-R`/`PTT` − 1 has mean **+265.2%**,
sd 370%, max +1010% over 3,535 overlapping days, while today's raw closes are 42.11 vs 42.00 — the
historical `-R` series is not on the same corporate-action basis as the main line. Any NVDR
premium computed from this feed would be an artefact of the feed.

**Foreign board (`-F`) — exists, long history, mostly stale.** All 15 large names probed have an
`-F` line; BBL/KBANK/BAY/SCCC/EGCO go back to 2000-01-04. Mean `-F`close / main close − 1, whole
common history (transcribed from `thai_foreign_board_output.txt`):

| symbol | days | window | mean | sd | p95 | max | median `-F` vol | `-F` vol = 0 days |
|---|---|---|---|---|---|---|---|---|
| ADVANC | 4539 | 2008-02-04→2026-09-11 | +0.084% | 3.813% | +5.641% | +40.341% | 0 | 3276 |
| BBL | 6616 | 2000-01-04→2026-09-11 | +6.775% | 12.956% | +34.916% | +77.358% | **1,174,500** | 723 |
| KBANK | 6616 | 2000-01-04→2026-09-11 | +3.417% | 5.644% | +15.741% | +60.000% | **1,760,900** | 476 |
| PTT | 4564 | 2007-12-27→2026-09-11 | +0.111% | 3.555% | +6.369% | +29.167% | 0 | 2852 |
| SCB | 1068 | 2022-04-27→2026-09-11 | −0.008% | 1.998% | +2.455% | +36.364% | 0 | 561 |
| CPALL | 4605 | 2007-10-29→2026-09-11 | −2.944% | 10.351% | +5.000% | +64.943% | 0 | 3386 |
| AOT | 5524 | 2004-03-11→2026-09-11 | −2.724% | 16.500% | +14.685% | +131.013% | 0 | 4857 |
| SCC | 5754 | 2003-04-24→2026-09-11 | +2.878% | 5.451% | +14.021% | +36.937% | **135,250** | 1544 |
| TU | 6126 | 2001-11-20→2026-09-11 | +1.846% | 10.561% | +20.107% | +66.477% | 0 | 4713 |
| KTB | 4570 | 2007-12-18→2026-09-11 | +1.558% | 13.319% | +13.260% | +146.023% | 0 | 3618 |
| BAY | 6616 | 2000-01-04→2026-09-11 | +7.275% | 19.551% | +47.059% | +89.607% | 0 | 3590 |
| TISCO | 4543 | 2008-01-29→2026-09-11 | +1.019% | 10.212% | +10.385% | +67.331% | 0 | 3612 |
| SCCC | 6616 | 2000-01-04→2026-09-11 | +16.703% | 34.895% | +82.952% | +152.644% | 0 | 6042 |
| EGCO | 6616 | 2000-01-04→2026-09-11 | +1.766% | 14.335% | +33.898% | +55.665% | 0 | 4177 |
| BANPU | 2380 | 2016-10-28→2026-08-11 | +35.228% | 41.264% | +137.805% | +207.087% | 0 | 2366 |

**Only BBL, KBANK and SCC have a foreign board that trades on most days.** For the other twelve the
"premium" is a live price over a stale one and carries no information. This table is a data
diagnostic; it is **not** a return estimate, and no strategy was formed from it.

## 6. What this window is worth, in this project's own units

`thai_window_power_threshold.py` binary-searches `sourcing_power_check` (existing module, existing
DSR ladder `(8, 43, 397, 1131)`, `sigma_SR = sqrt(periods/n_obs)` per project precedent) for the
smallest claimed net annualized Sharpe that returns PROCEED at 252 periods/yr:

```
Thai 26.69y  n_local=5 : 1.425
Thai 26.69y  n_local=8 : 1.528
Thai 26.69y  n_local=16: 1.660
US control 10.683y n_local=8: 2.416   <- matches DECLINED_AT_SOURCING.md exactly
```

The US control reproducing 2.416 is the check that the search is reading the same gate the ledger
used. The Thai window lowers the bar by ~37% at n_local=8, purely through calendar years.
