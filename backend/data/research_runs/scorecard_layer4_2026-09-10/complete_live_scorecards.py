"""Complete the four live-registration scorecards — layer 4, the power block,
verdict, decision — from the drafts in scorecard_drafts_2026-09-10/ (layers 1-3
already filled), validate each with the real parser, and write it where the
completeness test looks: data/research_runs/scorecards/<family>_SCORECARD.json.

    ./venv/bin/python data/research_runs/scorecard_layer4_2026-09-10/complete_live_scorecards.py

EVERY NUMBER BELOW IS MEASURED AND PERSISTED, with its run_tag or artifact:
  cost scenarios  — cross_sectional_trial_results rows (run_tags named per
                    scenario), short_interest_borrow_composition_2026-09-05.txt,
                    cost_scenarios_2026-09-10.json in this directory
  capacity        — trailing-252-row (365 for crypto) median daily dollar
                    volume from the shared price store to 2026-09-08
  regime coverage — registration_scorecard.regimes_covered_by
  power           — dsr_power.dsr_power_report on the persisted sigma_sr /
                    skew / kurtosis of the canonical row, recomputed here
  preservation    — preservation_score_2026-09-03.json (three families) and
                    preservation_score_crypto_2026-09-10.json (crypto)

THE ONE BAR USED FOR EVERY VERDICT IS 0.95, this project's validated-edge bar.
Two of the four pre-registrations state it; the other two families never
pre-declared a numeric bar and the registration files use the 0.50
forward-registration screening floor as their SELECTION criterion. A verdict
against 0.50 would read as a pass of a floor, so the cards judge against
0.95 and record, in the rationale, how each spec stands against 0.50.

Nothing here reads or writes a live registration row (CLAUDE.md rule 6).
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_BACKEND))

from app.services.research_lab.dsr_power import dsr_power_report
from app.services.research_lab.registration_scorecard import (
    parse_scorecard,
    policy_d_verdict,
    regimes_covered_by,
)

DRAFTS = _BACKEND / "data" / "research_runs" / "scorecard_drafts_2026-09-10"
OUT = _BACKEND / "data" / "research_runs" / "scorecards"
HERE = Path(__file__).resolve().parent
TODAY = "2026-09-10"
BAR = 0.95
PARTICIPATION = 0.01

AUTHOR = (
    "layers 1 and provenance assembled mechanically by a Sonnet sub-agent 2026-09-09 "
    "(build_scorecard_drafts.py); layers 2-3 by the Fable 5.1 main session 2026-09-10 from the "
    "source papers (apply_layer_2_3_review.py); layer 4, power, verdict and decision by the same "
    "session the same day from measured, persisted runs (complete_live_scorecards.py)"
)

# ---------------------------------------------------------------------------
# per-family content
# ---------------------------------------------------------------------------

DRIFT_NOTE_CBOP = (
    "REPRODUCIBILITY, measured 2026-09-10: re-screening this family with the canonical config does "
    "NOT reproduce run_tag quality_build_2026-08-28 — the registered spec moves -0.0027 Sharpe, "
    "siblings up to -0.0900 (cbop_ls_h252_quintile). Controlled replays (scorecard_layer4_2026-09-10/): "
    "(1) rolling the companyfacts documents back to 2026-08-28 through the fact store restores "
    "cbop_ls_h252 exactly and most of the long-hold movement — the 2026-09-09 document refresh is "
    "that part; (2) the remaining -0.027/-0.040 on the three hedged specs and -0.017 on cbop_ls_h63 is "
    "NEITHER the price store (a throw-away store fetched fresh from the vendor reproduces the shared "
    "store to 0.0009) NOR the 2026-09-04 dividend-convention change (0.0003). It lies in inputs no "
    "08-28 snapshot exists for — vendor data between 08-28 and the 09-04 freeze, or companyfacts "
    "content that left the documents before their 09-09 version — and cannot be separated further. "
    "That is the defect class the point-in-time stores now prevent going forward and could not undo "
    "backward. Every cost scenario below is therefore read against a SAME-DAY baseline "
    "(scorecard_cost_scenarios_2026-09-10_quality_cbop_baseline_5bp, cbop_ls_h63 +0.453786), not "
    "against the canonical row."
)

FAMILIES: dict[str, dict] = {
    "quality_cbop": {
        "preregistration_path": (
            "NONE — no pre-registration document exists for this family. The registration decision "
            "and its reasoning are a post-hoc record: app/services/research_lab/"
            "quality_forward_registration.py (written after the backtest, 2026-08-30)."
        ),
        "threshold_source": (
            "0.95 is this project's validated-edge bar (registration_scorecard.py). The family never "
            "pre-declared a numeric bar; its own docstring section 5 judges against 'this project's "
            "bar' and calls the result 'no validated edge'. The 0.50 figure quality_forward_registration.py "
            "cites is the forward-registration SCREENING floor that selected this spec, cleared at every "
            "ladder rung (0.8174 / 0.7288 / 0.6118 / 0.5609) — recorded in the rationale, not used as the "
            "verdict bar."
        ),
        "power": {
            "claimed": 8.5 / (606**0.5) * (12**0.5),
            "source": (
                "Ball, Gerakos, Linnainmaa & Nikolaev working paper (17 Apr 2015) Table 4: the "
                "high-minus-low DECILE cash-based-operating-profitability strategy's three-factor alpha "
                "carries t = 8.5 over July 1963 - December 2013 (606 months); annualized Sharpe taken as "
                "t / sqrt(606) x sqrt(12) = 1.196. GROSS of costs, value-weighted, NYSE breakpoints over "
                "the whole market — an upper bound for this ~68-name, magnitude-weighted, quarterly "
                "construction on all three counts, used deliberately as the generous claimed effect. "
                "Not from a pre-registration (none exists); from the paper the family cites."
            ),
        },
        "cost_scenarios": [
            {
                "name": "as registered (canonical 2026-08-28 inputs; 5 bp flat one-way, no financing)",
                "one_way_bps": 5.0,
                "source": (
                    "run_tag quality_build_2026-08-28, the row the registration was made on; live "
                    "yfinance prices (pre-store) and the 2026-08-28 companyfacts documents. Not "
                    "reproducible today — see the rationale's reproducibility note."
                ),
                "best_spec_net_sharpe": 0.45652867,
            },
            {
                "name": "same-day baseline (5 bp flat, no financing) — the reference for the arms below",
                "one_way_bps": 5.0,
                "source": "run_tag scorecard_cost_scenarios_2026-09-10_quality_cbop_baseline_5bp",
                "best_spec_net_sharpe": 0.453786,
            },
            {
                "name": "corrected EDGE large-cap half-spread (2 bp one-way) — the optimistic bound",
                "one_way_bps": 2.0,
                "source": (
                    "run_tag scorecard_cost_scenarios_2026-09-10_quality_cbop_trading_2bp; 2.00 bp is the "
                    "pooled median one-way half-spread of the corrected EDGE frame on the S&P 500 panel "
                    "(edge_cost_correction_2026-09-05.txt), corroborated by Hagstromer JFE 2021 Table 1"
                ),
                "best_spec_net_sharpe": 0.456495,
            },
            {
                "name": "2x stress (10 bp one-way)",
                "one_way_bps": 10.0,
                "source": "run_tag scorecard_cost_scenarios_2026-09-10_quality_cbop_trading_10bp; a stress, not a prediction",
                "best_spec_net_sharpe": 0.449268,
            },
            {
                "name": "5 bp + general-collateral borrow bracket (17 bp/yr on gross = 34 bp/yr on the short leg)",
                "one_way_bps": 5.0,
                "source": (
                    "run_tag scorecard_cost_scenarios_2026-09-10_quality_cbop_financing_gc_17bp; the GC "
                    "bracket borrow_cost offers. NOT a measurement for this book: cbop's short leg was "
                    "never measured the way short_interest's and lazy_prices' were (2026-09-05). The as-run "
                    "financing is 0.0, the standing disclosed optimism."
                ),
                "best_spec_net_sharpe": 0.442709,
            },
        ],
        "capacity": {
            "adv": 330_063_015.0,
            "n_names": 7,
            "method": (
                "median trailing-252-row daily dollar volume (close x volume) across the 164 live-priced "
                "names of the family's own seeded 200-ticker sample, to 2026-09-08, from the shared price "
                "store; x 1% participation cap x 7 names per leg (persisted avg_names_per_leg 6.775). Per "
                "leg; the long_short book has two. Informational only — no capital is deployed."
            ),
        },
        "window": (date(2015, 1, 7), date(2026, 8, 27)),
        "regime_statement": (
            "The 2015-2026 window covers the COVID crash and the 2022 rate-hike bear market and misses "
            "the GFC and the dot-com bust entirely. A profitability premium is the kind of factor whose "
            "worst episodes in the source's own sample (attenuation from ~2004, BGLN section 4.1) fall "
            "OUTSIDE this window, so the backward result has seen neither a prolonged factor drawdown nor "
            "a credit crisis. Informational; it does not change the negative verdict."
        ),
        "decision": "REGISTERED",
        "decision_rationale": (
            "Registered 2026-08-30 for OBSERVATIONAL forward validation only (no capital, real or paper): "
            "the best of 9 pre-declared specs by DSR, clearing the 0.50 screening floor at every ladder "
            "rung (0.8174 at n=9, 0.7288 at 43, 0.6118 at 397, 0.5609 at 1131) but nowhere near the 0.95 "
            "validated-edge bar, which is the family's own verdict ('no validated edge'). The layer-2 review "
            "(2026-09-10) found every quoted formula and statistic verbatim in the paper, and that what the "
            "spec tests — quarterly reformation, filing-date availability, magnitude-weighted deciles on ~68 "
            "names, 2015-2026 — is a construction the paper does not report, so a positive forward result "
            "would be evidence about this construction, not a replication of Table 4. Layer 4: the cost "
            "range moves the Sharpe by at most 0.014 across 2-10 bp and a GC borrow bracket, so the verdict "
            "is not cost-sensitive; capacity ~$23M per leg at 1% participation. Power: the paper's own "
            "decile-strategy effect (t = 8.5 over 606 months) would have been detected with 96% power "
            "in this sample even against the 0.95 bar, so the failure to reach it is informative, not a "
            "power artefact. " + DRIFT_NOTE_CBOP + " Status changes remain the owner's (rule 6)."
        ),
        "preservation_note_extra": "",
    },
    "short_interest_ratio": {
        "preregistration_path": "data/research_runs/short_interest_PREREGISTRATION.txt",
        "threshold_source": (
            "Pre-registration section 5 (committed f091c7c before any result): 'the best spec's deflated "
            "Sharpe (DSR, n_trials = 12) clears 0.95'."
        ),
        "power": None,
        "power_absent_reason": (
            "No claimed Sharpe can be honestly stated: the source's full text was not obtained (at build "
            "or at review) and its abstract reports no Sharpe or t-statistic; the pre-registration states "
            "no expected effect size. A power number seeded from a second-hand figure would be exactly the "
            "invented precision this block exists to prevent."
        ),
        "cost_scenarios": [
            {
                "name": "as registered (5 bp flat one-way, financing 0.0; live yfinance prices)",
                "one_way_bps": 5.0,
                "source": "run_tag short_interest_build_2026-09-02, the row the registration was made on",
                "best_spec_net_sharpe": 0.4531,
            },
            {
                "name": "pinned snapshot baseline (5 bp flat, financing 0.0)",
                "one_way_bps": 5.0,
                "source": (
                    "short_interest_borrow_composition_2026-09-05.txt 'baseline (LIVE config, financing "
                    "0.0)' arm on the frozen price snapshot of section 8 (module docstring); the basis for "
                    "the three financing arms below, which differ from it ONLY in financing_bps_per_year"
                ),
                "best_spec_net_sharpe": 0.4161,
            },
            {
                "name": "5 bp + general-collateral bracket (17 bp/yr on gross = 34 bp/yr on the short side)",
                "one_way_bps": 5.0,
                "source": "short_interest_borrow_composition_2026-09-05.txt, GC bracket arm",
                "best_spec_net_sharpe": 0.3809,
            },
            {
                "name": "5 bp + MEASURED borrow for this hedged book (44.7705 bp/yr on gross) — THE LIVE CONFIG since 2026-09-06",
                "one_way_bps": 5.0,
                "source": (
                    "short_interest_borrow_composition_2026-09-05.txt: borrow_cost.BorrowSchedule run over "
                    "the registered spec's own realized short side, 89.5410 bp/yr on that side = 44.7705 on "
                    "gross; adopted on the owner's sign-off 2026-09-06 (SHORT_INTEREST_FINANCING_BPS_PER_YEAR)"
                ),
                "best_spec_net_sharpe": 0.3233,
            },
            {
                "name": "5 bp + the family's long_short-book borrow (215.0 bp/yr) — stress, not this spec's book",
                "one_way_bps": 5.0,
                "source": (
                    "short_interest_borrow_composition_2026-09-05.txt: the rate measured for the family's "
                    "long_short books, which short the MOST heavily shorted names; this hedged spec shorts "
                    "the equal-weighted universe, so this is the wrong book — shown as the ceiling"
                ),
                "best_spec_net_sharpe": -0.0298,
            },
        ],
        "capacity": {
            "adv": 347_774_539.0,
            "n_names": 21,
            "method": (
                "median trailing-252-row daily dollar volume (close x volume) across the 501 live-priced "
                "names of the S&P 500 screening universe to 2026-09-08, from the shared price store; x 1% "
                "participation x 21 names in the ranked long leg (persisted avg_names_per_leg 20.57). The "
                "hedge side is the equal-weighted universe and is not the binding leg. Informational only."
            ),
        },
        "window": (date(2018, 1, 12), date(2026, 9, 1)),
        "regime_statement": (
            "The 2018-2026 window covers the COVID crash and the 2022 rate-hike bear market and misses the "
            "GFC and the dot-com bust. For a short-interest signal the missing episode that matters is a "
            "credit crisis with a short-sale ban (2008), during which the paper's mechanism could not have "
            "operated normally; nothing in this window resembles it. Informational."
        ),
        "decision": "REGISTERED",
        "decision_rationale": (
            "Registered 2026-09-02 for OBSERVATIONAL forward validation only, and deliberately NOT the "
            "family's best spec: the top five specs are days-to-cover, whose long leg sits at the 72.7th "
            "percentile of volume and only the 33.2nd of the short-interest ratio — a volume sort wearing a "
            "short-interest label. si_ratio_hedged_h21 is the paper's own measure x its long-side reading x "
            "its monthly cadence, the most pre-specified cell of the grid, and it FAILS the pre-registered "
            "bar (DSR 0.7962 at n=12 against 0.95; 0.7463 / 0.6680 / 0.6340 at the pooled rungs). The "
            "family's verdict is an honest negative and stands. Layer 2 is UNVERIFIABLE: the paper's full "
            "text could not be obtained, every construction choice is second-hand, and the paper's headline "
            "'heavily traded' conditioning is not replicated. Layer 4: the measured borrow for this hedged "
            "book, adopted 2026-09-06, costs 0.093 Sharpe (0.4161 -> 0.3233 on the pinned snapshot); "
            "capacity ~$73M in the long leg at 1% participation. Power: not stated — no honest claimed "
            "effect exists (see the power block's absence note). Status changes remain the owner's (rule 6)."
        ),
        "preservation_note_extra": "",
    },
    "lazy_prices_jaccard_full": {
        "preregistration_path": "data/research_runs/lazy_prices_2026-09-01_preregistration.txt",
        "threshold_source": (
            "Pre-registration section 8 (written 2026-09-01 before any run): 'at least one spec with "
            "sharpe_annualized > 0 AND dsr >= 0.95'."
        ),
        "power": {
            "claimed": 3.59 / (240**0.5) * (12**0.5),
            "source": (
                "Cohen, Malloy & Nguyen, NBER w25084 introduction p. 3 / Table II: the value-weighted "
                "non-changers-minus-changers portfolio earns 'up to 58 basis points per month (t=3.59)' "
                "over 1995-2014 (240 months); annualized Sharpe taken as t / sqrt(240) x sqrt(12) = 0.803. "
                "GROSS, value-weighted, on the universe of all U.S. filers with 10-K AND 10-Q — an upper "
                "bound for this S&P-500, 10-K-only, inverse-vol construction, used deliberately as the "
                "generous claimed effect. The pre-registration quotes this figure (section 1) but states "
                "no expected Sharpe of its own."
            ),
        },
        "cost_scenarios": [
            {
                "name": "as registered (raw EDGE half-spread frame, median 24.41 bp one-way; financing 0.0; live yfinance prices)",
                "one_way_bps": 24.41,
                "source": "run_tag lazy_prices_2026-09-01, the row the registration was made on",
                "best_spec_net_sharpe": 0.6035,
            },
            {
                "name": "raw EDGE frame on the frozen price snapshot (the 'before' of the 2026-09-05 correction)",
                "one_way_bps": 24.41,
                "source": "run_tag edge_cost_correction_2026-09-05_control_raw_edge (= cost_basis_switch_2026-09-05_before_raw_edge)",
                "best_spec_net_sharpe": 0.5946,
            },
            {
                "name": "calibrated EDGE frame (median 2.00 bp one-way), financing 0.0",
                "one_way_bps": 2.0,
                "source": (
                    "run_tag edge_cost_correction_2026-09-05_calibrated_spread: sign=True truncation, "
                    "one-tick floor, level pinned to Hagstromer JFE 2021 Table 1 (edge_cost_correction_2026-09-05.txt)"
                ),
                "best_spec_net_sharpe": 0.7456,
            },
            {
                "name": "calibrated + general-collateral borrow bracket (17 bp/yr on gross)",
                "one_way_bps": 2.0,
                "source": "run_tag edge_cost_correction_2026-09-05_calibrated_plus_gc_borrow",
                "best_spec_net_sharpe": 0.6677,
            },
            {
                "name": "calibrated + MEASURED borrow for this book (48.1644 bp/yr on gross) — THE LIVE CONFIG since 2026-09-06",
                "one_way_bps": 2.0,
                "source": (
                    "run_tag cost_basis_switch_2026-09-05_after_calibrated_measured_borrow; borrow_cost."
                    "BorrowSchedule over the registered spec's own realized short side "
                    "(lazy_prices_borrow_composition_2026-09-05); adopted on the owner's sign-off 2026-09-06"
                ),
                "best_spec_net_sharpe": 0.5251,
            },
            {
                "name": "calibrated + hard-to-borrow bracket (the ceiling, not this book)",
                "one_way_bps": 2.0,
                "source": "run_tag edge_cost_correction_2026-09-05_calibrated_plus_htb_borrow",
                "best_spec_net_sharpe": -0.2376,
            },
        ],
        "capacity": {
            "adv": 347_774_539.0,
            "n_names": 88,
            "method": (
                "median trailing-252-row daily dollar volume across the 501 live-priced names of the S&P "
                "500 screening universe to 2026-09-08, from the shared price store; x 1% participation x "
                "88 names per leg (persisted avg_names_per_leg 87.67, quintile legs). Per leg. Informational."
            ),
        },
        "window": (date(2015, 1, 7), date(2026, 8, 31)),
        "regime_statement": (
            "The 2015-2026 window covers the COVID crash and the 2022 rate-hike bear market and misses the "
            "GFC and the dot-com bust. The paper's own sample (1995-2014) contains both; this window "
            "contains neither, so nothing here says how an inattention effect behaves through a prolonged "
            "crisis. Informational."
        ),
        "decision": "REGISTERED",
        "decision_rationale": (
            "Registered 2026-09-03 for OBSERVATIONAL forward validation only: the family's top-DSR spec, "
            "registered as is because — unlike short_interest's days-to-cover — it is one of the paper's own "
            "measures on the paper's own base scope. It FAILS the pre-registered bar (DSR 0.7540 at n=36 "
            "against 0.95; 0.7396 / 0.5614 / 0.4835 pooled) and the family's verdict is an honest negative. "
            "Layer 2 (2026-09-10) verified every quotation; deviations: stop words removed (the paper's "
            "robustness variant, not its base case), 10-K only, 6-month hold, inverse-vol weighting, S&P 500 "
            "2015-2026. Two economic facts carried onto the card: the paper puts the return in the SHORT leg "
            "(Figure 7), and the family's own 2026-09-03 correction found a vocabulary-size ceiling that "
            "explains ~half of Jaccard's variance and 49% of the short leg (orthogonalising it costs 22% of "
            "the Sharpe). Layer 4: the cost ladder spans 0.7456 (calibrated spread, no borrow) to 0.5251 "
            "(the live config with measured borrow) to -0.2376 (hard-to-borrow ceiling) — the borrow on the "
            "leg that carries the return is the economics of this family; capacity ~$306M per leg at 1%. "
            "Power: against the 0.95 bar this sample has only ~39% power to detect the paper's own "
            "value-weighted effect, so the negative is UNDERPOWERED rather than definite. The registered "
            "DSR disagrees across run_tags (0.7540 canonical vs 0.8639 on the later cost basis) — carried "
            "unresolved. Status changes remain the owner's (rule 6)."
        ),
        "preservation_note_extra": "",
    },
    "cross_sectional_crypto": {
        "preregistration_path": (
            "NONE — no pre-registration document exists. The registration decision is a post-hoc "
            "record: app/services/research_lab/bab_forward_registration.py (2026-08-27; deployed "
            "2026-09-04), with its 2026-09-10 correction appended."
        ),
        "threshold_source": (
            "0.95 is this project's validated-edge bar. bab_forward_registration.py pins NO numeric bar "
            "for this registration — it is an explicit, disclosed exception, forward-tracked despite failing "
            "every standing DSR bar because its backward confound check passed. The card judges against "
            "0.95 and records that the spec also fails the 0.50 screening floor at every rung (0.3553 / "
            "0.2505 / 0.0224 / 0.0055)."
        ),
        "power": {
            "claimed": 0.78,
            "source": (
                "Frazzini & Pedersen, 'Betting Against Beta', 2013 draft p. 4: the U.S. equity BAB factor "
                "'realizes a Sharpe ratio of 0.78 between 1926 and March 2012'. GROSS, beta-neutral by "
                "levering, monthly rebalanced, on U.S. equities — the paper does not cover crypto at all, "
                "so this is the mechanism's own reported effect transplanted, used deliberately as the "
                "generous claimed effect. No pre-registration exists to have stated one."
            ),
        },
        "cost_scenarios": [
            {
                "name": "as registered (30 bp one-way blended; 800 bp/yr spot borrow = 400 on gross)",
                "one_way_bps": 30.0,
                "source": (
                    "run_tag global_effective_n_2026-09-04, the persisted canonical row; reproduced "
                    "EXACTLY by the same-day baseline scorecard_cost_scenarios_2026-09-10_crypto_baseline_30bp"
                ),
                "best_spec_net_sharpe": 0.9437630151,
            },
            {
                "name": "half the blended assumption (15 bp one-way), same borrow",
                "one_way_bps": 15.0,
                "source": "run_tag scorecard_cost_scenarios_2026-09-10_crypto_trading_15bp",
                "best_spec_net_sharpe": 0.9540,
            },
            {
                "name": "double the blended assumption (60 bp one-way) — stress for the thinner alts",
                "one_way_bps": 60.0,
                "source": "run_tag scorecard_cost_scenarios_2026-09-10_crypto_trading_60bp",
                "best_spec_net_sharpe": 0.9232,
            },
            {
                "name": "30 bp, financing 0 — what the 800 bp/yr spot borrow is worth (NOT the perpetual-funding credit the module refuses to book)",
                "one_way_bps": 30.0,
                "source": "run_tag scorecard_cost_scenarios_2026-09-10_crypto_financing_0",
                "best_spec_net_sharpe": 1.0544,
            },
        ],
        "capacity": {
            "adv": 20_331_708.0,
            "n_names": 10,
            "method": (
                "median trailing-365-row daily USD volume (yfinance crypto Volume is already in USD) across "
                "the 66 alive coins of CRYPTO_UNIVERSE excluding BTC and ETH — a quintile leg of this family "
                "is made of alts, not majors — to 2026-09-08, from the shared price store; x 1% participation "
                "x 10 names per leg (persisted avg_names_per_leg 9.75). Per leg. Informational; ~$2M per leg "
                "is the honest number and it is small."
            ),
        },
        "window": (date(2020, 11, 1), date(2026, 8, 25)),
        "regime_statement": (
            "The formation window begins 2020-11-01 — after the COVID crash — and covers only the 2022 "
            "rate-hike bear market (which in crypto was the Terra/FTX collapse year, present in the data "
            "with LUNA1 priced all the way down). It has seen no equity-style credit crisis and, more to the "
            "point for a funding-liquidity mechanism, no episode of the funding-constraint tightening "
            "Frazzini-Pedersen's prediction (3) is about, which this family does not test. Informational."
        ),
        "decision": "REGISTERED",
        "decision_rationale": (
            "Registered 2026-08-27 (deployed 2026-09-04) for OBSERVATIONAL forward validation only, as an "
            "explicit, disclosed EXCEPTION: DSR 0.3553 at n=28 fails every bar this project uses, including "
            "the 0.50 screening floor at every rung, and was forward-tracked because its backward confound "
            "check passed (BTC beta 0.0572, alpha t 2.68 net of BTC and the equal-weighted basket). The "
            "layer-2 review (2026-09-10) found three defects in the registration's own text, corrected by "
            "appended note: 'BTC as market proxy per Liu-Tsyvinski-Wu' is a wrong attribution (their market "
            "factor is a value-weighted coin index); LTW's own beta quintile sorts are INSIGNIFICANT, "
            "negative evidence recorded nowhere in the family; and 'held up under a regime split' has no "
            "committed definition or artifact. Construction deviates from Frazzini-Pedersen on the beta "
            "estimator, the median split, rank weights, beta-neutral levering and monthly rebalance, and the "
            "paper does not cover crypto. Layer 4: the trading-cost range moves the Sharpe by 0.03 across "
            "15-60 bp; the spot borrow is worth 0.11; capacity ~$2M per leg at 1% participation — small. "
            "Power: against the 0.95 bar this sample has ~1% power to detect FP's own U.S. equity BAB "
            "Sharpe of 0.78 (sigma_sr 0.515 across 28 siblings on a 365-day calendar), so the negative is "
            "UNDERPOWERED rather than definite — the test could not have seen the effect if it were there. preservation_score "
            "measured 2026-09-10 from a replay that reproduces the persisted row exactly. Status changes "
            "remain the owner's (rule 6)."
        ),
        "preservation": {
            "score": 0.1504653369444808,
            "no_stab": 0.16606713415852967,
            "note": (
                "computed 2026-09-10 by scorecard_layer4_2026-09-10/run_crypto_preservation_score.py, which "
                "replays the family's own run_crypto_screening through the capture hook of "
                "run_preservation_score.py and scores on the family's 365-day calendar; the rebuilt Sharpe "
                "matches run_tag global_effective_n_2026-09-04 to 0.0 (sharpe_delta_vs_persisted = 0.0); "
                "rerun DSR 0.3552701584 at n_trials 28. Artifact: preservation_score_crypto_2026-09-10.json."
            ),
        },
        "preservation_note_extra": "",
    },
}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for family_key, spec in FAMILIES.items():
        draft = json.loads((DRAFTS / f"{family_key}_SCORECARD_DRAFT.json").read_text())
        l1 = draft["layer_1_statistical"]

        # --- layer 1 completion --------------------------------------------
        l1["dsr_pass_threshold"] = BAR
        l1["dsr_pass_threshold_source"] = spec["threshold_source"]
        if "preservation" in spec:
            l1["preservation_score"] = spec["preservation"]["score"]
            l1["preservation_score_no_stab"] = spec["preservation"]["no_stab"]
            l1["preservation_inputs_note"] = spec["preservation"]["note"]
        dsr_by_n = {int(k): v for k, v in l1["dsr_by_n"].items()}
        n_local = int(l1["n_local"])
        power_at_claimed = None
        if spec["power"] is None:
            l1["power"] = None
            l1["power_absent_reason"] = spec["power_absent_reason"]
        else:
            ds = draft["provenance"]
            # sigma_sr / skew / kurt of the canonical row, as the draft generator used them
            stats = spec.get("stats") or _canonical_stats(family_key)
            report = dsr_power_report(
                claimed_sharpe_annualized=spec["power"]["claimed"],
                threshold=BAR,
                n_observations=int(l1["n_observations"]),
                n_trials=n_local,
                sigma_sr_annualized=stats["sigma_sr_annualized"],
                periods_per_year=float(l1["periods_per_year"]),
                # the validator recomputes with dsr_power_report's DEFAULT skew/kurtosis
                # (0 / 3); the block must state exactly the inputs it will be checked on
            )
            l1["power"] = {
                "claimed_sharpe_annualized": spec["power"]["claimed"],
                "claimed_sharpe_source": spec["power"]["source"],
                "sigma_sr_annualized": stats["sigma_sr_annualized"],
                "periods_per_year": float(l1["periods_per_year"]),
                "required_observed_sharpe": report.required_observed_sharpe,
                "power_at_claimed_sharpe": report.power_at_claimed_sharpe,
                "min_detectable_sharpe": report.min_detectable_sharpe,
                "years_to_detect_claimed": report.years_to_detect_claimed,
                "sigma_sr_source": stats["source"],
                "note": (
                    "power is scored as registration_scorecard recomputes it — dsr_power_report with its "
                    "default skewness 0 and kurtosis 3, i.e. a Gaussian PSR; the canonical row's own skew/"
                    "kurtosis are in its deflated_sharpe block and are NOT used here"
                ),
            }
            power_at_claimed = report.power_at_claimed_sharpe
            del ds
        l1["verdict"] = policy_d_verdict(
            dsr_by_n=dsr_by_n, threshold=BAR, n_local=n_local, power_at_claimed_sharpe=power_at_claimed
        )
        l1.pop("verdict_computed_for_reference_only_NOT_A_SCHEMA_FIELD", None)

        # --- layer 4 ---------------------------------------------------------
        cap = spec["capacity"]
        start, end = spec["window"]
        present, absent = regimes_covered_by(start, end)
        draft["layer_4_economics"] = {
            "cost_scenarios": spec["cost_scenarios"],
            "capacity": {
                "avg_daily_dollar_volume_usd": cap["adv"],
                "participation_cap_fraction": PARTICIPATION,
                "n_names_per_leg": cap["n_names"],
                "capacity_usd": round(cap["adv"] * PARTICIPATION * cap["n_names"], 2),
                "method": cap["method"],
            },
            "regime_coverage": {
                "window_start": start.isoformat(),
                "window_end": end.isoformat(),
                "regimes_present": present,
                "regimes_absent": absent,
                "statement": spec["regime_statement"],
            },
        }

        # --- top level -------------------------------------------------------
        draft["decision"] = spec["decision"]
        draft["decision_rationale"] = spec["decision_rationale"]
        draft["preregistration_path"] = spec["preregistration_path"]
        draft["written_at"] = TODAY
        draft["author"] = AUTHOR
        draft.pop("draft_status", None)
        draft.pop("gaps", None)
        draft["completed_from_draft"] = (
            f"scorecard_drafts_2026-09-10/{family_key}_SCORECARD_DRAFT.json (layers 1-3) + "
            "scorecard_layer4_2026-09-10/complete_live_scorecards.py (layer 4, power, verdict, decision), "
            f"{TODAY}"
        )

        # --- validate with the real parser, then write --------------------
        card = parse_scorecard(draft, source_path=OUT / f"{family_key}_SCORECARD.json")
        (OUT / f"{family_key}_SCORECARD.json").write_text(json.dumps(draft, indent=2, ensure_ascii=False) + "\n")
        print(f"{family_key:26s} verdict={card.layer_1.verdict:18s} decision={card.decision}  "
              f"power={None if card.layer_1.power is None else round(card.layer_1.power.power_at_claimed_sharpe, 3)}  "
              f"capacity=${card.layer_4.capacity.capacity_usd:,.0f}  regimes={card.layer_4.regime_coverage.regimes_present}")
    return 0


def _canonical_stats(family_key: str) -> dict:
    """sigma_sr / skewness / kurtosis of the canonical row, from the DB."""
    import sqlite3

    rows = {
        "quality_cbop": ("quality_cbop", "cbop_ls_h63", "quality_build_2026-08-28"),
        "lazy_prices_jaccard_full": ("lazy_prices", "lazy_jaccard_full_h126_ivol", "lazy_prices_2026-09-01"),
        "cross_sectional_crypto": ("crypto", "xc_btcbeta_l180_h180", "global_effective_n_2026-09-04"),
    }
    fk, tid, tag = rows[family_key]
    db = sqlite3.connect(str(Path("/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend/aladdin2.db")))
    (js,) = db.execute(
        "select full_result_json from cross_sectional_trial_results where family_key=? and trial_id=? and run_tag=?",
        (fk, tid, tag),
    ).fetchone()
    ds = json.loads(js)["deflated_sharpe"]
    return {
        "sigma_sr_annualized": float(ds["sigma_sr_annualized"]),
        "skewness": float(ds["skewness"]),
        "kurtosis": float(ds["kurtosis"]),
        "source": f"deflated_sharpe block of cross_sectional_trial_results row ({fk}/{tid}, run_tag {tag})",
    }


if __name__ == "__main__":
    raise SystemExit(main())
