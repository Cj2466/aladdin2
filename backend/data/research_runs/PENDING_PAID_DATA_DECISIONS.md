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
* **New evidence, 2026-09-06 (IPO lockup-expiration candidate feasibility
  scoping):** measured directly rather than assumed, on this project's own
  `YFinanceProvider`. Every one of 6 independently-verified real delisted/
  acquired IPO companies (LinkedIn, Fitbit, Zynga, Pandora Media, The
  Container Store, Cloudera) returned ZERO price rows around their OWN
  historical lockup-expiration window — a 0% hit rate on the
  highest-confidence "known bad" set. An unbiased, systematically-sampled
  (not cherry-picked) set of 37 ordinary 2012-2019 IPOs hit at 40.5%.
  Split empirically by "does this ticker resolve to any data in the last 30
  days": 64.3% historical hit rate for the "still trading" bucket vs. 10.7%
  for the "not" bucket — the clearest quantified survivorship-bias
  signature measured yet for this gap.
* **New failure mode found the same day, WORSE than plain missingness
  because it is silent:** ticker recycling/renaming. Facebook's own 2012
  IPO ticker "FB" was confirmed live, via `yfinance.Ticker("FB").info`, to
  now resolve to an entirely unrelated security (ProShares S&P 500 Dynamic
  Daily Buffer ETF, an ETF) after Meta's 2022 rename freed the symbol;
  Pandora Media's own ticker "P" now resolves to an unrelated company
  (Everpure, Inc.). A naive "is this ticker still resolvable" check would
  say YES for both — wrongly attributing a third party's current existence
  to the original company. This means the P2 stand-in's own bias
  description ("those tickers simply resolve no data and drop out") is
  INCOMPLETE: a recycled or renamed ticker does not just drop out, it can
  silently return a plausible-looking but wrong answer. Any family that
  checks "is this ticker alive today" as a proxy for data availability
  (rather than directly querying the target historical window, as this
  run did) inherits this risk.
* **Partial counter-evidence, same run:** delisted-name coverage is real
  but INCONSISTENT, not a clean always-missing rule. Two acquired/merged
  companies (Foundation Medicine, acquired by Roche 2018; Hortonworks,
  merged into Cloudera 2019) correctly returned real, plausible historical
  prices for their own old lockup windows despite independently-confirmed
  non-live status today — Yahoo appears to retain some delisted archives
  and fully purge others, unpredictably from outside.
* **Repo evidence:** `data/research_runs/run_ipo_lockup_feasibility.py`,
  `data/research_runs/ipo_lockup_feasibility_2026-09-06.txt` (Q3 section),
  `data/research_runs/ipo_lockup_samples/section_c_price_availability_summary.json`.

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

### P4 — Roll-adjusted continuous futures prices

* **Missing:** individual-contract or properly roll-adjusted continuous
  futures price history, for the equity-index / government-bond / currency /
  commodity contracts a TSMOM (time-series momentum) family would need.
* **Stand-in as of 2026-09-05:** none in use — **and this entry exists to
  keep it that way.** The obvious stand-in, Yahoo's `=F` tickers reachable
  through the yfinance library this project already uses
  (`app/services/market_data/yfinance_provider.py`), was measured and
  rejected. It is a raw, unadjusted front-month splice, proven three
  independent ways in
  `data/research_runs/tsmom_futures_feasibility_2026-09-05.txt`:
  `CL=F` carries the real **-37.63** print of 2020-04-20 (no back-adjusted
  series can); `ES=F` is byte-equal to `ESU26.CME` on all 54 trading days
  from 2026-06-22 and differs before; and the switch itself injects a
  one-day return nobody earned (**+0.83 pct pts** ES, **+1.50** NQ).
* **Bias direction of that rejected stand-in — the reason this is a P-level
  entry and not a footnote:** it is **not** a conservative substitute, and
  it does **not** average away. Measured across all 764 candidate roll dates
  in the `ESU26`/`ESZ26` overlap the injected artifact was positive on
  **764 of 764** (mean **+0.78 pct pts**). It is also **undetectable**: on
  the roll date the splice's return had robust |z| 0.65 against the true
  return's 0.70 — the fabricated day is the *less* remarkable of the two, so
  no outlier filter, winsorisation or jump screen can find it. Per MOP
  (2012) §6.3 the series is the **spot** price path with the roll return
  omitted, so it can manufacture a false positive as easily as a false
  negative. That is this project's stated worst outcome.
* **Why this project cannot self-build the fix for free:** Yahoo purges
  expired contracts. Over 2015–2026, 3 of 48 ES quarterly contract months
  and 3 of 72 GC contract months resolve at all, and the count of genuinely
  *expired* ones carrying usable history is **zero** in both. There is no
  historical front-month chain to rebuild. (A *forward* collection
  programme, recording front-month contracts from today onward, would work
  and yields no history now.)
