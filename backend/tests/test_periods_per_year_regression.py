"""THE REGRESSION PROOF for the periods_per_year fix.

WHAT THE FIX WAS. metrics.sharpe_ratio annualized with a hardcoded
sqrt(TRADING_DAYS_PER_YEAR=252), backtest_result.py annualized mean return
with a hardcoded * 252, and deflated_sharpe.compute_deflated_sharpe
de-annualized with the same hardcoded 252. Crypto trades 24/7/365 -- verified
live 2026-08-27 against yfinance: BTC-USD returns 365/365/366/365/365/365/
366/365 rows for 2018..2025 with ZERO missing calendar days, against SPY's
251/252/253/252/251/250/252/250 -- so a 365-row-per-year crypto series was
having its Sharpe understated by sqrt(252/365) (~17%) and its annualized
return understated by 252/365 (~31%), with compute_deflated_sharpe
compounding the same error a second time on the way back down to daily scale.

WHY THIS FILE IS A REGRESSION TEST AND NOT AN ASSERTION. The numbers below
were captured by RUNNING THE PRE-FIX TREE (commit 53b01f6, before any
periods_per_year parameter existed) through tests/_periods_per_year_fixture
.py -- the exact module this test replays. All eight cross-sectional families
that existed before the crypto build are screened end-to-end through the
shared harness on one deterministic panel, and every float the fix could
possibly have moved is pinned: the annualized Sharpe from metrics.sharpe_
ratio, and every field compute_deflated_sharpe derives from it (daily Sharpe,
PSR-vs-zero, DSR, SR0, sigma_SR). 153 specs, 918 floats. A single changed
float in any of them fails this test.

Asserting "the default is still 252" would prove nothing of the kind: the
whole risk of this change was that threading a parameter through five call
sites silently reorders or rescales something. Only replaying the real
families against pre-fix outputs rules that out.
"""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd
import pytest

from app.services.research_lab.deflated_sharpe import compute_deflated_sharpe
from app.services.research_lab.metrics import (
    CALENDAR_DAYS_PER_YEAR,
    TRADING_DAYS_PER_YEAR,
    sharpe_ratio,
)
from app.services.risk.volatility import annualized_volatility
from tests._periods_per_year_fixture import existing_families, screen_family

# (n_specs, sha256[:32] of the family's canonical result repr) -- captured
# from the PRE-FIX tree. See this module's docstring.
PRE_FIX_FAMILY_DIGESTS: dict[str, tuple[int, str]] = {
    "bonds": (18, "ab43b51138c21434888d2813725749f5"),
    "buyback": (14, "fed2169d784519f4e392c8e86558503c"),
    "commodities": (24, "830b7be719a8a3f0e778a6279b1d1f83"),
    "fx": (36, "50c3e52f8f9d7f487e398e5d275742eb"),
    "ivol": (21, "612bc8e848fb75e5b86cfa6ad6818975"),
    "patterns_d2": (4, "d5a0d26c77b1a330ec0ce2bd602e1918"),
    "patterns_round_c": (30, "8bc379ca4aaeddab54c1e0a6ae563996"),
    "patterns_round_d": (6, "d6207fd5ca9efe1fb9cca205355d7caa"),
}

# The single highest-Sharpe spec of each family, written out in full so a
# failure shows a human-readable number and not only a hash mismatch:
# family -> (pattern_id, sharpe_annualized, psr_vs_zero, dsr).
PRE_FIX_SPOT_VALUES: dict[str, tuple[str, float, float, float | None]] = {
    "bonds": ("bonds_butterfly_l63_h252", 0.3176253468254152, 0.8041038634477693, 0.19171584865695424),
    "buyback": ("nsi_l126_hedged_h252", 0.7108741410380696, 0.9703867203332347, 0.715444184824769),
    "commodities": (
        "cmd_blend_m126_r1260_h126_inverse_vol",
        1.2313298016189689,
        0.9746037918490587,
        0.7487105967242016,
    ),
    "fx": ("fx_momentum_l252_h63_inverse_vol", 1.1541516023470353, 0.9664819707109062, 0.4744929072931241),
    "ivol": ("ivol_resid_w252_hedged_h126", -0.3429770644697175, 0.1902891420626655, 0.0900126431746201),
    "patterns_d2": ("d2_reversal_long_universe_hedged_l756", -0.3675334874740222, 0.21683999100414814, None),
    "patterns_round_c": ("cgo_ls_decile_l504_h126", 0.8250123613057417, 0.9711037249057841, 0.384428781976604),
    "patterns_round_d": ("lps_intraday_l252_h21", 0.06326068485549234, 0.5641970378949074, 0.28485585211975273),
}


