# Does SEC's free whole-market accounting data carry what we need? — measured, not assumed (2026-09-12)

Orchestrator: Opus 5, own measurement (`measure_fsds_coverage.py`, output `fsds_coverage.json`).
Two quarters measured end to end: **2016q1** (6,011 filers, 6,532 filings) and **2024q1** (5,506
filers, 6,028 filings). A tag counts only as a CONSOLIDATED fact (empty `segments` and `coreg`).

## 1. Answer in one line
**Yes for the core, with two real caveats** — the tag names migrate over time, so every field needs
a fallback ladder; and cost of goods sold is thin (44–47%), which limits gross-profitability
signals to roughly half the market.

## 2. Coverage of every field the top buildable predictors need (% of filers, after the ladder)

| field | 2016q1 | 2024q1 | ladder used |
|---|---|---|---|
| total assets | **98.1%** | **99.3%** | Assets |
| operating cash flow | **97.7%** | 93.3% | …OperatingActivities, …OperatingActivitiesContinuingOperations |
| financing cash flow | 96.3% | 92.6% | same pair |
| investing cash flow | 90.3% | 86.2% | same pair |
| shares outstanding | 89.8% | 87.0% | CommonStockSharesOutstanding, …Issued, WeightedAverageBasic |
| equity | 89.7% | 87.2% | StockholdersEquity |
| net income | 89.6% | 87.8% | NetIncomeLoss |
| current assets / liabilities | 75.0% / 74.9% | 72.7% / 72.4% | AssetsCurrent, LiabilitiesCurrent |
| revenue | 73.2% | 72.5% | RevenueFromContractWithCustomer(Excl/Incl), Revenues, SalesRevenueNet, …GoodsNet, …ServicesNet |
| operating income | 72.3% | 71.2% | OperatingIncomeLoss |
| income tax expense | 71.8% | 72.1% | IncomeTaxExpenseBenefit |
| **cost of goods sold** | **46.5%** | **43.8%** | CostOfGoodsAndServicesSold, CostOfRevenue, CostOfGoodsSold, CostOfServices |
| gross profit (direct) | 34.9% | 36.6% | GrossProfit |
| buybacks / issuance / dividends paid | 36.9 / 34.2 / 34.0% | 39.2 / 29.7 / 33.4% | single tags |
| long-term debt issued / repaid | 22.8 / 26.6% | 17.2 / 21.0% | single tags |
| deferred tax | 35.6% | 31.8% | DeferredIncomeTaxExpenseBenefit |
| **federal / foreign tax split** | **0.1% / 0.0%** | **0.0% / 0.0%** | not usable — use the fallback branch |

## 3. The two caveats, with the evidence
**(a) Tags migrate; a single-tag build would silently lose half the sample.** Measured:
`SalesRevenueNet` 1,633 filers in 2016 → **0** in 2024; `RevenueFromContractWithCustomerExcludingAssessedTax`
0 → 2,161 (the 2018 revenue-standard change). `CostOfGoodsSold` 1,260 → 2. Operating cash flow splits
across two tags: 3,320 + 2,808 in 2016 vs 5,070 + 227 in 2024 — using only the first tag gives 55%
in 2016 and 92% in 2024, which looks like a trend in the data and is really a trend in the tagging.
The ladders above restore 93–98%. **Any predictor built here must use a ladder and report which tag
supplied each value.**

**(b) Flow items read low because most firms do not do them.** A firm with no buyback does not tag
`PaymentsForRepurchaseOfCommonStock`; absence usually means zero, not missing. That is fine for
signals whose definition treats a non-payer as zero (net payout yield, external finance), and it is
NOT fine to impute silently. Rule for the build: a flow field absent while the cash-flow statement
IS present (93%+) is treated as zero and counted; a flow field absent with no cash-flow statement
is missing. Both counts get reported per predictor.

## 4. What this means for the top-15 buildable predictors
- **Fully covered** (assets, income, cash flows, equity, tax expense, share counts):
  NetPayoutYield, XFIN, PctTotAcc, NetEquityFinance, cfp, roaq, ChTax, ShareIss1Y/5Y, Tax
  (Tax's federal+foreign numerator is unusable at 0.1% — its own definition's fallback,
  total tax minus deferred tax, is covered at 72% / 32%).
- **Half covered**: GP (needs revenue AND cogs → ~44%). Buildable on the covered half, with the
  restriction disclosed, or via the direct `GrossProfit` tag (35–37%).
- **Needs a substitute, not blocked**: AnnouncementReturn — the top-ranked buildable predictor —
  uses IBES only for the announcement DATE; this project already reads Item 2.02 8-K dates from
  EDGAR (`cross_sectional_pead.py`), so the date source substitutes.
- **NOT buildable free, correction to Set 3**: EarningsStreak (SR 0.87) needs IBES analyst
  estimates (`actual − meanest`), although OSAP labels it Cat.Data = Accounting. My Set 3
  buildability screen used Cat.Data alone, so **163 is an upper bound**. A keyword scan of all 163
  definitions flags 5 as analyst-dependent (AnnouncementReturn — date only, substitutable;
  EarningsStreak — genuinely blocked; RIO_Disp, ProbInformedTrading, Beta — low Sharpe, unchecked
  in detail). The Set 3 pooled numbers are not re-computed for this (that would be a second look);
  the correction is recorded here and the affected names are flagged before any build.
- Not from this source at all (and not needed from it): DivYieldST and VolumeTrend (prices,
  dividends, volume), ShortInterest (FINRA), IO_ShortInterest (13F + FINRA).

## 5. Scale and cost
~100–125 MB per quarter zipped; `num.txt` alone is 409–487 MB per quarter uncompressed, so the
ingest must stream and filter (the `nport_provider` pattern) rather than keep raw files. 2016q1 →
2026q2 is ~42 quarters. Free, no registration. `filed` in `sub.txt` is SEC's own receipt date, which
makes a dated point-in-time view exact rather than inferred.

## 6. Not verified here
Whether quarterly (`qtrs=1`) values are as complete as annual for the fields above (only tag-level
coverage was measured); restatement behaviour across quarters (the store's first-write-wins rule
handles it, untested here); how many of these filers map to a tradable ticker (that join needs the
A1 universe, which is being built); IFRS filers (761 `Assets` facts in 2024q1 carry the `ifrs`
namespace and are excluded by a us-gaap-only ladder).
