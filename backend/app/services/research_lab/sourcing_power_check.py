"""A power pre-check run BEFORE a family is built, not after.

WHY THIS MODULE EXISTS. `dsr_power.py` (read its docstring first; this module
calls it and adds no new statistics) computes the power of the DSR gate for a
family that has already been screened -- it needs a realized grid size and
(optionally) realized moments. `letf_rebalancing_eod` was pre-registered with
its own version of this check inline (`data/research_runs/letf_power_block.py`,
committed 2026-09-10 BEFORE any strategy return was computed) and the family
was correctly declared underpowered in advance (power 0.014 at the deciding
50%-of-claim arm, bar 0.95, n_local). That check was written by hand, once,
for one family. This module is the same idea generalised so every future
family gets it automatically at the SOURCING stage -- before a single line of
signal-construction code is written -- rather than depending on each builder
remembering to write a bespoke pre-check script.

THE ARITHMETIC IS NOT NEW. Every power number here comes from
`dsr_power.dsr_power_report` (which itself calls `required_observed_sharpe`,
`power_to_pass`, `years_to_detect` -- see that module's docstring for the
Bailey & Lopez de Prado derivation and its synthetic-data validation in
`tests/test_dsr_power.py`). Nothing in `dsr_power.py` is retyped here. The
gate's own `POWER_FLOOR` (0.80, Cohen 1988's convention) is imported, not
restated, and is the only threshold this module applies -- there is no
separate, sourcing-specific bets-per-year or Sharpe magic number anywhere in
this file.

THE DSR LADDER IS NOT NEW EITHER. `n_local_tier` and `ladder` are obtained by
calling `global_effective_n.dsr_n_trials(n_local)` and then
`dsr_policy_n.dsr_policy_denominators` on the result -- the exact two calls
every family's own `policy_d_denominators()` makes (see
`letf_rebalancing_eod.policy_d_denominators` and
`intraday_momentum_spy.policy_d_denominators`). No rung is hardcoded; the
ladder read here is whatever `dsr_policy_n.json` currently declares, so this
module tracks a future ladder revision automatically.

THE ONE FORMULA THAT *IS* THIS MODULE'S OWN CHOICE: sigma_SR_annualized.
`dsr_power_report` requires a `sigma_sr_annualized` -- the assumed dispersion
of Sharpe ratios across the n_trials grid that feeds
`expected_max_sharpe_under_noise` (Bailey & Lopez de Prado's SR0). At
sourcing time no trial has been run, so there is no realized dispersion to
plug in (contrast `intraday_momentum_spy`, whose run_output.json records a
REALIZED sigma_SR of 0.574 across its 8 built specs -- not available before
the specs exist). `letf_rebalancing_eod`'s own POWER_BLOCK.md section 4
faced exactly this gap and declared, in writing, BEFORE any result existed:

    sigma_SR_annualized = sqrt(periods_per_year / n_observations)

"the null sampling standard error of one annualized Sharpe estimate...this
project's own choice, not a formula from any source paper. It is the
conservative side: correlated specs disperse *less* than independent draws,
and a larger sigma_SR raises the required observed Sharpe, so this can only
*lower* the computed power." (POWER_BLOCK.md section 4; declared-in-advance
sensitivity bounds at sigma_SR=0 and 2x are in the same file's section 5.)
This module reuses that same precedent formula, because it is the project's
only existing answer to "what sigma_SR before any data exists", it was
reasoned through once already, and inventing a second formula here for the
same gap would be exactly the kind of undocumented judgment call CLAUDE.md's
mechanism-fidelity rule exists to prevent. It is cited here as project
precedent (POWER_BLOCK.md / ADDENDUM_01 section 4), not as a result from any
external paper.

CONSEQUENCE FOR REPRODUCING A FAMILY'S OWN REALIZED-sigma_SR POWER NUMBER:
this module's sigma_SR will generally NOT equal a family's post-hoc realized
sigma_SR (see the LETF and intraday_momentum_spy regression tests in
tests/test_sourcing_power_check.py, and the tolerance/divergence notes
there). That is expected, not a bug -- this is a SOURCING-TIME proxy for a
quantity that literally cannot be measured before the grid is built.

WHAT "PROCEED" MEANS AND DOES NOT MEAN. `verdict` is `PROCEED` iff the power
at the SMALLEST of `offset_fractions` (i.e. the most conservative fraction of
the claimed effect that was checked), evaluated at the family's own
`n_local_tier` (the most lenient rung -- CLAUDE.md's family-local N), is at
least `POWER_FLOOR`. Otherwise `DECLINE_AT_SOURCING`. `PROCEED` is not itself
a pass -- it only means this test COULD see the claimed effect if it were
real; the family still has to be built, screened, and cleared through DSR,
preservation_score and mechanism-fidelity review like any other family
(CLAUDE.md section 4). `DECLINE_AT_SOURCING` means the opposite of a
DEFINITE_NEGATIVE: nothing was tested, because the test as scoped could not
have told the difference between "no edge" and "an edge too weak for this
sample to resolve" even under the source literature's own most conservative
claim.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.services.research_lab.dsr_policy_n import dsr_policy_denominators
from app.services.research_lab.dsr_power import (
    POWER_FLOOR,
    DsrPowerReport,
    dsr_power_report,
)
from app.services.research_lab.global_effective_n import dsr_n_trials

PROCEED = "PROCEED"
DECLINE_AT_SOURCING = "DECLINE_AT_SOURCING"


class SourcingPowerCheckError(ValueError):
    """Inputs that cannot yield a sourcing verdict. Raised, never papered
    over -- a silently-defaulted verdict here would be exactly the false
    precision this project's rules exist to prevent."""