def _canon(x: float | None) -> str:
    """repr() of a plain Python float, or 'None'. The coercion is
    load-bearing: DeflatedSharpeResult.sharpe_net_daily comes out of a numpy
    division and is an np.float64 whose repr is 'np.float64(0.02)', not
    '0.02' — hashing the raw repr would pin numpy's display convention
    alongside the actual value."""
    return "None" if x is None else repr(float(x))


def _digest(results: dict[str, tuple]) -> str:
    canon = ";".join(
        f"{pid}=" + ",".join(_canon(x) for x in results[pid]) for pid in sorted(results)
    )
    return hashlib.sha256(canon.encode()).hexdigest()[:32]


# --- the regression proof ---------------------------------------------------


@pytest.mark.parametrize("family_name", sorted(PRE_FIX_FAMILY_DIGESTS))
def test_periods_per_year_fix_changes_no_existing_family_number(family_name: str):
    """Byte-for-byte: every one of this family's specs must reproduce the
    exact floats the PRE-FIX tree produced on identical input."""
    specs, config, tickers = existing_families()[family_name]
    # The fix must not have moved any family off the 252-session default.
    assert config.periods_per_year == TRADING_DAYS_PER_YEAR

    results = screen_family(specs, config, tickers)
    expected_n, expected_digest = PRE_FIX_FAMILY_DIGESTS[family_name]

    assert len(results) == expected_n, (
        f"{family_name}: {len(results)} specs produced results, pre-fix it was {expected_n} — "
        "the fix changed WHICH specs survive the data floors, not just their numbers."
    )
    assert _digest(results) == expected_digest, (
        f"{family_name}: at least one of the {expected_n} specs' Sharpe/PSR/DSR/SR0/sigma_SR "
        "floats differs from the value the pre-fix tree produced on identical input. The "
        "periods_per_year change was required to be a no-op for every non-crypto family."
    )


@pytest.mark.parametrize("family_name", sorted(PRE_FIX_SPOT_VALUES))
def test_pre_fix_spot_values_reproduce_exactly(family_name: str):
    """The same proof at human-readable resolution: one named spec per
    family, with its literal pre-fix numbers."""
    specs, config, tickers = existing_families()[family_name]
    results = screen_family(specs, config, tickers)
    pattern_id, sharpe, psr, dsr = PRE_FIX_SPOT_VALUES[family_name]

    assert pattern_id in results, f"{family_name}: {pattern_id} no longer produces a result"
    got_sharpe, _daily, got_psr, got_dsr, _sr0, _sigma = results[pattern_id]
    assert got_sharpe == sharpe
    assert got_psr == psr
    assert got_dsr == dsr


# --- the parameter itself ---------------------------------------------------


def test_sharpe_ratio_default_is_the_252_session_year():
    returns = pd.Series([0.01, -0.004, 0.006, 0.002, -0.001, 0.008])
    assert sharpe_ratio(returns) == sharpe_ratio(returns, periods_per_year=TRADING_DAYS_PER_YEAR)
    assert sharpe_ratio(returns) == sharpe_ratio(returns, periods_per_year=252)


def test_sharpe_ratio_scales_as_sqrt_of_periods_per_year():
    """The exact size of the bug: a 365-day-a-year series annualized at 252
    is understated by sqrt(252/365)."""
    returns = pd.Series([0.01, -0.004, 0.006, 0.002, -0.001, 0.008, 0.003, -0.002])
    at_252 = sharpe_ratio(returns, periods_per_year=252)
    at_365 = sharpe_ratio(returns, periods_per_year=CALENDAR_DAYS_PER_YEAR)
    assert at_252 == pytest.approx(at_365 * np.sqrt(252.0 / 365.0))
    # The headline number from the bug report: ~17% understated.
    assert at_252 / at_365 == pytest.approx(0.8311, abs=5e-4)


