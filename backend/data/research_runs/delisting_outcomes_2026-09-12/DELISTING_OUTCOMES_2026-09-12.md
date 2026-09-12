# Delisting outcomes for the whole-market Alpaca price panel — 2026-09-12

## What this is

The whole-market Alpaca panel at `backend/data/price_store_alpaca/v1/` (14,451
tickers, window 2016-01-04..2026-09-11) stores each dead ticker's price history
ending on its last traded bar. For tickers that were **acquired**, that silently
drops the final gain (or loss) shareholders actually realized when the deal
closed — usually a premium over the last quoted price. This run identifies
every dead ticker, looks up what actually happened via Alpaca's free
corporate-actions feed, and computes what a shareholder finally received.

All numbers below are computed from the two committed artifacts
(`dead_names.csv`, `delisting_outcomes.csv`) and are reproducible from the
cached raw feed (`corporate_actions_raw.json.gz`) without re-fetching.

## Corporate-actions `types=` filter — corrected from the task brief

The brief's assumed type-filter strings (`cash_dividends`, `forward_splits`,
`reverse_splits`, `cash_mergers`, `stock_mergers`) are **wrong** — every one of
them returns HTTP 400. Alpaca's own error body names the real, singular
snake_case set: `forward_split, reverse_split, stock_dividend, spin_off,
cash_merger, stock_merger, stock_and_cash_merger, unit_split, cash_dividend,
redemption, name_change, worthless_removal, rights_distribution,
contract_adjustment, partial_call, reorganization,
capital_gains_distribution`. Full probe output:
`corporate_actions_type_probe.txt`.

## Dead-name universe

