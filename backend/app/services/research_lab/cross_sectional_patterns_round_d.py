"""Round D: LPS-intraday-only — the 6 intraday-component Lou, Polk & Skouras
(2019) variants (3 lookbacks {21, 63, 252} x 2 holds {21, 63}), as a
DOCUMENTED SUBSET of Round C's already-computed results, not a freshly
re-screened family.

WHY THIS SUBSET IS INTERESTING: a real, independently-replicated finding
from 2026-08-26's work, across all 12 LPS variants and both legs (24 cells,
52,096 real observations) — the 12 intraday-component cells were 12/12
correctly-signed (weight-vs-forward-return correlation) while the 12
overnight-component cells were only 7/12, and this replicated exactly on a
fresh, independent out-of-sample data pull.

THIS MODULE WAS ORIGINALLY BUILT WITH A DEDICATED SCREENING FUNCTION
(`run_round_d_screening`) THAT COMPUTED A FRESH DSR CORRECTION UNDER
n_trials=6. That design was reviewed and rejected on 2026-08-26 as a form of
improper post-hoc trial-count reduction ("trial-count laundering"), for a
reason worth spelling out precisely because it does NOT look like ordinary
cherry-picking:

  The 12-vs-7 structural split was itself discovered by analyzing outcomes
  already computed on Round C's original 30-definition family (n_trials=30).
  The selection criterion (intraday vs overnight component type) is
  structural, not a raw-Sharpe cherry-pick — some intraday-component
  patterns included in the split had near-zero/negative Sharpe, so this is
  not "keep only the winners." But the mechanism insight that motivated
  narrowing to these 6 was still extracted from the SAME data the fresh
  screening would then re-test. Treating that narrower group's DSR as if it
  came from a clean n_trials=6 search — as `run_round_d_screening` did —
  understates the real number of implicit comparisons: the true search that
  produced this 6-pattern hypothesis was "try slicing Round C's 30 patterns
  by every plausible structural axis and see which axis best separates
  correctly-signed from incorrectly-signed cells," which has a much larger
  effective trial count than 6, even though only one axis (component type)
  is the one being reported. This is subtler than performance-based
  cherry-picking but has the same effect: a corrected-looking Sharpe that is
  not actually corrected for the search that produced the hypothesis.

TWO HONEST PATHS EXIST, laid out so this isn't rediscovered from scratch:

  (a) Don't shrink n_trials below what already exists. These 6 patterns
      already have valid, honest DSR verdicts from Round C's n_trials=30
      screening (see cross_sectional_patterns.ROUND_C_FAMILY /
      run_round_c_screening) — that is Round C's real number of trials and
      stays the final, correct word on these 6 patterns' statistical
      significance. `select_intraday_only_from_round_c` below implements
      this path: it filters Round C's own already-computed results down to
      these 6 pattern_ids, changing nothing about their DSR numbers.

  (b) Genuine forward-validation. Extend the existing pairs/momentum
      ForwardValidationRegistration walk-forward mechanism (see
      forward_validation_service.py / forward_validation_runner.py) to
      cross-sectional strategies, and test the intraday-only hypothesis on
      real future-only data that this analysis never touched. This is the
      only way to test the hypothesis with a genuinely fresh, small
      n_trials=6 — the trial count is only honest on data the hypothesis
      wasn't formed from. Not built as of 2026-08-26 (cross-sectional
      strategies have no forward-validation registration path yet) — a real
      future track, not attempted here.

This module ships only path (a). It does not run a new screening, does not
compute a new DSR, and does not touch price data or the network.
"""

from app.services.research_lab.cross_sectional import CrossSectionalScreeningResult, CrossSectionalSpec
from app.services.research_lab.cross_sectional_patterns import (
    LPS_CITATION,
    LPS_HOLDING_DAYS,
    LPS_LOOKBACK_DAYS,
    signal_component_persistence,
)

# The exact, fixed set of pattern_ids this module is about — a documentation
# / filtering aid only. Building this list does NOT constitute running a
# screening or computing a DSR correction; see module docstring.
from functools import partial as _partial


def _build_lps_intraday_only_pattern_ids() -> list[CrossSectionalSpec]:
    """Rebuilds the same 6 spec objects Round C already screens (identical
    pattern_id, signal_fn, and every other field) purely so this module can
    name/filter by them without importing Round C's full 30-spec family.
    These specs are never passed to screen_cross_sectional_universe from
    this module — see module docstring for why."""
    specs: list[CrossSectionalSpec] = []
    for lookback in LPS_LOOKBACK_DAYS:
        for horizon in LPS_HOLDING_DAYS:
            specs.append(
                CrossSectionalSpec(
                    pattern_id=f"lps_intraday_l{lookback}_h{horizon}",
                    family="lps_intraday_only",
                    citation=LPS_CITATION,
                    signal_fn=_partial(
                        signal_component_persistence, component="intraday", lookback_days=lookback
                    ),
                    lookback_days=lookback + 1,
                    holding_days=horizon,
                    portfolio="long_short",
                    rank_fraction=0.1,
                    requires_open=True,
                )
            )
    assert len(specs) == 6, f"expected exactly 6 LPS intraday-component definitions, got {len(specs)}"
    assert len({s.pattern_id for s in specs}) == len(specs), "pattern_ids must be unique"
    return specs


ROUND_D_LPS_INTRADAY_FAMILY: list[CrossSectionalSpec] = _build_lps_intraday_only_pattern_ids()

LPS_INTRADAY_ONLY_PATTERN_IDS: frozenset[str] = frozenset(s.pattern_id for s in ROUND_D_LPS_INTRADAY_FAMILY)


def select_intraday_only_from_round_c(
    round_c_results: list[CrossSectionalScreeningResult],
) -> list[CrossSectionalScreeningResult]:
    """Filters Round C's own already-computed screening results (produced
    under Round C's real, honest n_trials=30 family — see
    cross_sectional_patterns.run_round_c_screening) down to just the 6
    intraday-component LPS patterns.

    Returns the matching results COMPLETELY UNCHANGED: their
    deflated_sharpe.n_trials is still 30, sigma_sr_annualized is still
    computed from all 30 siblings, dsr is still Round C's own verdict. This
    function performs no recomputation and touches no price data — it is a
    pure filter, specifically so it CANNOT manufacture a smaller n_trials
    for this subset. See module docstring for why a fresh n_trials=6 pass
    was rejected.
    """
    return [r for r in round_c_results if r.pattern_id in LPS_INTRADAY_ONLY_PATTERN_IDS]
