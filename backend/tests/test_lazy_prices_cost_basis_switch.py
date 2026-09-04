"""THE 2026-09-05 SWITCH OF lazy_prices_jaccard_full's COST BASIS, PINNED.

WHAT WAS SWITCHED. The live registration's edge_spread cost basis moved from
spread_estimator.build_edge_half_spread_frame (documented as ~19x too
expensive on this family's own real panel) to
build_calibrated_half_spread_frame, at both call sites at once.

WHY THIS FILE EXISTS RATHER THAN A COMMENT. The switch has two properties
that are load-bearing and invisible to every other test in the suite, and a
future edit could quietly break either:

  1. IT MUST NOT MOVE config_fingerprint. The half-spread frame is DATA the
     adapter builds, and cost_model is not one of config_identity()'s
     fields, so the live row keeps ticking across the change. If that ever
     stops being true, the runner's drift gate parks the registration as
     "spec_drift" on its very next tick and the forward clock stops for good.
  2. THE TWO CALL SITES MUST NOT DIVERGE. The backtest path
     (run_lazy_prices_screening) and the live forward tick
     (build_lazy_prices_live_panel) have to charge the same cost, or the
     backward reference number and the forward record stop being comparable.
     They now share one function; this pins that they still do.

AND ONE THING THAT WAS DELIBERATELY *NOT* SWITCHED, pinned for the same
reason: financing_bps_per_year stays 0.0. Not because 0.0 is right — it is
known-wrong, and borrow_cost.py exists because of that — but because it IS
in config_identity, so adopting any borrow rate parks the registration.
test_any_non_zero_borrow_rate_would_park_this_registration is the executable
form of that argument, so nobody has to take it on trust.
"""

import numpy as np
import pandas as pd
import pytest

from app.services.cross_sectional_forward_validation_service import detect_config_drift
from app.services.research_lab.cross_sectional import CrossSectionalConfig
from app.services.research_lab.cross_sectional_forward_registry import (
    config_fingerprint,
    config_identity,
)
from app.services.research_lab.cross_sectional_lazy_prices import (
    build_lazy_prices_half_spread_frame,
    default_lazy_prices_config,
)
from app.services.research_lab.spread_estimator import (
    SP500_TARGET_MEDIAN_HALF_SPREAD,
    build_calibrated_half_spread_frame,
    build_edge_half_spread_frame,
)

# The fingerprint the LIVE row was registered under on 2026-09-03, read off
# cross_sectional_forward_validation_registrations directly rather than
# recomputed from the same code this test is checking. A change here is not a
# test to update — it is the forward clock stopping.
REGISTERED_CONFIG_FINGERPRINT = (
    "2dccbf932bfda8605e2f89ede56c501cc41dfb44ca8e876a99e6385e2dd06e2c"
)


def _roll_model_ohlc(n_days: int = 300, n_tickers: int = 12, half_spread: float = 0.0010):
    """OHLC with a REAL bid-ask bounce: an efficient GBM price observed
    through a half-spread that flips between bid and ask independently at
    each open and each close (Roll 1984). This is the microstructure EDGE is
    built to recover; a bare GBM path with fixed high/low bands carries none
    and makes every estimate non-positive."""
    tickers = [f"T{i:02d}" for i in range(n_tickers)]
    dates = pd.bdate_range(end=pd.Timestamp("2026-08-31"), periods=n_days)
    rng = np.random.default_rng(20260905)
    efficient = pd.DataFrame(
        {t: 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.012, n_days))) for t in tickers},
        index=dates,
    )
    q_close = pd.DataFrame(rng.choice([-1.0, 1.0], efficient.shape), index=dates, columns=tickers)
    q_open = pd.DataFrame(rng.choice([-1.0, 1.0], efficient.shape), index=dates, columns=tickers)
    return (
        efficient.shift(1).bfill() * (1.0 + half_spread * q_open),
        efficient * 1.008 * (1.0 + half_spread),
        efficient * 0.992 * (1.0 - half_spread),
        efficient * (1.0 + half_spread * q_close),
    )


# --- 1: the switch must not stop the forward clock ---------------------------


def test_the_switch_did_not_move_the_registered_config_fingerprint():
    """The whole reason this switch was enactable at all. If this fails, the
    live registration parks as spec_drift on its next tick."""
    assert config_fingerprint(default_lazy_prices_config()) == REGISTERED_CONFIG_FINGERPRINT


def test_cost_model_is_not_part_of_the_config_identity():
    """The structural fact the switch rests on, asserted rather than assumed:
    swapping the half-spread frame is invisible to the fingerprint because
    the frame is data, not config."""
    identity = config_identity(default_lazy_prices_config())
    assert "cost_model" not in identity
    assert config_fingerprint(CrossSectionalConfig(cost_model="edge_spread")) == config_fingerprint(
        CrossSectionalConfig(cost_model="flat_bps")
    )


