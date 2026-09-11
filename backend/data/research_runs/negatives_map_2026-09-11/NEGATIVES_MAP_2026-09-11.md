# Negatives map — every family_key in FAMILY_INVENTORY.json, 2026-09-11

Companion to `negatives_map.csv`. One row per `family_key` in
`data/research_runs/scorecards/FAMILY_INVENTORY.json` (55 keys, captured
2026-09-10 from `select distinct family_key from cross_sectional_trial_results`
against the shared `backend/aladdin2.db`). Re-queried live for this table
(2026-09-11); the DB group-by now returns 54 distinct family_keys — `nport_flow_fit`
currently has zero rows in `cross_sectional_trial_results` even though it is
in the captured inventory and in `SCORECARD_WAIVERS.json`, so its
`n_observations_proxy`/`best_dsr`/`best_sharpe_annualized` are `unknown (no DB
rows found)`, not zero.

## Sourcing, column by column

- **outcome**: read from, in this priority order — (1) the seven persisted
  scorecards under `data/research_runs/scorecards/*_SCORECARD.json`, via each
  card's `covers_family_keys` list mapping its own filename-key onto the
  DB's family_key spelling (`crypto`->`cross_sectional_crypto`,
  `lazy_prices`->`lazy_prices_jaccard_full`,
  `short_interest`->`short_interest_ratio`; the other four match directly) —
  `decision: REGISTERED` maps to `live-registered`, `decision: DECLINED` maps
  to `DECLINED`; (2) `SCORECARD_WAIVERS.json`'s 31 `family_key` entries, whose
  own stated `reason` is "closed candidate family: no live forward
  registration and not parked in the Dormant pool" for every one of them, so
  waived maps to `DECLINED`; (3) `dormant_pool_manifest.json`'s 16 `entries`
  maps to `Dormant-parked`; (4) `app/services/research_lab/registration_scorecard.py`'s
  `RETIRED_LIVE_REGISTRATION_FAMILY_KEYS = frozenset({"quality_noa_industry_neutral"})`
  maps to `retired`. These four sources partition all 55 keys exactly (7 + 31
  + 16 + 1 = 55) with no leftover and no overlap — checked programmatically,
  not assumed. **Re-check note**: `letf_rebalancing_eod`'s scorecard was read
  twice during this task and changed from `NOT_YET_DECIDED` to `DECLINED`
  between the two reads (file mtime 2026-09-11 12:55:07, i.e. someone finished
  writing it while this task was running in the shared main checkout). The
  table below uses the later, current value.
- **n_observations_proxy**: `max(n_observations)` over that family's rows in
  `cross_sectional_trial_results`, queried directly against
  `backend/aladdin2.db` (read-only `SELECT`, no writes).
- **best_dsr**, **best_sharpe_annualized**: `max(dsr)` / `max(sharpe_annualized)`
  over the same rows, same query.
- **n_trial_rows_in_db**: `count(*)` for that family_key, for context on how
  thin the max-based proxies above are.
- **rebalance_frequency**: a keyword search (`intraday`, `quarterly`,
  `monthly`, `weekly`, `daily`, `calendar-time`, `calendar-anchored`,
  `calendar-driven`, `annual`) over each family module's own docstring
  (`ast.get_docstring` on the mapped file). Three initial hits were false
  positives — `bonds`, `low_frequency_patterns` and `patterns_d2` each
  contained the word "intraday" only in a sentence about a *different*,
  unrelated prior round, not their own frequency — checked by reading the
  surrounding context and corrected to `unknown`. Left `unknown` for every
  family whose docstring did not state a frequency in this vocabulary
  (`unknown` outnumbers every stated value — 30 of 55).
- **cost_sensitivity**, **capacity**: `unknown` for every family except the
  seven with a persisted scorecard, where `layer_4_economics.cost_scenarios`
  (one-way bps range across the scenarios actually persisted) and
  `layer_4_economics.capacity.capacity_usd` (plus its stated method, truncated)
  are read directly from the scorecard JSON. No other family's cost arm or
  capacity claim was chased down for this table — most have no scorecard at
  all, so there is nothing persisted to point at.