**1,817 tickers** (of 14,451, 12.6%) have a last bar on or before 2026-08-12
(30 days before the panel's window end). Full list with first/last bar, last
close, bar count and median dollar volume: `dead_names.csv`.

## Outcome counts

| outcome | n | % of dead names |
|---|---|---|
| no_action_found | 1,235 | 68.0% |
| cash_merger | 271 | 14.9% |
| stock_merger | 175 | 9.6% |
| other_action (split/name_change/redemption/worthless_removal) | 102 | 5.6% |
| stock_and_cash_merger | 34 | 1.9% |
| **acquisition total (cash+stock+stock_and_cash merger)** | **480** | **26.4%** |

So roughly **1 in 4** dead names is a confirmed acquisition with a Form-25-type
deal; the remainder is either a non-merger corporate action (5.6%, real event,
no cash/stock value implied by the type itself) or not found in this free
feed at all (68.0% — see the EDGAR spot-check below: this is a real feed
coverage gap, not evidence of 1,235 unexplained failures).

## Premium / `implied_final_return` distribution

Across the 419 merger rows (of 480) where a final value could actually be
computed (61 stock/stock_and_cash mergers could not be priced — the acquirer
symbol was blank in 12 cases, a genuine internal-restructuring artifact, or
its close on the effective date wasn't found in the store in 49 cases):

| stat | all 419 | excluding the 5 flagged suspect rows (n=414) |
|---|---|---|
| min | -96.6% | -96.6% |
| Q1 | -0.05% | ~-0.05% |
| median | **+0.03%** | +0.03% |
| Q3 | +0.28% | +0.28% |
| mean | +0.85% | **-0.36%** |
| max | +241% (suspect, excluded above) | n/a |

**The median premium over the last trade is essentially zero (+0.03%).** This
is not a bug — it is the direct consequence of a measured fact: the gap
between `last_bar` and the deal's `effective_date` is 1 calendar day at the
median and ≤3 days for 94.6% of the 480 merger rows (min -1,800 days / max
1,522 days at the extremes — those extremes are exactly the ticker-reuse cases
flagged as suspects below). Alpaca's feed already carries most acquired
tickers to within a day or two of deal close, by which point arbitrage has
priced the stock to (or very near) the deal consideration. **cash_merger
alone**: median +0.023%, mean -0.9% (ex-suspect, n=269) — same picture.

**Practical implication (the "money-size of the correction"):** for a
strategy that equal-weights every dead name and silently drops the final bar,
splicing in the real payout for the 419 priced merger rows shifts the
equal-weighted average final-period return by **roughly +0.03 to +0.85
percentage points**, driven almost entirely by 5-6 outlier rows rather than a
broad-based bias. The correction is small in aggregate but NOT uniformly
negligible — see FIT below (a genuine +6.06% one-day gap) and the suspect
rows (up to and beyond ±100%, i.e., large enough to matter a great deal for
any single-name attribution even though the aggregate/equal-weighted effect
is muted by dilution across ~1,800 names).

## Three hand-verified rows (exact match)

| ticker | last_bar | last_close | acquirer | rate | effective_date | implied_final_return |
|---|---|---|---|---|---|---|
| ACIA | 2021-02-26 | 114.99 | CSCO | 115.00 | 2021-03-01 | +0.0087% |
| CLDR | 2021-10-07 | 15.99 | (n/a in feed) | 16.00 | 2021-10-08 | +0.0625% |
| FIT | 2021-01-13 | 6.93 | (n/a in feed) | 7.35 | 2021-01-14 | **+6.06%** |

All three reproduce the task brief's stated values exactly (rate and
effective_date match; CLDR/FIT have no `acquirer_symbol` field in Alpaca's
own record — the feed just doesn't populate it for those two deals).

## Suspect rows (implied_final_return outside -90%..+200%)

5 rows, all individually investigated (raw feed dump inspected by hand, not
guessed):

| ticker | outcome | implied_final_return | diagnosis |
|---|---|---|---|
| GV | *(reclassified to `name_change`, no longer a numeric outlier)* | — | **Fixed a real selection bug**: GV had a 2020-12-30 cash_merger record (cusip 381370105, rate $7) AND the actual reason the *later* GV (a different company, cusip 92838F200) stopped trading in 2026 was a 2026-07-31 name_change to GVHGF. A naive "does this ticker have a merger record" check picked the wrong, unrelated 2020 deal (implying a fabricated +4,800% return). Fixed by comparing ALL corporate-action types (not just mergers) and picking the one closest in date to `last_bar`. |
| BFY | stock_merger | +228% | Genuine per the feed: BFY (BNY Mellon-related preferred/depositary-type security, ratio 1.03013→BNY) last traded 3 days before its 2021-04-12 effective date — no ticker-reuse or stale-bar signature found. Flagged for a human to confirm the security type (a depositary share converting into full BNY common at an outsized ratio is unusual and worth independent confirmation before trusting). |
| BSE | stock_merger | +229% | Same deal family as BFY (also →BNY, ratio 0.9923), same diagnosis. |
| EV | stock_and_cash_merger | +241% | **Ticker reuse, not fixed**: the only merger record for EV is Eaton Vance→Morgan Stanley, effective 2021-03-01. But the EV in our dead-name list has `last_bar` 2025-04-17 — over 4 years later. A second, unrelated company also traded as EV until 2025 and this feed has no record explaining ITS delisting, so my selector had nothing closer to prefer. Correctly flagged, not silently trusted. |
| HCAP | cash_merger | -96.3% | Feed data-quality issue: HCAP (Harvest Capital Credit) → PTMN (Portman Ridge) was publicly a stock-for-stock deal, but Alpaca's `cash_mergers` bucket carries `rate: 0.36` for it — almost certainly the exchange ratio mis-typed into the cash-rate field, not a real $0.36 cash payment. Flagged, not corrected (we don't invent a value the feed didn't give us). |
| HHRSW | cash_merger | -96.6% | HHRSW is a warrant (Hall of Fame Resort & Entertainment warrants); a $0.10 cash-out of an out-of-the-money warrant against a $2.97 last quote is plausible on its face but not independently confirmed here — flagged for the same reason. |

Full suspect rows (with all fields): `suspect_rows.csv`.

## `no_action_found` — 10-ticker EDGAR spot-check

1,235 rows have no matching record in Alpaca's corporate-actions feed. Per
the task's own framing, this is **not** proof of 1,235 unexplained failures.
The first 10 alphabetically (AABA, AACQU, ABDC, ACACU, ACAMU, ACGLP, ACKIT,
ACKIU, ACSF, ACTCU) were checked against SEC EDGAR (`browse-edgar` type=25
company search + `efts.sec.gov` full-text search, User-Agent "aladdin2
research autoa0792@gmail.com"). **All 10 have a confirmed real corporate
event on file** (Form 25 or 25-NSE): 8 are SPAC unit/share-class de-SPAC
renames (holders' position continues under a new ticker, e.g. AACQU→ORGN,
ACAMU→CarLotz, ACTCU→Proterra — no cash realized on the old ticker itself,
nothing "lost"), and 2 are confirmed real cash outcomes this feed simply
doesn't carry (AABA/Altaba's 2019-2020 liquidating distributions after the
Verizon sale of Yahoo's operating business; ACGLP/Arch Capital's preferred
Series E redemption at par). Full detail: `edgar_no_action_found_check.txt`.

**This does not resolve all 1,235** — only 10 were checked (time-boxed), and
the pattern (SPAC-related tickers heavily overrepresented among the first 10
alphabetically) may not generalize across the full set. Treating any
`no_action_found` row as "worthless" or "still owed a payout" would both be
guesses; the honest statement is "not found in this free feed," full stop.

## Limitations (read before using this data anywhere)

1. **Stock-merger valuation is an approximation.** `final_value_per_share` for
   a stock or stock_and_cash merger = exchange ratio × the acquirer's own
   close on the effective_date, read from the same price store. This ignores
   any intraday timing/collar mechanics in the actual deal and assumes the
   acquirer's closing price that day is the right reference point — it is a
   reasonable approximation, not the deal's legal cash-equivalent value.
2. **61 of 480 merger rows could not be priced at all**: 12 have a blank
   `acquirer_symbol` in Alpaca's own record (mostly SPAC de-SPAC/internal
   restructuring artifacts, not real 3rd-party stock deals), 49 have an
   acquirer symbol the store either doesn't cover or lacks a close for near
   the effective date.
3. **Feed coverage before 2016 is untested** — this run only queried
   2016-01-01 onward, matching the panel's own window; whether Alpaca's
   corporate-actions feed is reliable for older delistings is unknown.
4. **`no_action_found` is not "no delisting happened" or "shareholders got
   nothing."** It means "not found in Alpaca's free feed for the 8 types
   requested." The 10-name EDGAR check above found real events for 10/10;
   extrapolating that rate to all 1,235 would itself be a fabrication — it
   is reported as a spot-check, not a resolution.
5. **Ambiguous/reused tickers**: 68 of the 1,817 dead names had more than one
   candidate corporate-action record (merger and/or non-merger) competing for
   the same ticker symbol. All 68 are resolved by picking whichever record's
   date is closest to `last_bar`, tie-broken toward richer merger types over
   a bare cash sweep — every such row is annotated in its `notes` field so a
   human can audit the choice; GV, ARYA, and TSU are confirmed examples where
   this logic changed the outcome from wrong to right (verified by hand
   against the raw feed dump).
6. **Suspect-row diagnoses (BFY/BSE/HCAP/HHRSW) are my read of the raw feed,
   not independently confirmed against a second source** (e.g. the actual
   merger proxy). They are flagged, not corrected — do not treat their
   `final_value_per_share` as trustworthy without a second look.
7. This whole analysis depends on the not-yet-merged
   `whole-market-panel-2026-09-12` branch's STORE (read directly, files only)
   — not that branch's code. If the store's own construction has defects
   (e.g. a share-basis issue like the 2026-09-09 price-store defect found
   elsewhere in this project), those would propagate into `last_close` here
   unexamined; this run did not re-audit the store itself.