def test_any_non_zero_borrow_rate_would_park_this_registration():
    """WHY THE BORROW COST WAS NOT ADOPTED IN THE SAME CHANGE, as an
    executable argument rather than a claim in a docstring.

    financing_bps_per_year IS in config_identity. Every candidate rate the
    2026-09-05 correction bracketed — general collateral (17.0 on gross), the
    measured schedule rate for this family's own short leg (48.16), and the
    worst-case specials bracket (215.0) — re-hashes the fingerprint, and
    detect_config_drift then returns a reason, which is what makes the runner
    call _park_as_drifted. That is an operational-status change, and status
    is the repo owner's decision, never a side effect of a cost fix."""
    registered = default_lazy_prices_config()
    assert registered.financing_bps_per_year == 0.0

    class _Row:
        config_fingerprint = REGISTERED_CONFIG_FINGERPRINT
        family_key = "lazy_prices_jaccard_full"
        started_at = "2026-09-03"
        config_snapshot_json = "{}"

    for rate in (17.0, 48.1644, 215.0):
        drifted = CrossSectionalConfig(cost_model="edge_spread", financing_bps_per_year=rate)
        assert config_fingerprint(drifted) != REGISTERED_CONFIG_FINGERPRINT
        assert (
            detect_config_drift(_Row(), config_fingerprint(drifted), config_identity(drifted))
            is not None
        ), f"financing_bps_per_year={rate} must be detected as config drift"


# --- 2: the two call sites must charge the same thing ------------------------


def test_the_backtest_and_the_live_tick_share_one_half_spread_builder():
    """Both paths must route through the family's own builder. Two direct
    calls to the estimator in two files is the shape that lets a half-fix
    ship, and is what this switch replaced."""
    import inspect

    from app.services.research_lab import cross_sectional_forward_registry as registry
    from app.services.research_lab import cross_sectional_lazy_prices as family

    live = inspect.getsource(registry.build_lazy_prices_live_panel)
    backtest = inspect.getsource(family.run_lazy_prices_screening)
    for name, source in (("live tick", live), ("backtest", backtest)):
        assert "build_lazy_prices_half_spread_frame" in source, f"{name} bypasses the builder"
        assert "build_edge_half_spread_frame(" not in source, (
            f"{name} still calls the raw estimator directly"
        )


def test_the_family_builder_returns_the_calibrated_frame_not_the_raw_one():
    open_, high, low, close = _roll_model_ohlc()
    produced = build_lazy_prices_half_spread_frame(open_, high, low, close)
    expected, _report = build_calibrated_half_spread_frame(open_, high, low, close)
    pd.testing.assert_frame_equal(produced, expected)

    raw = build_edge_half_spread_frame(open_, high, low, close)
    # Same shape and alignment contract — it is a drop-in replacement — but a
    # materially different level, which is the entire point of the switch.
    assert produced.shape == raw.shape
    assert produced.index.equals(raw.index) and produced.columns.equals(raw.columns)
    assert not np.allclose(
        np.nanmedian(produced.to_numpy()), np.nanmedian(raw.to_numpy()), rtol=0.1
    )


def test_the_calibrated_basis_is_pinned_to_the_published_level():
    """The level is not estimated from the panel, it is pinned to the sourced
    S&P 500 target. The median charged cell must land on it."""
    open_, high, low, close = _roll_model_ohlc()
    produced = build_lazy_prices_half_spread_frame(open_, high, low, close)
    median = float(np.nanmedian(produced.to_numpy()))
    assert median == pytest.approx(SP500_TARGET_MEDIAN_HALF_SPREAD, rel=1e-9)

    raw_median = float(np.nanmedian(build_edge_half_spread_frame(open_, high, low, close)))
    assert raw_median > median, "the raw frame must be the more expensive one"


def test_calibration_start_reaches_the_underlying_builder():
    """The pooled median that pins the level is taken over the rows the run
    actually forms on, so the argument must not be dropped in the wrapper."""
    open_, high, low, close = _roll_model_ohlc()
    cut = close.index[150].date()
    assert not build_lazy_prices_half_spread_frame(
        open_, high, low, close, calibration_start=cut
    ).equals(build_lazy_prices_half_spread_frame(open_, high, low, close))


# --- 3: a bad data day must be reported, not crashed -------------------------


def test_a_panel_with_no_estimable_spread_is_refused_rather_than_guessed():
    """A GBM path with no bid-ask bounce yields no positive EDGE cell at all.
    There is then nothing to pin a level to, and inventing a scalar would be
    the fabricated number this whole correction removes. Refusing is correct;
    the live adapter translates the refusal into its own documented
    panel-unavailable contract (see build_lazy_prices_live_panel)."""
    dates = pd.bdate_range(end=pd.Timestamp("2026-08-31"), periods=200)
    rng = np.random.default_rng(7)
    close = pd.DataFrame(
        {t: 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.01, len(dates)))) for t in ("A", "B", "C")},
        index=dates,
    )
    with pytest.raises(ValueError, match="no positive EDGE half-spread cell"):
        build_lazy_prices_half_spread_frame(
            close.shift(1).bfill(), close * 1.01, close * 0.99, close
        )


def test_the_live_adapter_translates_that_refusal_into_panel_unavailable():
    from app.services.research_lab import cross_sectional_forward_registry as registry

    source = __import__("inspect").getsource(registry.build_lazy_prices_live_panel)
    assert "CrossSectionalPanelUnavailableError" in source
    assert "except ValueError" in source