@dataclass(frozen=True)
class FractionResult:
    """Everything computed for one fraction of the claimed Sharpe, across
    every rung of the DSR ladder."""

    fraction: float
    claimed_sharpe_annualized: float
    reports_by_n_trials: dict[int, DsrPowerReport]

    def power_at(self, n_trials: int) -> float:
        return self.reports_by_n_trials[n_trials].power_at_claimed_sharpe

    def years_to_detect_at(self, n_trials: int) -> float | None:
        return self.reports_by_n_trials[n_trials].years_to_detect_claimed

    def underpowered_at(self, n_trials: int) -> bool:
        return self.reports_by_n_trials[n_trials].underpowered

    def to_dict(self) -> dict:
        return {
            "fraction": self.fraction,
            "claimed_sharpe_annualized": self.claimed_sharpe_annualized,
            "by_n_trials": {
                str(n): {
                    "power_at_claimed_sharpe": r.power_at_claimed_sharpe,
                    "years_to_detect_claimed": r.years_to_detect_claimed,
                    "required_observed_sharpe": r.required_observed_sharpe,
                    "min_detectable_sharpe": r.min_detectable_sharpe,
                    "underpowered": r.underpowered,
                }
                for n, r in self.reports_by_n_trials.items()
            },
        }


@dataclass(frozen=True)
class SourcingPowerCheckReport:
    """The sourcing-stage bundle. All Sharpe fields are ANNUALIZED, matching
    dsr_power's contract."""

    claimed_sharpe_annualized: float
    periods_per_year: float
    years_of_data: float
    n_observations: int
    n_local: int
    n_local_tier: int
    bar: float
    sigma_sr_annualized: float
    ladder: tuple[int, ...]
    offset_fractions: tuple[float, ...]
    fraction_results: dict[float, FractionResult]
    smallest_fraction: float
    power_at_smallest_fraction_at_n_local: float
    verdict: str

    def summary(self) -> str:
        lines = [
            (
                f"sourcing power pre-check: claimed Sharpe {self.claimed_sharpe_annualized:.4f} "
                f"annualized, {self.periods_per_year:.4f} periods/yr, {self.years_of_data:.4f} years "
                f"-> n_observations={self.n_observations}"
            ),
            (
                f"n_local={self.n_local} -> n_local_tier (dsr_n_trials)={self.n_local_tier}; "
                f"ladder={list(self.ladder)}; bar={self.bar:.2f}; "
                f"sigma_SR_annualized=sqrt(periods_per_year/n_observations)={self.sigma_sr_annualized:.6f} "
                "(project precedent, POWER_BLOCK.md section 4 -- not a source-paper formula)"
            ),
        ]
        for fraction in self.offset_fractions:
            fr = self.fraction_results[fraction]
            lines.append(f"  fraction {fraction:.2f} (claimed Sharpe {fr.claimed_sharpe_annualized:.4f}):")
            for n_trials in self.ladder:
                power = fr.power_at(n_trials)
                yrs = fr.years_to_detect_at(n_trials)
                yrs_s = "n/a" if yrs is None else f"{yrs:.2f}"
                lines.append(
                    f"    N={n_trials}: power={power:.4f} "
                    f"({'UNDERPOWERED' if fr.underpowered_at(n_trials) else 'adequate'} vs floor {POWER_FLOOR:.2f}); "
                    f"years_to_detect={yrs_s}"
                )
        lines.append(
            f"verdict: {self.verdict} (power at smallest fraction {self.smallest_fraction:.2f} "
            f"at n_local_tier {self.n_local_tier} = {self.power_at_smallest_fraction_at_n_local:.4f}, "
            f"floor {POWER_FLOOR:.2f})"
        )
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "claimed_sharpe_annualized": self.claimed_sharpe_annualized,
            "periods_per_year": self.periods_per_year,
            "years_of_data": self.years_of_data,
            "n_observations": self.n_observations,
            "n_local": self.n_local,
            "n_local_tier": self.n_local_tier,
            "bar": self.bar,
            "sigma_sr_annualized": self.sigma_sr_annualized,
            "sigma_sr_formula": "sqrt(periods_per_year / n_observations) -- POWER_BLOCK.md section 4 precedent",
            "ladder": list(self.ladder),
            "offset_fractions": list(self.offset_fractions),
            "fraction_results": {str(f): fr.to_dict() for f, fr in self.fraction_results.items()},
            "smallest_fraction": self.smallest_fraction,
            "power_at_smallest_fraction_at_n_local": self.power_at_smallest_fraction_at_n_local,
            "power_floor": POWER_FLOOR,
            "verdict": self.verdict,
        }