* **Two further measured defects in the free series**, each alone enough to
  void a 12-month-lookback backtest in that market for a year: `CL=F` goes
  negative in April 2020, so a return series is undefined there; `6J=F`
  carries a **10x one-day scale break** on 2001-12-17 (0.007923 → 0.000783 →
  0.007860, implying −90.0% then +903.8%).
* **What would close it:** **Norgate Data — Futures package, USD 270/12
  months** (USD 148.50/6 months), price read from
  `norgatedata.com/futurespackage.php` 2026-09-05: ~100 markets across 11
  exchange groups, history to ~1980 or first trading day, supplied as
  **both** unadjusted and back-adjusted spot-month continuous contracts with
  a stated roll rule. **Buy-side caveat, recorded so it is not discovered
  afterwards:** Norgate's back-adjustment "is calculated arithmetically" —
  the Panama/difference form, which destroys percentage returns (demonstrated
  numerically in `run_tsmom_futures_feasibility.py`'s synthetic fixture and
  its tests). The **unadjusted** series, chained per MOP (2012) §2.1, is the
  thing to use. Alternative: Databento (licensed CME distributor, USD 125
  sign-up credit, CME plans reported from USD 179/mo) — correct but a
  recurring subscription. Interactive Brokers' API is free *with a funded
  account*, which is itself a paid decision and was not tested.
* **What is already built and does NOT need buying:** the construction and
  its validation. `run_tsmom_futures_feasibility.py` implements MOP (2012)
  §2.1 verbatim, proves ratio back-adjustment exactly equivalent to it and
  arithmetic/Panama adjustment not equivalent, and validates all of it
  against a synthetic case whose every answer is derivable by hand
  (`tests/test_tsmom_futures_feasibility.py`). The blocker is data alone.
* **Repo evidence:** `data/research_runs/run_tsmom_futures_feasibility.py`
  module docstring (PROOF_1/2/3, DEFECT_A/B),
  `data/research_runs/tsmom_futures_feasibility_2026-09-05.txt`,
  `app/services/market_data/price_store.py:681` (`drop_implausible`, which
  would silently discard `CL=F`'s negative rows if futures were routed
  through this project's own provider — futures are **not** currently
  ingested anywhere, and this is why they should not be until that is
  addressed).

### P5 — Reference data for Lou (2012) Table II column 7's partial scaling factor

* **Missing:** two per-fund, per-quarter portfolio-average inputs that Lou
  (2012) Eq.(3)'s own stated PSF specification needs, neither of which is
  reconstructible from Form N-PORT plus this project's free data:
  1. **Portfolio-average ownership share** — the fund's holding of each
     security divided by that security's shares outstanding, averaged over the
     fund's WHOLE portfolio. N-PORT gives the numerator for every position, but
     the denominator needs shares outstanding for every security a fund holds,
     including foreign equities, unlisted issues and non-equity instruments,
     keyed by CUSIP/ISIN/LEI. This project's
     `app/services/market_data/sec_shares_outstanding_provider.py` covers US
     SEC registrants only, via `dei:EntityCommonStockSharesOutstanding`.
  2. **Portfolio-average effective bid-ask spread**, and specifically the one
     Lou names — Table II's own note, verbatim: "the effective half bid-ask
     spread estimated from the Basic Market-Adjusted model as described in
     Hasbrouck (2006, 2009)". This project implements a DIFFERENT estimator
     (Ardia-Guidotti-Kroencke EDGE,
     `app/services/research_lab/spread_estimator.py`), whose own module
     docstring records that it is unreliable as a LEVEL for post-2005 large
     caps — which is exactly what column 7's -51.076 level loading consumes.
* **Stand-in as of 2026-09-05:** Lou's UNIVARIATE partial scaling factors,
  Table II columns 1 and 5 (0.970 outflow / 0.618 inflow), in
  `app/services/research_lab/cross_sectional_nport_flow.py`
  (`LOU_PUBLISHED_PSF`). The author himself sanctions the substitution,
  footnote 9, verbatim: "The main results of the paper are not sensitive to the
  particular choice of PSF. Using specifications in other columns of Table II
  yields similar return patterns."
* **Bias direction:** unknown in sign and small in expected magnitude. The
  univariate PSF is a two-valued constant while column 7's varies by fund, so
  the stand-in removes cross-fund dispersion in the scaling factor. On Lou's
  own evidence that dispersion does not change his return patterns; on this
  project's sample it is untested, which is why the run carries the
  perfect-scaling (PSF == 1) and own-panel re-estimated PSFs as pre-declared
  sensitivity arms rather than asserting the choice is immaterial.
