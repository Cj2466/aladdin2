"""Shared fixture for the periods_per_year regression proof.

Lives in its own module (not inside the test file) so the SAME code that
captured the golden numbers from the pre-fix tree is the code the test
replays against the post-fix tree -- a golden file captured by one script
and asserted by a differently-written test proves much less.

Everything here is deterministic: one fixed seed, one fixed calendar, one
fixed synthetic panel that supplies EVERY optional CrossSectionalData frame
so that every existing family's specs can be replayed through the shared
harness without any family-specific data plumbing.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.services.research_lab.cross_sectional import (
    CrossSectionalConfig,
    CrossSectionalData,
    CrossSectionalSpec,
    fixed_universe_membership,
)

SEED = 20260827
# 60 tickers so a DECILE spec (rank_fraction 0.1 — the Round C / D1 / D2
# convention) still forms legs of 6, comfortably over the harness's
# DEFAULT_MIN_NAMES_PER_LEG of 5. At 20 tickers every decile family was
# skipped for thin legs and this fixture silently proved nothing about them.
N_TICKERS = 60
N_ROWS = 1900
START = "2015-01-02"

TICKERS: list[str] = [f"T{i:02d}" for i in range(N_TICKERS)]


def deterministic_panel(tickers: list[str] | None = None) -> CrossSectionalData:
    """A seeded geometric-random-walk panel with every optional frame
    populated and exactly aligned. Business-day indexed (equity/bond/FX/
    commodity convention) -- this fixture exists to prove the NON-crypto
    families are unchanged, so it deliberately uses their calendar.

    `tickers` overrides the default synthetic names for the one family whose
    SIGNALS are keyed to real ticker identity (cross_sectional_bonds' fixed
    Treasury ladder); every other family's signals are identity-agnostic and
    use the default T00.. names."""
    names = list(tickers) if tickers is not None else list(TICKERS)
    n_tickers = len(names)
    rng = np.random.default_rng(SEED)
    index = pd.bdate_range(START, periods=N_ROWS)

    drift = rng.normal(0.0002, 0.0003, size=n_tickers)
    vol = rng.uniform(0.008, 0.030, size=n_tickers)
    shocks = rng.normal(0.0, 1.0, size=(N_ROWS, n_tickers))
    market = rng.normal(0.0, 1.0, size=(N_ROWS, 1))
    beta = rng.uniform(0.4, 1.4, size=n_tickers)
    log_returns = drift + vol * (0.6 * market * beta + 0.8 * shocks)
    close = pd.DataFrame(
        100.0 * np.exp(np.cumsum(log_returns, axis=0)), index=index, columns=names
    )

    # price_only_close: the same path minus a steady distribution wedge, so
    # the TR/PX ratio a carry signal reads is a real, non-degenerate number.
    wedge = np.exp(np.cumsum(np.tile(rng.uniform(0.0, 0.00012, size=n_tickers), (N_ROWS, 1)), axis=0))
    price_only_close = close / wedge

    open_ = close * (1.0 + rng.normal(0.0, 0.002, size=(N_ROWS, n_tickers)))
    volume = pd.DataFrame(
        rng.lognormal(14.0, 0.5, size=(N_ROWS, n_tickers)), index=index, columns=names
    )
    # Share counts: a forward-filled STEP series (quarterly changes only),
    # the shape cross_sectional_buyback's signal requires.
    steps = np.repeat(
        np.cumprod(1.0 + rng.normal(-0.002, 0.01, size=(N_ROWS // 63 + 1, n_tickers)), axis=0),
        63,
        axis=0,
    )[:N_ROWS]
    shares = pd.DataFrame(1.0e9 * steps, index=index, columns=names)
    market_cap = shares * price_only_close

    returns = close.pct_change(fill_method=None)
    trailing_vol = returns.rolling(63, min_periods=21).std(ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        leg_weight_basis = (1.0 / trailing_vol).replace([np.inf, -np.inf], np.nan)

    return CrossSectionalData(
        close=close,
        open=pd.DataFrame(open_.to_numpy(), index=index, columns=names),
        volume=volume,
        market_cap=market_cap,
        price_only_close=price_only_close,
        leg_weight_basis=leg_weight_basis,
        shares_outstanding=shares,
    )


def synthetic_rate_differentials() -> pd.DataFrame:
    """Monthly (foreign - USD) differentials keyed by this fixture's tickers
    — the one external input build_fx_family needs."""
    rng = np.random.default_rng(SEED + 1)
    months = pd.date_range("2014-01-31", periods=150, freq="ME")
    return pd.DataFrame(
        rng.normal(0.0, 0.015, size=(len(months), N_TICKERS)), index=months, columns=TICKERS
    )


def existing_families() -> dict[str, tuple[list[CrossSectionalSpec], CrossSectionalConfig, list[str]]]:
    """Every cross-sectional family that existed BEFORE the crypto build,
    paired with its own production config. Imported lazily so a failure in
    one family module names itself instead of breaking collection."""
    from app.services.research_lab import (
        cross_sectional_bonds as bonds,
    )
    from app.services.research_lab import (
        cross_sectional_buyback as buyback,
    )
    from app.services.research_lab import (
        cross_sectional_commodities as commodities,
    )
    from app.services.research_lab import (
        cross_sectional_fx as fx,
    )
    from app.services.research_lab import (
        cross_sectional_ivol as ivol,
    )
    from app.services.research_lab import (
        cross_sectional_patterns as patterns,
    )
    from app.services.research_lab import (
        cross_sectional_patterns_d2 as d2,
    )
    from app.services.research_lab import (
        cross_sectional_patterns_round_d as round_d,
    )

    fx_config = CrossSectionalConfig(
        cost_bps=fx.FX_SPREAD_BPS_ONE_WAY,
        financing_bps_per_year=fx.FX_FINANCING_BPS_PER_YEAR,
        min_names_per_leg=fx.FX_MIN_NAMES_PER_LEG,
    )
    default = list(TICKERS)
    return {
        "bonds": (list(bonds.BONDS_FAMILY), bonds.default_bonds_config(), list(bonds.BONDS_UNIVERSE)),
        "buyback": (list(buyback.BUYBACK_FAMILY), buyback.default_buyback_config(), default),
        "commodities": (
            commodities.build_commodities_family(),
            commodities.default_commodities_config(),
            default,
        ),
        "fx": (fx.build_fx_family(synthetic_rate_differentials()), fx_config, default),
        "ivol": (list(ivol.ROUND_D1_FAMILY), CrossSectionalConfig(), default),
        "patterns_round_c": (list(patterns.ROUND_C_FAMILY), CrossSectionalConfig(), default),
        "patterns_d2": (list(d2.D2_FAMILY), CrossSectionalConfig(), default),
        "patterns_round_d": (
            list(round_d.ROUND_D_LPS_INTRADAY_FAMILY),
            CrossSectionalConfig(),
            default,
        ),
    }


def screen_family(
    specs: list[CrossSectionalSpec], config: CrossSectionalConfig, tickers: list[str]
) -> dict[str, tuple]:
    """Replay one family through the shared harness and return the exact
    floats the periods_per_year fix could possibly move: the annualized
    Sharpe (metrics.sharpe_ratio), and every field
    deflated_sharpe.compute_deflated_sharpe derives from it."""
    from app.services.research_lab.cross_sectional import (
        screen_cross_sectional_universe,
    )

    data = deterministic_panel(tickers)
    results = screen_cross_sectional_universe(
        data, specs, config, fixed_universe_membership(tickers)
    )
    out: dict[str, tuple] = {}
    for r in results:
        d = r.deflated_sharpe
        out[r.pattern_id] = (
            r.sharpe_annualized,
            d.sharpe_net_daily,
            d.psr_vs_zero,
            d.dsr,
            d.expected_max_sharpe_noise_annualized,
            d.sigma_sr_annualized,
        )
    return out


def capture_all() -> dict[str, dict[str, tuple]]:
    return {
        name: screen_family(specs, cfg, tickers)
        for name, (specs, cfg, tickers) in existing_families().items()
    }
