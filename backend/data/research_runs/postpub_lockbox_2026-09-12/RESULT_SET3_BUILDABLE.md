# Set 3 result — how much of the published book is within our reach (2026-09-12, computed once under `PROTOCOL_SET3_BUILDABLE.md` @ 2881420; header time read from the clock: 13:58)

## Headline
Of the 195 P-clean predictors, **163 are in data categories our free stack already covers**
(Accounting 96 via EDGAR companyfacts, Price 41, Trading/volume 13, Event 7, 13F 6); 32 are not
(Analyst 18, Options 9, Other 5 — IBES and options data are paid gaps P6-class).

| book | members | months | Sharpe after haircut | NW t | PSR |
|---|---|---|---|---|---|
| Set 2 primary (all P-clean) | 195 | 612 | 0.599 | 4.27 | ≈1.00 |
| **buildable only** | **163** | **612** | **0.597** | **4.26** | **≈1.00** |
| not buildable only | 32 | 480 | 0.517 | 2.71 | 0.999 |

**The edge is not hiding in the data we lack.** The buildable book carries the whole Set 2 result.
Orchestrator re-derivation (plain-Python csv, no shared code): 163 / 612 / 0.4237 %/mo / Sharpe
0.5974 — exact.

## Independence inside the buildable set (sealed months, ≥120 overlapping)
12,141 pairs: mean ρ 0.029, mean |ρ| 0.216, **27% of pairs at |ρ| ≥ 0.30** (families of near-
duplicates — external-financing variants, accrual variants, valuation ratios — cluster). The
buildable and non-buildable books correlate 0.24 over 480 months. Median per-predictor sealed
Sharpe after haircut 0.17; 77% positive. So the effective number of independent members is well
below 163 — the Day-1 census logic (drop hubs) applies before anything is admitted.

## Top of the ranking (buildable, sealed Sharpe after haircut; descriptive, not admission)
| predictor | data | economic | published | sealed months | SR | t |
|---|---|---|---|---|---|---|
| AnnouncementReturn | Price | earnings event | 1996 | 336 | 1.01 | 5.3 |
| DivYieldST | Accounting | valuation | 1979 | 540 | 0.98 | 6.4 |
| VolumeTrend | Trading | volume | 1996 | 336 | 0.94 | 5.0 |
| NetPayoutYield | Accounting | valuation | 2007 | 204 | 0.91 | 3.4 |
| EarningsStreak | Accounting | earnings growth | 2012 | 144 | 0.87 | 2.5 |
| XFIN | Accounting | external financing | 2006 | 216 | 0.83 | 2.9 |
| GP | Accounting | profitability | 2013 | 132 | 0.79 | 2.9 |
| ShareIss5Y | Accounting | external financing | 2006 | 216 | 0.76 | 2.9 |
| PctTotAcc | Accounting | accruals | 2011 | 156 | 0.74 | 2.1 |
| NetEquityFinance | Accounting | external financing | 2006 | 216 | 0.71 | 2.6 |
| IO_ShortInterest | 13F | ownership | 2005 | 228 | 0.70 | 3.1 |
| Tax | Accounting | other | 2004 | 240 | 0.68 | 3.5 |
| cfp | Accounting | valuation | 2004 | 240 | 0.66 | 2.4 |
| roaq | Accounting | profitability | 2010 | 168 | 0.66 | 2.3 |
| ShortInterest | Trading | short sale constraints | 2001 | 276 | 0.66 | 4.2 |
Full table: `set3_per_predictor.csv` (163 buildable + 32 not, with authors and descriptions).

## Overlap with families this project already tested (flagged, not double-counted)
Our free-data versions of several of these exist and were NEGATIVE or parked on our universes:
asset growth, net share issuance (buyback), PEAD via announcement return (pead_ear ≈ AnnouncementReturn),
residual momentum, capital-gains overhang, insider trading, short interest, cash-based profitability.
The OSAP sealed numbers for those are evidence about the CRSP-breadth, equal-weight versions;
ours ran on S&P 500/600 with 5 bps flat costs. The gap between the two is the next thing to
measure — it is the cost of our universe, and it is measurable predictor by predictor.

## Caveats carried from Set 2
Idea survivorship; OSAP's equal-weight CRSP universe includes micro-caps (HXZ); haircut is a
turnover upper bound, not a per-name spread; "buildable" means the data CATEGORY exists here —
breadth (thousands of names vs our ~500–2,000) and history (1974→ vs our 2016→ for delisted
coverage) do not.

## What this changes
The project's founding thesis — many small published edges, pooled — has its first measured
support, and 84% of that support sits in data categories we already hold. The honest path is now
concrete: pick the least-correlated buildable predictors, pre-register each on our data with the
paper-faithful spec ONLY (no grid), compare our sealed-window number to OSAP's, and admit to the
BOOK at screening level. That is Step 2 of the roadmap, with the search space no longer empty.

---
CORRECTION (appended 2026-09-12): the header says 13:58; the shell clock at commit read 13:54. Written ahead of the clock again; content unchanged.