def sourcing_power_check(
    claimed_sharpe_annualized: float,
    periods_per_year: float,
    years_of_data: float,
    n_local: int,
    *,
    bar: float = 0.95,
    offset_fractions: tuple[float, ...] = (1.0, 0.5),
    skewness: float = 0.0,
    kurtosis: float = 3.0,
) -> SourcingPowerCheckReport:
    """Run the pre-build power pre-check for a candidate family.

    claimed_sharpe_annualized: the source literature's claimed effect size
        (annualized Sharpe), net of this project's cost model where the
        source reports gross -- the same contract dsr_power.dsr_power_report
        states for its own `claimed_sharpe_annualized` argument.
    periods_per_year: the sampling frequency the family would screen at.
    years_of_data: calendar years of data actually available for the family.
    n_local: the intended pre-declared grid size (number of specs).
    bar: the DSR threshold this family would be judged against (default 0.95,
        matching every live registration's own bar).
    offset_fractions: fractions of claimed_sharpe_annualized to check power
        at, most lenient first by convention (default: the full claim, then
        half of it -- half is not a magic number here, it mirrors the
        "50%-of-Tuzun" deciding arm letf_rebalancing_eod's own
        pre-registration named as its conservative check, but any caller may
        pass its own fractions from its own source literature).

    Raises SourcingPowerCheckError for invalid inputs, and re-raises
    dsr_power.DsrPowerError unmodified if the bar is unreachable at some
    rung -- that is real information (this test's bar cannot be cleared even
    at Sharpe 10), never papered over into a manufactured power number.
    """
    if not np.isfinite(claimed_sharpe_annualized):
        raise SourcingPowerCheckError(f"claimed_sharpe_annualized must be finite, got {claimed_sharpe_annualized}")
    if not (np.isfinite(periods_per_year) and periods_per_year > 0):
        raise SourcingPowerCheckError(f"periods_per_year must be positive, got {periods_per_year}")
    if not (np.isfinite(years_of_data) and years_of_data > 0):
        raise SourcingPowerCheckError(f"years_of_data must be positive, got {years_of_data}")
    if int(n_local) < 1:
        raise SourcingPowerCheckError(f"n_local={n_local} is not a real grid size")
    if not offset_fractions:
        raise SourcingPowerCheckError("offset_fractions must be non-empty")
    if any(f <= 0 for f in offset_fractions):
        raise SourcingPowerCheckError(f"offset_fractions must all be positive, got {offset_fractions}")

    n_local = int(n_local)
    n_observations = max(3, round(years_of_data * periods_per_year))
    sigma_sr_annualized = float(np.sqrt(periods_per_year / n_observations))

    n_local_tier = dsr_n_trials(n_local)
    ladder = tuple(dsr_policy_denominators(n_local_tier))

    fraction_results: dict[float, FractionResult] = {}
    for fraction in offset_fractions:
        claimed = claimed_sharpe_annualized * fraction
        reports: dict[int, DsrPowerReport] = {}
        for n_trials in ladder:
            reports[n_trials] = dsr_power_report(
                claimed_sharpe_annualized=claimed,
                threshold=bar,
                n_observations=n_observations,
                n_trials=n_trials,
                sigma_sr_annualized=sigma_sr_annualized,
                periods_per_year=periods_per_year,
                skewness=skewness,
                kurtosis=kurtosis,
            )
        fraction_results[fraction] = FractionResult(
            fraction=fraction,
            claimed_sharpe_annualized=claimed,
            reports_by_n_trials=reports,
        )

    smallest_fraction = min(offset_fractions)
    power_at_smallest_fraction_at_n_local = fraction_results[smallest_fraction].power_at(n_local_tier)
    verdict = PROCEED if power_at_smallest_fraction_at_n_local >= POWER_FLOOR else DECLINE_AT_SOURCING

    return SourcingPowerCheckReport(
        claimed_sharpe_annualized=claimed_sharpe_annualized,
        periods_per_year=periods_per_year,
        years_of_data=years_of_data,
        n_observations=n_observations,
        n_local=n_local,
        n_local_tier=n_local_tier,
        bar=bar,
        sigma_sr_annualized=sigma_sr_annualized,
        ladder=ladder,
        offset_fractions=tuple(offset_fractions),
        fraction_results=fraction_results,
        smallest_fraction=smallest_fraction,
        power_at_smallest_fraction_at_n_local=power_at_smallest_fraction_at_n_local,
        verdict=verdict,
    )


__all__ = [
    "DECLINE_AT_SOURCING",
    "PROCEED",
    "FractionResult",
    "SourcingPowerCheckError",
    "SourcingPowerCheckReport",
    "sourcing_power_check",
]