def test_sharpe_ratio_periods_per_year_is_keyword_only():
    """Positional would let an existing caller silently pass something else
    into it. TypeError is the intended contract."""
    with pytest.raises(TypeError):
        sharpe_ratio(pd.Series([0.01, 0.02, -0.01]), 365)  # type: ignore[misc]


def test_annualized_volatility_default_is_unchanged_and_scales_correctly():
    returns = pd.Series([0.01, -0.004, 0.006, 0.002, -0.001, 0.008])
    assert annualized_volatility(returns) == annualized_volatility(returns, periods_per_year=252)
    assert annualized_volatility(returns, periods_per_year=365) == pytest.approx(
        annualized_volatility(returns) * np.sqrt(365.0 / 252.0)
    )


def test_compute_deflated_sharpe_default_matches_explicit_252():
    rng = np.random.default_rng(7)
    returns = pd.Series(rng.normal(0.0004, 0.01, size=800))
    a = compute_deflated_sharpe(0.9, returns, 28, 0.4)
    b = compute_deflated_sharpe(0.9, returns, 28, 0.4, periods_per_year=252)
    assert (a.sharpe_net_daily, a.psr_vs_zero, a.dsr, a.expected_max_sharpe_noise_annualized) == (
        b.sharpe_net_daily,
        b.psr_vs_zero,
        b.dsr,
        b.expected_max_sharpe_noise_annualized,
    )


def test_compute_deflated_sharpe_de_annualizes_with_the_supplied_year_length():
    """The compounding half of the bug: at a fixed ANNUALIZED Sharpe, a
    larger periods_per_year means a smaller per-period Sharpe, and SR0 must
    be re-annualized with the same figure it was de-annualized by."""
    rng = np.random.default_rng(11)
    returns = pd.Series(rng.normal(0.0004, 0.01, size=800))
    at_252 = compute_deflated_sharpe(0.9, returns, 28, 0.4, periods_per_year=252)
    at_365 = compute_deflated_sharpe(0.9, returns, 28, 0.4, periods_per_year=365)

    assert at_365.sharpe_net_daily == pytest.approx(0.9 / np.sqrt(365.0))
    assert at_252.sharpe_net_daily == pytest.approx(0.9 / np.sqrt(252.0))
    assert at_365.sharpe_net_daily < at_252.sharpe_net_daily
    # SR0 round-trips through the same year length, so the ANNUALIZED
    # benchmark is scale-invariant even though the daily one is not.
    assert at_365.expected_max_sharpe_noise_annualized == pytest.approx(
        at_252.expected_max_sharpe_noise_annualized
    )
    # A lower per-period point estimate against the same n means less
    # confidence -- the direction that makes the 252-on-crypto error a
    # FLATTERING one for DSR, not merely a rescaling.
    assert at_365.psr_vs_zero < at_252.psr_vs_zero


def test_deflated_sharpe_helpers_stay_unit_agnostic():
    """probabilistic_sharpe_ratio and expected_max_sharpe_under_noise
    deliberately take NO periods_per_year — they never convert scales, and a
    no-op parameter there would imply a conversion that does not happen. If
    someone adds one, this test is the place that argument gets re-made."""
    import inspect

    from app.services.research_lab import deflated_sharpe as ds

    assert "periods_per_year" not in inspect.signature(ds.probabilistic_sharpe_ratio).parameters
    assert "periods_per_year" not in inspect.signature(ds.expected_max_sharpe_under_noise).parameters
    assert "periods_per_year" in inspect.signature(ds.compute_deflated_sharpe).parameters


def test_module_level_trading_days_constant_is_untouched():
    """deflated_sharpe.py and sharpe_robustness.py import this constant
    directly; changing it (rather than threading a parameter) would have
    silently moved every number they produce."""
    from app.services.research_lab import deflated_sharpe as ds
    from app.services.research_lab import sharpe_robustness as sr

    assert TRADING_DAYS_PER_YEAR == 252
    assert ds.TRADING_DAYS_PER_YEAR == 252
    assert sr.TRADING_DAYS_PER_YEAR == 252
    assert CALENDAR_DAYS_PER_YEAR == 365