- **mechanism_type**: one of `published anomaly` / `flow mechanism` /
  `intraday` / `crypto` / `other`, assigned by reading each module's own
  docstring opening (first ~1500 characters via `ast.get_docstring`) and
  classifying by its own stated framing — explicit "FLOW"/"PRESSURE"/
  "flow-induced" language to `flow mechanism`; "intraday" framing to
  `intraday`; Binance/perpetual-futures/crypto framing to `crypto`; a named
  academic anomaly/paper as the core test to `published anomaly`; a
  meta-combination test (`multi_signal_combination`, `round_c`,
  `phase_a_intraday_expanded`) or a cross-asset timing overlay not obviously
  any of the above (`correlation_risk_premium`, `eigenportfolio_statarb`,
  `vol_regime`) to `other`. **This is a judgment call on which of four labels
  best fits each docstring's own words, not itself a verified fact** — a
  different reader could draw some of these lines differently (e.g.
  `best_ideas_13f` and `index_removal` sit close to the flow/anomaly
  boundary); flagged here rather than presented as settled.
- **module_path**: found by grepping `app/services/research_lab/*.py` for the
  literal `family_key` string and hand-resolving the ambiguous cases (several
  small-cap/re-run variants share their parent module; `patterns_d2` maps to
  `cross_sectional_patterns_d2.py`, which the initial glob filter missed and
  a second pass found).

## Headline counts

**By outcome** (55 total):

| outcome | count |
|---|---|
| DECLINED (includes all 31 waived "closed candidate" families + 3 scorecard DECLINED) | 34 |
| Dormant-parked | 16 |
| live-registered | 4 |
| retired | 1 |

**By mechanism type** (55 total):

| mechanism_type | count |
|---|---|
| published anomaly | 29 |
| flow mechanism | 14 |
| other | 7 |
| crypto | 4 |
| intraday | 1 |

**Outcome x mechanism type**:

| outcome \ mechanism | published anomaly | flow mechanism | crypto | intraday | other |
|---|---|---|---|---|---|
| DECLINED | 15 | 12 | 3 | 1 | 3 |
| Dormant-parked | 10 | 2 | 0 | 0 | 4 |
| live-registered | 3 | 0 | 1 | 0 | 0 |
| retired | 1 | 0 | 0 | 0 | 0 |

**By n_observations_proxy band** (max n_observations across the family's DB
rows; 54 families have a proxy, `nport_flow_fit` is `unknown`):

| band | count |
|---|---|
| <500 | 7 |
| 500-1499 | 2 |
| 1500-2999 | 39 |
| 3000-4999 | 4 |
| >=5000 | 2 |
| unknown | 1 |

**Band x outcome**:

| band \ outcome | DECLINED | Dormant-parked | live-registered | retired |
|---|---|---|---|---|
| <500 | 7 | 0 | 0 | 0 |
| 500-1499 | 2 | 0 | 0 | 0 |
| 1500-2999 | 23 | 11 | 4 | 1 |
| 3000-4999 | 0 | 4 | 0 | 0 |
| >=5000 | 1 | 1 | 0 | 0 |
| unknown | 1 | 0 | 0 | 0 |

## What clusters and what does not — counts only, no interpretation beyond them

- Every one of the 9 families with `n_observations_proxy` under 1,500 (the
  `<500` and `500-1499` bands) is `DECLINED`. None of those 9 is
  `Dormant-parked`, `live-registered`, or `retired`.
- All 4 `live-registered` families and the 1 `retired` family sit in the
  `1500-2999` band. No `live-registered` or `retired` family sits outside it.
- The `3000-4999` band is 4 families, all 4 `Dormant-parked`. The `>=5000`
  band is 2 families, split 1 `DECLINED` / 1 `Dormant-parked`.
- The large majority of families (39 of 55) sit in the `1500-2999` band
  regardless of outcome — `DECLINED` (23), `Dormant-parked` (11),
  `live-registered` (4) and `retired` (1) are all represented there, so that
  band alone does not separate outcomes.
- `published anomaly` is the largest mechanism-type bucket in every outcome
  category (15 of 34 `DECLINED`, 10 of 16 `Dormant-parked`, 3 of 4
  `live-registered`, the 1 `retired`), which mostly reflects that
  `published anomaly` is also the largest bucket overall (29 of 55) rather
  than a mechanism-specific pattern.
- `flow mechanism` families are `DECLINED` in 12 of 14 cases and
  `Dormant-parked` in the other 2; none is `live-registered` or `retired`.
- `crypto` (4 families) splits 3 `DECLINED` / 1 `live-registered`; `intraday`
  (1 family) is `DECLINED`; `other` (7 families) splits 4 `Dormant-parked` /
  3 `DECLINED`.