* **What would close it:** a global security master with shares outstanding by
  identifier (Compustat Global / Refinitiv / FactSet reference data), plus
  either TAQ (for a directly measured effective spread) or an implementation of
  Hasbrouck's Gibbs-sampler estimator on daily CRSP prices — the last of which
  is code, not a purchase, and is the cheaper half.
* **Repo evidence:**
  `app/services/research_lab/cross_sectional_nport_flow.py` module docstring
  section 4, `data/research_runs/nport_flow_fit_PREREGISTRATION.txt` section 5,
  `app/services/research_lab/spread_estimator.py` (the KNOWN LIMITATION block
  on EDGE's large-cap level bias).

### P6 — Historical option open-interest-by-strike-and-expiration, and the trade/participant-classified data Bollen-Whaley (2004) / Barbon-Buraschi (2021) actually use

* **Missing:** two distinct things, kept separate because they close different
  gaps:
  1. A **historical** archive of option open interest by strike and
     expiration (any depth) — needed to backtest a GEX-style dealer-gamma
     proxy at all. Free sources checked are all LIVE-SNAPSHOT-ONLY: yfinance's
     historical/expired-contract chains return zero rows (reproduced live,
     `data/research_runs/options_gamma_feasibility_2026-09-06.txt` Q2/Q3);
     Alpaca's `/v2/options/contracts` returns only the current
     `open_interest`/`open_interest_date`, no history; Alpaca's separate
     historical-bars product only reaches back to Feb 2024 and does not carry
     OI. OCC's own free batch page could not be reached from this environment
     (403/404 behind what looks like Cloudflare) — UNVERIFIED-FROM-HERE, not
     confirmed unavailable.
  2. The **sign-identification** data Bollen-Whaley's Net Buying Pressure and
     Barbon-Buraschi's Gamma Imbalance actually use — trade-vs-quote-midpoint
     classification (Bollen-Whaley) or broker-dealer-vs-customer volume from
     ISE/GEMX/PHLX exchange licenses (Barbon-Buraschi, their own Eq.(1),
     `p.12`) — which free open-interest data cannot supply at all, at any
     price checked. A free build is a DIFFERENT construction (the
     ASSUMED-sign "GEX" heuristic), not a degraded version of either paper's
     measure.
* **Stand-in as of 2026-09-06:** none in use — no family module reads
  options data at all yet (verified: `grep` for `option_chain`/`openInterest`
  across `app/` returned zero hits before this run). This entry exists to
  keep it that way until a deliberate choice is made.
* **Bias direction:** not applicable yet — nothing is built. The risk named
  is prospective: an assumed-sign GEX proxy substituted for either paper's
  actual, directly-observed dealer-side measure would be presented as
  stronger mechanism-fidelity evidence than it is, unless explicitly logged
  as a deviation per CLAUDE.md Section 4.
* **What would close gap 1 (historical archive):** CBOE DataShop's "Option
  EOD Summary" (`datashop.cboe.com/option-eod-summary`) — a real, self-serve,
  cart-based product, by-strike/expiration open interest back to January
  2012, Greeks sold as an optional add-on. Exact price NOT obtained: the cart
  shows no total until specific symbols/date ranges are selected, so no
  single honest headline figure can be quoted here (unlike Norgate's ~$270/yr
  for TSMOM, P4).
* **What would close gap 2 (sign-identification data):** OptionMetrics
  IvyDB, the source both cited papers actually used for daily OI/greeks
  merged with exchange-provided participant-type volume. Confirmed
  (WebSearch: WRDS/Wharton, Imperial College London, Princeton University
  Library all listed as ACCESS POINTS, none as a public price list)
  institutional/university-subscription-only — no individually-purchasable
  tier found anywhere in this search, a materially harder barrier than a
  self-serve consumer product. The broker-dealer-vs-customer participant-type
  volume itself (ISE/GEMX/PHLX) is not evidently sold at any price: even
  Barbon & Buraschi's own paper (footnote 8, p.10-11) states they were "in
  the process of obtaining additional data from the CBOE C1 exchange"
  directly, at the time of writing, to extend coverage past 10-20% — i.e.
  a direct exchange relationship, not a subscription product.
* **Repo evidence:** `data/research_runs/run_options_gamma_feasibility.py`
  module docstring and probe functions (`probe_yfinance_expired_contracts`,
  `probe_alpaca_options_contracts`, `probe_occ_daily_open_interest_endpoint`),
  `data/research_runs/options_gamma_feasibility_2026-09-06.txt` (full
  citations and live-probe evidence), real captured samples under
  `data/research_runs/options_gamma_samples/`.

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
