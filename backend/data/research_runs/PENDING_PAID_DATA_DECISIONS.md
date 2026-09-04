# PENDING PAID-DATA DECISIONS

Every place this project has hit a wall that only a paid data source closes.
One line per gap: what is missing, what currently stands in for it, which
direction the substitute biases results, and what would close it.

## Why this file did not exist until 2026-09-05, which is itself the finding

Four modules already refer to this list **as though it were a repo artifact**:

| module | line | text |
|---|---|---|
| `cross_sectional_index_removal.py` | 313 | *"the delisted-securities vendor already on this project's pending-paid list (Norgate, CRSP, Sharadar)"* |
| `cross_sectional_seasonality.py` | 232 | *"the project's known delisted-securities gap — see the pending-paid-decisions list"* |
| `cross_sectional_commodities.py` | 560 | *"a real borrow feed is a paid data source, already on the project's pending-paid list"* |
| `cross_sectional_bonds.py` | 414 | *"a real borrow feed is a paid data source and is noted as such rather than silently wished away"* |

A `grep -rn "pending.paid"` over the whole repo before this commit returned
those four references and **no list**. The list existed only in an agent's
conversational memory, so every one of those cross-references pointed at
nothing a reader of this repository could open. That is the same class of
failure as an uncited number: a claim that looks sourced and is not.

This file is the list those four comments have been pointing at. It is
started, not backfilled: an entry appears here only where the gap is
evidenced by a specific in-repo line, quoted below. Gaps that exist only in
conversation are **not** transcribed here from memory.

---

## OPEN

### P1 — Securities-lending / short-borrow rate feed

* **Missing:** per-name, per-day historical equity borrow rates.
* **Stand-in as of 2026-09-05:** for US single-stock equity families,
  `financing_bps_per_year = 0.0` — verified literal in
  `QUALITY_`/`BUYBACK_`/`BEST_IDEAS_`/`SHORT_INTEREST_FINANCING_BPS_PER_YEAR`,
  and the config default passed through by lazy_prices, pead, jump_drift,
  residual_momentum, asset_growth and quality_neutral. Non-single-stock
  families already charge a declared assumption: bonds 20, commodities 40,
  fx 25, eigenportfolio 50, correlation_risk_premium 100 bps/yr.
* **New as of 2026-09-05:** `app/services/research_lab/borrow_cost.py`
  provides a cited free approximation — 34 bps/yr general collateral
  (Beneish/Lee/Nichols 2015 p.15, DCBS=1), 430 bps/yr hard-to-borrow
  (D'Avolio 2002 Table 3, specials value-weighted mean), assigned by
  short-interest decile with **both** tails charged the high rate (the
  U-shape D'Avolio Fig. 1 and BLN p.5 both document). It is a **schedule**,
  not a feed, and it does not close this gap.
* **Bias direction of the 0.0 stand-in:** flatters every short leg, worst
  exactly where the short leg is deliberately built from heavily-shorted
  names.
* **What the schedule charges the two LIVE registrations, now measured
  rather than bracketed** (both are decisions still waiting on the repo
  owner; neither was adopted, because `financing_bps_per_year` is in
  `config_identity()` and any non-zero value parks the row as `spec_drift`):

  | registration | short-side tail share | schedule rate | `financing_bps_per_year` | Sharpe cost | still clears the 0.50 floor at every N? |
  |---|---|---|---|---|---|
  | `lazy_prices_jaccard_full/lazy_jaccard_full_h126_ivol` | 0.1710 | 96.33 bp/yr | 48.16 | 0.7456 → 0.5251 | **no** (0.4740 / 0.4329 pooled) |
  | `short_interest_ratio/si_ratio_hedged_h21` | 0.1590 | 89.54 bp/yr | 44.77 | 0.4161 → 0.3233 | **yes** (0.6339 / 0.6212 pooled) |

  Reports: `lazy_prices_borrow_composition_2026-09-05.txt`,
  `short_interest_borrow_composition_2026-09-05.txt`. The no-tilt reference
  is 0.20 tail share / 113.2 bp/yr, so **both** live registrations sit
  slightly BELOW a borrow-blind draw — including the one `borrow_cost.py`
  names as where the zero bites hardest, because that sentence is about
  short_interest's `long_short` specs and the registered one is
  `long_universe_hedged`. Those six unregistered `long_short` specs are the
  genuinely exposed books: `si_ratio_ls_*` measures a tail share of exactly
  1.0000 → 430 bp/yr → `financing_bps_per_year` 215.0, which is the
  schedule's worst case reached exactly rather than approximately.
* **Bias direction of the new schedule:** overcharges. BLN p.17: *"even in
  the highest SIR decile, less than 30 percent of the stocks are special"*,
  so charging a whole decile the specials rate prices ~70% of it too high.
  Intended: it replaces a zero.
* **What would close it:** S&P Global / IHS Markit Securities Finance, S3
  Partners, or EquiLend/DataLend historical rates. None has a free tier
  carrying history.
* **Repo evidence:** `cross_sectional_commodities.py:560`,
  `cross_sectional_bonds.py:414`, `borrow_cost.py` module docstring.

### P2 — Delisted-securities price history

* **Missing:** prices for names that left the index by failure, acquisition
  or downgrade and that yfinance no longer serves.
* **Stand-in:** those tickers simply resolve no data and drop out.
* **Bias direction:** flatters, in the ordinary survivorship direction.
  `cross_sectional_index_removal.py:308-313` names ENDP and DO as identified
  cases that *"kept FALLING after removal rather than rebounding, so their
  absence flatters this family"*. `cross_sectional_seasonality.py:231` reports
  *"143 of the point-in-time universe's tickers resolved no price data at
  all"*.
* **What would close it:** Norgate, CRSP, or Sharadar — the three vendors
  `cross_sectional_index_removal.py:313` already names.
* **Status note:** an earlier "resolved free via Alpaca" claim did not hold
  up on re-check; Alpaca helps and is not a closed fix.

### P3 — Country-index book-to-market (BE/ME)

* **Missing:** MSCI country-index BE/ME, the source measure for the country
  value/momentum family.
* **Stand-in:** a declared deviation, stated in the code itself —
  `cross_sectional_country_valmom.py:409`: *"country-index BE/ME measure (a
  paid dataset this project cannot obtain) — DECLARED DEVIATION"*.
* **Bias direction:** unknown; it is a different measure, not a degraded one.
* **What would close it:** an MSCI index-fundamentals subscription.
* **Repo evidence:** `cross_sectional_country_valmom.py:67` and `:409`,
  `data/research_runs/candidate_sourcing_2026-09-04.txt:122`.

---

## HOW TO ADD AN ENTRY

Only when the gap is real and demonstrated. Give: what is missing, the
stand-in **with the file:line that implements it**, which direction the
stand-in biases results, and what specific product would close it. An entry
with no repo evidence line does not belong here — put it in the run report
where it was discovered and cross-reference that instead.

Per this project's standing rule, hitting one of these mid-build is logged
here and **not** escalated as an interrupt; the whole list is resurfaced
together before any go-live decision.
