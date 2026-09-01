"""Macro/commodity exposure betas — "Project 2", Layer 1.

WHAT THIS IS, AND WHAT IT IS EXPLICITLY NOT
============================================================================
This module produces a DURABLE LOOKUP TABLE: for each of 13 pre-declared
macro / commodity / rate / currency drivers and each ticker in the S&P 500
snapshot universe, the historical sensitivity (OLS beta) of that ticker's
daily return to that driver's daily move.

IT IS NOT A TRADING SIGNAL, and no caller may present it as one. There is no
portfolio here, no long/short legs, no cost model, no turnover, no Sharpe.
Nothing in this module imports or touches any execution pathway, and that
absence is deliberate rather than incidental.

Because there is no portfolio Sharpe, this codebase's usual Deflated Sharpe
gate (deflated_sharpe.py) DOES NOT LITERALLY APPLY and is not used. It is
replaced — not quietly dropped — by evaluate_out_of_sample_forecast_quality
below, held to the same standard: specified before results were seen,
corrected for the number of comparisons, and reported honestly either way.

The authoritative design is the pre-registration, committed BEFORE any number
from this module existed:
    backend/data/research_runs/macro_beta_PREREGISTRATION.txt
Where this docstring and that document could ever disagree, that document
wins; it is the one that was frozen in advance.

NO RAW FUTURES SYMBOLS, EVER
============================================================================
Every price-side driver is a liquid, investable ETF, and the one index-level
driver comes from FRED. This is a hard constraint inherited from a bug this
project already found and fixed once: Yahoo's raw continuous-futures tickers
(NG=F, CL=F, ...) are a naive front-month splice that fabricates phantom roll
return. The in-repo measurement, at cross_sectional_commodities.py lines
41-50, is NG=F's chained-return CAGR of -4.20%/yr against the investable
proxy UNG's -25.42%/yr over the same window — the splice invents +28.4%/yr
that no holder of the commodity could ever have earned.

test_macro_beta.py asserts mechanically that no declared driver symbol
contains "=", so this discipline cannot be lost to a future edit.

UNITS — THE ONE THING A CONSUMER MOST EASILY GETS WRONG
============================================================================
Betas are NOT comparable across driver kinds. A "price" driver's beta is
dimensionless (return per unit return). A "rate" driver's beta is return per
BASIS POINT, numerically ~1e-4 the size. Ranking names by |beta| is therefore
only meaningful WITHIN one driver, which is why the read API takes exactly
one driver per request and offers no global leaderboard.
"""

import logging
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd
from scipy.stats import spearmanr, ttest_1samp
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.macro_commodity_beta import MacroCommodityBeta
from app.services.macro_data.base import MacroDataError, MacroDataProvider
from app.services.market_data.base import MarketDataProvider
from app.services.market_data.price_cache import get_price_history_cached

logger = logging.getLogger(__name__)


# --- driver definitions -----------------------------------------------------

DRIVER_KIND_PRICE = "price"
DRIVER_KIND_RATE = "rate"

DRIVER_SOURCE_ETF = "etf"
DRIVER_SOURCE_FRED = "fred"


@dataclass(frozen=True)
class MacroDriver:
    """One pre-declared driver. Frozen as a tuple below; the roster may not
    grow or shrink after the pre-registration commit.

    `kind` decides how a LEVEL becomes a MOVE, and therefore what the beta's
    units are:
      - DRIVER_KIND_PRICE: move = simple daily return of the level.
      - DRIVER_KIND_RATE:  move = daily first difference in BASIS POINTS.
                           FRED reports all five rate/spread series in
                           percent, so the conversion is x100.

    DTWEXBGS is classified `price`, not `rate`, on purpose: it is an index
    LEVEL (~118), not a rate, so a percentage change is its meaningful move
    and a first difference would be a unit error.

    `mechanism` is the REASON FOR INCLUSION — economic reasoning, explicitly
    NOT a verified empirical claim and not a citation to any paper. See
    section 1 of the pre-registration: this family replicates no published
    result and deliberately makes no academic claim, so there is no citation
    here to verify.
    """

    driver_id: str
    source: str
    symbol: str
    kind: str
    label: str
    mechanism: str


MACRO_DRIVERS: tuple[MacroDriver, ...] = (
    MacroDriver(
        "oil_uso", DRIVER_SOURCE_ETF, "USO", DRIVER_KIND_PRICE, "Crude oil (USO)",
        "Crude oil price level; input cost for transport/industrials, revenue for E&P.",
    ),
    MacroDriver(
        "gold_gld", DRIVER_SOURCE_ETF, "GLD", DRIVER_KIND_PRICE, "Gold (GLD)",
        "Safe-haven and real-yield hedge; physically backed, so no roll effect at all.",
    ),
    MacroDriver(
        "copper_cper", DRIVER_SOURCE_ETF, "CPER", DRIVER_KIND_PRICE, "Copper (CPER)",
        "Global industrial and construction demand; China-sensitive.",
    ),
    MacroDriver(
        "natgas_ung", DRIVER_SOURCE_ETF, "UNG", DRIVER_KIND_PRICE, "Natural gas (UNG)",
        "Energy input cost for utilities and industrials; energy-security shocks.",
    ),
    MacroDriver(
        "agri_dba", DRIVER_SOURCE_ETF, "DBA", DRIVER_KIND_PRICE, "Agriculture (DBA)",
        "Food-price inflation channel; consumer-staples margin pressure.",
    ),
    MacroDriver(
        "broad_commod_dbc", DRIVER_SOURCE_ETF, "DBC", DRIVER_KIND_PRICE, "Broad commodities (DBC)",
        "Aggregate commodity-inflation level.",
    ),
    MacroDriver(
        "china_fxi", DRIVER_SOURCE_ETF, "FXI", DRIVER_KIND_PRICE, "China large-cap (FXI)",
        "China and global-growth node; commodity demand and risk appetite both route through it.",
    ),
    MacroDriver(
        "credit_spread", DRIVER_SOURCE_FRED, "BAMLH0A0HYM2", DRIVER_KIND_RATE,
        "High-yield OAS (BAMLH0A0HYM2)",
        "Risk appetite / financial conditions. NOTE: FRED serves this series over a rolling "
        "~3-year window only (measured 2026-09-01: earliest observation 2023-09-01), so this "
        "is the lowest-powered driver of the 13 — see pre-registration section 3.",
    ),
    MacroDriver(
        "rate_dgs10", DRIVER_SOURCE_FRED, "DGS10", DRIVER_KIND_RATE, "10Y Treasury yield (DGS10)",
        "Nominal discount-rate level; what duration-sensitive sectors react to daily.",
    ),
    MacroDriver(
        "curve_t10y2y", DRIVER_SOURCE_FRED, "T10Y2Y", DRIVER_KIND_RATE, "10Y-2Y curve (T10Y2Y)",
        "Curve slope — a distinct dimension from the yield level above.",
    ),
    MacroDriver(
        "real_yield_dfii10", DRIVER_SOURCE_FRED, "DFII10", DRIVER_KIND_RATE,
        "10Y TIPS real yield (DFII10)",
        "The discount-rate channel net of inflation.",
    ),
    MacroDriver(
        "breakeven_t10yie", DRIVER_SOURCE_FRED, "T10YIE", DRIVER_KIND_RATE,
        "10Y breakeven inflation (T10YIE)",
        "Inflation expectations; feeds policy pricing and therefore real yields.",
    ),
    MacroDriver(
        "dollar_broad", DRIVER_SOURCE_FRED, "DTWEXBGS", DRIVER_KIND_PRICE,
        "Broad trade-weighted USD (DTWEXBGS)",
        "Exporter/importer translation and EM-stress channel. An index level, hence kind=price.",
    ),
)

MACRO_DRIVERS_BY_ID: dict[str, MacroDriver] = {d.driver_id: d for d in MACRO_DRIVERS}

# The pre-declared trial count. 13 drivers x 2 beta variants = 26 primary
# (rank) tests, and that is the Bonferroni denominator fixed by the
# pre-registration. The 26 secondary sign tests are reported alongside but do
# not enlarge this denominator, because they are not the pass/fail gate.
N_DRIVERS = len(MACRO_DRIVERS)
N_BETA_VARIANTS = 2
N_PRIMARY_TESTS = N_DRIVERS * N_BETA_VARIANTS
FAMILY_ALPHA = 0.05
BONFERRONI_ALPHA = FAMILY_ALPHA / N_PRIMARY_TESTS  # 0.0019230769...

BETA_VARIANT_FULL_SAMPLE = "full_sample"
BETA_VARIANT_SHOCK_DAYS = "shock_days"

MACRO_BETA_FAMILY_NAME = "macro_beta"


# --- pre-declared estimator constants (frozen by the pre-registration) ------

# Top decile of |move|. 0.90 is the quantile, computed within the reference
# window and for that driver only — never a cross-driver or full-history
# threshold, which would leak one regime's volatility into another's.
SHOCK_DECILE_QUANTILE = 0.90

MIN_OBS_FULL_SAMPLE = 60
MIN_OBS_SHOCK_DAYS = 10

# The out-of-sample split: 252 fit days immediately followed by 252 test days.
# The fit window is 252 rather than something larger precisely so the thing
# evaluated is the SAME estimator that gets persisted, not a research-only
# variant that is never deployed.
OOS_FIT_WINDOW_DAYS = 252
OOS_TEST_WINDOW_DAYS = 252
OOS_REQUIRED_ALIGNED_DAYS = OOS_FIT_WINDOW_DAYS + OOS_TEST_WINDOW_DAYS

MIN_OOS_SHOCK_DAYS = 10
MIN_OOS_CROSS_SECTION = 100

VERDICT_SKILL = "skill"
VERDICT_NO_SKILL = "no_skill"
VERDICT_NO_VERDICT = "no_verdict"

# Trading days are ~252/365 of calendar days. Fetching a window in CALENDAR
# days and then slicing the last N ALIGNED TRADING rows is the only correct
# order of operations: slicing calendar-first would silently shorten the
# window by every weekend and holiday it happened to span.
_CALENDAR_PER_TRADING_DAY = 1.5
_CALENDAR_BUFFER_DAYS = 60


def calendar_lookback_days(trading_days: int) -> int:
    """Calendar-day lookback generous enough to contain `trading_days`
    trading days plus slack for holidays and a stale final FRED print."""
    return int(trading_days * _CALENDAR_PER_TRADING_DAY) + _CALENDAR_BUFFER_DAYS


# --- the estimator -----------------------------------------------------------


@dataclass
class OlsFit:
    beta: float
    t_stat: float
    correlation: float
    n: int


def _ols_with_intercept(y: np.ndarray, x: np.ndarray) -> OlsFit | None:
    """Univariate OLS of y on x WITH an intercept.

        beta = Sxy / Sxx,   t = beta / SE(beta),
        SE(beta) = sqrt( SSR/(n-2) / Sxx )

    Returns None rather than a NaN-filled result when the fit is not defined:
    fewer than 3 points (n-2 <= 0), or zero variance in x. Handing back a
    fabricated number for a degenerate regression is exactly the failure this
    project's conventions exist to prevent, so a non-fit is an explicit
    absence, never a silent zero.
    """
    n = len(y)
    if n < 3 or len(x) != n:
        return None

    x_centered = x - x.mean()
    y_centered = y - y.mean()
    sxx = float((x_centered**2).sum())
    syy = float((y_centered**2).sum())
    sxy = float((x_centered * y_centered).sum())

    if sxx <= 0 or not np.isfinite(sxx):
        return None

    beta = sxy / sxx
    residuals = y_centered - beta * x_centered
    ssr = float((residuals**2).sum())
    se_beta_sq = (ssr / (n - 2)) / sxx

    if se_beta_sq > 0 and np.isfinite(se_beta_sq):
        t_stat = beta / np.sqrt(se_beta_sq)
    else:
        # A perfect fit (SSR == 0) has an infinite t-stat in the limit. On
        # synthetic data that is exact and meaningful; report it as inf
        # rather than pretending the regression failed.
        t_stat = float("inf") * np.sign(beta) if beta != 0 else 0.0

    # Correlation needs REAL variance in y, and `syy > 0` is not a strong
    # enough test for that. A flat return series (a halted or stale-priced
    # ticker repeating the same close) leaves syy as pure floating-point
    # residue — measured at ~1e-64 for a constant 0.001 series over 120 days
    # — which is strictly positive and would make the ratio
    # tiny/sqrt(tiny) an arbitrary number anywhere in [-1, 1]. A garbage
    # correlation of 0.99 sitting next to a beta of 0 is exactly the kind of
    # internally-inconsistent row a later phase would have no way to spot.
    # So degeneracy is judged RELATIVE to the scale of y, not against zero.
    y_scale = float((y**2).sum())
    y_is_degenerate = syy <= np.finfo(float).eps * max(1.0, y_scale)
    correlation = 0.0 if y_is_degenerate else sxy / np.sqrt(sxx * syy)
    correlation = float(np.clip(correlation, -1.0, 1.0))

    if not np.isfinite(beta):
        return None
    return OlsFit(beta=float(beta), t_stat=float(t_stat), correlation=float(correlation), n=n)


def shock_day_mask(moves: pd.Series, quantile: float = SHOCK_DECILE_QUANTILE) -> pd.Series:
    """Boolean mask of the driver's own top-decile |move| days, computed
    WITHIN the passed window and for this driver alone.

    Uses >= against the quantile, so an exactly-at-threshold day is included.
    On real data ties are vanishingly rare; on synthetic test data with
    repeated values this can admit slightly more than a strict decile, which
    is deterministic and is what the tests pin.
    """
    absolute = moves.abs()
    if absolute.empty:
        return pd.Series(dtype=bool, index=moves.index)
    threshold = float(np.quantile(absolute.to_numpy(), quantile))
    return absolute >= threshold


@dataclass
class TickerBetaResult:
    """One (driver, ticker) measurement over one estimation window."""

    ticker: str
    beta_full_sample: float
    beta_shock_days: float | None
    correlation_full_sample: float
    n_observations_full_sample: int
    n_observations_shock_days: int
    t_stat_full_sample: float
    sign_agreement: float | None


def compute_beta_for_ticker(
    ticker: str,
    ticker_returns: pd.Series,
    driver_moves: pd.Series,
    *,
    min_obs_full_sample: int = MIN_OBS_FULL_SAMPLE,
    min_obs_shock_days: int = MIN_OBS_SHOCK_DAYS,
) -> TickerBetaResult | None:
    """Both betas for one ticker against one driver, over whatever window the
    two passed series span.

    The caller is responsible for having already sliced to the estimation
    window; this function does not slice. It aligns the two series on their
    shared index and drops any day either side is missing — NO forward-fill,
    NO interpolation, NO imputation. A missing day is dropped, never invented.

    Returns None when the full-sample gate fails (too few usable days, or a
    degenerate regression). A None is "not estimable" and the caller writes no
    row; it is never converted into a zero beta.
    """
    aligned = pd.concat(
        {"r": ticker_returns, "m": driver_moves}, axis=1, join="inner"
    ).dropna()
    if len(aligned) < min_obs_full_sample:
        return None

    r = aligned["r"].to_numpy(dtype=float)
    m = aligned["m"].to_numpy(dtype=float)

    full = _ols_with_intercept(r, m)
    if full is None:
        return None

    shock_mask = shock_day_mask(aligned["m"]).to_numpy()
    n_shock = int(shock_mask.sum())

    beta_shock: float | None = None
    if n_shock >= min_obs_shock_days:
        shock_fit = _ols_with_intercept(r[shock_mask], m[shock_mask])
        if shock_fit is not None:
            beta_shock = shock_fit.beta

    # sign_agreement: IN-SAMPLE and descriptive only. It carries no p-value
    # and gates nothing — evaluate_out_of_sample_forecast_quality is the only
    # place this family makes a predictive claim. Exact zeros on either side
    # count as disagreement (deterministic, and measure-zero on real data).
    sign_agreement: float | None = None
    if n_shock > 0:
        predicted = np.sign(full.beta * m[shock_mask])
        actual = np.sign(r[shock_mask])
        sign_agreement = float((predicted == actual).mean())

    return TickerBetaResult(
        ticker=ticker,
        beta_full_sample=full.beta,
        beta_shock_days=beta_shock,
        correlation_full_sample=full.correlation,
        n_observations_full_sample=full.n,
        n_observations_shock_days=n_shock,
        t_stat_full_sample=full.t_stat,
        sign_agreement=sign_agreement,
    )


# --- data assembly -----------------------------------------------------------


@dataclass
class MacroBetaInputs:
    """Everything both entrypoints need, fetched once.

    ticker_returns: DatetimeIndex x ticker daily simple returns.
    driver_moves:   driver_id -> daily move series (units per MacroDriver.kind).
    Drivers that could not be fetched appear in `failed_drivers` and are
    absent from `driver_moves` — never present with fabricated values.
    """

    ticker_returns: pd.DataFrame
    driver_moves: dict[str, pd.Series]
    missing_tickers: list[str]
    failed_drivers: dict[str, str]


def levels_to_moves(levels: pd.Series, kind: str) -> pd.Series:
    """Level series -> daily move, per the pre-registered convention.

    price: simple daily return.
    rate:  daily first difference in BASIS POINTS (FRED reports these in
           percent, so x100).
    """
    ordered = levels.sort_index().dropna()
    if kind == DRIVER_KIND_PRICE:
        return ordered.pct_change().dropna()
    if kind == DRIVER_KIND_RATE:
        return (ordered.diff() * 100.0).dropna()
    raise ValueError(f"unknown driver kind {kind!r}")


def load_macro_beta_inputs(
    db: Session,
    price_provider: MarketDataProvider,
    macro_provider: MacroDataProvider,
    tickers: list[str],
    *,
    end: date,
    trading_days_needed: int,
    drivers: tuple[MacroDriver, ...] = MACRO_DRIVERS,
) -> MacroBetaInputs:
    """Fetch every input from the EXISTING clients — no second FRED client and
    no second price client is written here.

    ETF drivers go through get_price_history_cached exactly like any equity,
    so they land in the same price_bars cache; FRED drivers go through
    FredProvider.get_observation_history.
    """
    start = end - timedelta(days=calendar_lookback_days(trading_days_needed))

    etf_symbols = [d.symbol for d in drivers if d.source == DRIVER_SOURCE_ETF]
    all_price_symbols = list(dict.fromkeys([*tickers, *etf_symbols]))

    prices, missing = get_price_history_cached(db, price_provider, all_price_symbols, start, end)
    if prices.empty:
        raise RuntimeError("price fetch returned no data at all — refusing to compute betas")

    returns = prices.pct_change()

    driver_moves: dict[str, pd.Series] = {}
    failed: dict[str, str] = {}

    for driver in drivers:
        if driver.source == DRIVER_SOURCE_ETF:
            if driver.symbol not in prices.columns:
                failed[driver.driver_id] = f"ETF {driver.symbol} did not resolve"
                continue
            driver_moves[driver.driver_id] = levels_to_moves(
                prices[driver.symbol].dropna(), driver.kind
            )
            continue

        try:
            observations = macro_provider.get_observation_history(driver.symbol, "lin", start, end)
        except MacroDataError as exc:
            failed[driver.driver_id] = f"FRED fetch failed: {exc}"
            continue
        if not observations:
            failed[driver.driver_id] = f"FRED returned no observations for {driver.symbol}"
            continue
        levels = pd.Series(
            [o.value for o in observations],
            index=pd.to_datetime([o.observation_date for o in observations]),
        )
        driver_moves[driver.driver_id] = levels_to_moves(levels, driver.kind)

    ticker_returns = returns[[c for c in returns.columns if c in set(tickers)]]

    return MacroBetaInputs(
        ticker_returns=ticker_returns,
        driver_moves=driver_moves,
        missing_tickers=missing,
        failed_drivers=failed,
    )


# --- entrypoint 1: build and persist the lookup table ------------------------


@dataclass
class MacroBetaRunSummary:
    as_of_date: date
    window_days: int
    n_rows: int
    n_drivers_computed: int
    rows_per_driver: dict[str, int]
    failed_drivers: dict[str, str]
    missing_tickers: list[str]


def run_macro_beta_family(
    db: Session,
    price_provider: MarketDataProvider,
    macro_provider: MacroDataProvider,
    tickers: list[str],
    *,
    end: date,
    window_days: int | None = None,
    persist: bool = True,
    inputs: MacroBetaInputs | None = None,
) -> MacroBetaRunSummary:
    """Compute every (driver, ticker) beta over the trailing `window_days`
    and APPEND them to macro_commodity_betas.

    APPEND-ONLY. This function only ever INSERTs. It contains no UPDATE and no
    DELETE, and adding one would break the provenance contract documented on
    MacroCommodityBeta — a later phase records which beta value it acted on,
    and that record has to stay checkable against the table forever.

    `inputs` lets a caller (and the tests) supply an already-assembled panel
    instead of hitting the network.
    """
    window_days = window_days or settings.macro_beta_rolling_window_days

    if inputs is None:
        inputs = load_macro_beta_inputs(
            db,
            price_provider,
            macro_provider,
            tickers,
            end=end,
            trading_days_needed=window_days,
        )

    rows: list[MacroCommodityBeta] = []
    rows_per_driver: dict[str, int] = {}
    as_of: date | None = None

    for driver in MACRO_DRIVERS:
        moves = inputs.driver_moves.get(driver.driver_id)
        if moves is None or moves.empty:
            continue

        # Align FIRST, then take the last `window_days` ALIGNED trading rows.
        # Slicing on calendar dates instead would silently shorten the window
        # by every weekend and holiday the range happened to span.
        common_index = inputs.ticker_returns.index.intersection(moves.index)
        if len(common_index) < MIN_OBS_FULL_SAMPLE:
            continue
        window_index = common_index.sort_values()[-window_days:]
        window_moves = moves.loc[window_index]
        driver_as_of = window_index[-1].date()
        as_of = driver_as_of if as_of is None else max(as_of, driver_as_of)

        count = 0
        for ticker in inputs.ticker_returns.columns:
            result = compute_beta_for_ticker(
                ticker, inputs.ticker_returns[ticker].loc[window_index], window_moves
            )
            if result is None:
                continue
            rows.append(
                MacroCommodityBeta(
                    driver=driver.driver_id,
                    ticker=ticker,
                    as_of_date=driver_as_of,
                    window_days=window_days,
                    beta_full_sample=result.beta_full_sample,
                    beta_shock_days=result.beta_shock_days,
                    correlation_full_sample=result.correlation_full_sample,
                    n_observations_full_sample=result.n_observations_full_sample,
                    n_observations_shock_days=result.n_observations_shock_days,
                    t_stat_full_sample=result.t_stat_full_sample,
                    sign_agreement=result.sign_agreement,
                )
            )
            count += 1
        rows_per_driver[driver.driver_id] = count

    if persist and rows:
        db.add_all(rows)
        db.commit()

    return MacroBetaRunSummary(
        as_of_date=as_of or end,
        window_days=window_days,
        n_rows=len(rows),
        n_drivers_computed=len(rows_per_driver),
        rows_per_driver=rows_per_driver,
        failed_drivers=inputs.failed_drivers,
        missing_tickers=inputs.missing_tickers,
    )


def latest_beta_as_of_date(db: Session) -> date | None:
    """Newest as_of_date in the table, or None if it is empty. An EMPTY table
    means "never computed", which the refresh runner must treat as STALE — a
    first deploy has to compute rather than sit idle forever."""
    return db.execute(
        select(MacroCommodityBeta.as_of_date).order_by(MacroCommodityBeta.as_of_date.desc()).limit(1)
    ).scalar_one_or_none()


# --- entrypoint 2: the out-of-sample forecast-quality test -------------------


@dataclass
class DriverForecastQuality:
    """One driver x one beta variant. 26 of these per full evaluation."""

    driver: str
    beta_variant: str
    verdict: str
    reason: str
    n_tickers_fit: int
    n_shock_days_tested: int
    min_cross_section: int | None
    mean_rank_correlation: float | None
    t_rank: float | None
    p_rank_one_sided: float | None
    mean_sign_rate_demeaned: float | None
    t_sign: float | None
    p_sign_one_sided: float | None
    mean_sign_rate_raw_diagnostic: float | None
    fit_start: date | None
    fit_end: date | None
    test_start: date | None
    test_end: date | None


def _fit_betas_over_window(
    ticker_returns: pd.DataFrame, moves: pd.Series, window_index: pd.Index
) -> dict[str, TickerBetaResult]:
    window_moves = moves.loc[window_index]
    fitted: dict[str, TickerBetaResult] = {}
    for ticker in ticker_returns.columns:
        result = compute_beta_for_ticker(
            ticker, ticker_returns[ticker].loc[window_index], window_moves
        )
        if result is not None:
            fitted[ticker] = result
    return fitted


def _one_sided_greater(values: list[float], null_value: float) -> tuple[float | None, float | None]:
    """One-sample t-test of `values` against `null_value`, alternative
    'greater'. Returns (t, p), or (None, None) when the test is undefined
    (fewer than 2 values, or zero variance — a degenerate case that must be
    reported as absent rather than as a p-value of 0 or 1)."""
    if len(values) < 2:
        return None, None
    array = np.asarray(values, dtype=float)
    if not np.isfinite(array).all() or float(array.std(ddof=1)) == 0.0:
        return None, None
    result = ttest_1samp(array, null_value, alternative="greater")
    t_stat = float(result.statistic)
    p_value = float(result.pvalue)
    if not np.isfinite(t_stat) or not np.isfinite(p_value):
        return None, None
    return t_stat, p_value


def evaluate_out_of_sample_forecast_quality(
    inputs: MacroBetaInputs,
    *,
    fit_window_days: int = OOS_FIT_WINDOW_DAYS,
    test_window_days: int = OOS_TEST_WINDOW_DAYS,
    min_shock_days: int = MIN_OOS_SHOCK_DAYS,
    min_cross_section: int = MIN_OOS_CROSS_SECTION,
    alpha: float = BONFERRONI_ALPHA,
) -> list[DriverForecastQuality]:
    """The pre-registered out-of-sample test. Returns 26 verdicts (13 drivers
    x 2 beta variants), in driver order.

    THE SINGLE MOST IMPORTANT STATISTICAL CHOICE HERE IS THE UNIT OF
    OBSERVATION, and it is fixed by the pre-registration: the DAY, not the
    (ticker, day) pair. Returns within one day are massively cross-sectionally
    correlated, so ~500 names on one day carry roughly one day's worth of
    independent information, not 500. Pooling pairs would understate the
    standard error by something like sqrt(500) and manufacture significance
    out of nothing. Every p-value below therefore has n = number of shock
    DAYS, typically ~25.

    The primary statistic is the per-day Spearman rank correlation between the
    fitted beta and the orientation-adjusted return. Spearman is invariant to
    subtracting a constant from every return on a day, so it is AUTOMATICALLY
    immune to the market-direction confound — that immunity is the reason it,
    and not the sign rate, is primary. The sign rate is reported as a
    cross-sectionally demeaned secondary statistic, plus a raw undemeaned
    version that is a DIAGNOSTIC ONLY and is evidence of nothing (if the
    market rose and most betas share a sign, the raw rate is high for reasons
    unrelated to the driver).
    """
    results: list[DriverForecastQuality] = []

    for driver in MACRO_DRIVERS:
        moves = inputs.driver_moves.get(driver.driver_id)

        for variant in (BETA_VARIANT_FULL_SAMPLE, BETA_VARIANT_SHOCK_DAYS):
            if moves is None or moves.empty:
                results.append(
                    _no_verdict(
                        driver.driver_id,
                        variant,
                        inputs.failed_drivers.get(driver.driver_id, "driver series unavailable"),
                    )
                )
                continue

            common = inputs.ticker_returns.index.intersection(moves.index).sort_values()
            required = fit_window_days + test_window_days
            if len(common) < required:
                results.append(
                    _no_verdict(
                        driver.driver_id,
                        variant,
                        f"insufficient history: {len(common)} aligned trading days, need {required}",
                    )
                )
                continue

            fit_index = common[-required:-test_window_days]
            test_index = common[-test_window_days:]

            fitted = _fit_betas_over_window(inputs.ticker_returns, moves, fit_index)
            betas = {
                ticker: (
                    result.beta_full_sample
                    if variant == BETA_VARIANT_FULL_SAMPLE
                    else result.beta_shock_days
                )
                for ticker, result in fitted.items()
            }
            betas = {t: b for t, b in betas.items() if b is not None and np.isfinite(b)}

            if len(betas) < min_cross_section:
                results.append(
                    _no_verdict(
                        driver.driver_id,
                        variant,
                        f"only {len(betas)} tickers had an estimable {variant} beta, "
                        f"need {min_cross_section}",
                        n_tickers_fit=len(betas),
                        fit_index=fit_index,
                        test_index=test_index,
                    )
                )
                continue

            # Window B's shock threshold comes from window B alone. Reusing
            # window A's would leak the fit period's volatility regime into
            # the test.
            test_moves = moves.loc[test_index]
            shock_days = test_index[shock_day_mask(test_moves).to_numpy()]

            beta_series = pd.Series(betas)
            rhos: list[float] = []
            sign_rates: list[float] = []
            raw_sign_rates: list[float] = []
            cross_sections: list[int] = []

            for day in shock_days:
                day_returns = inputs.ticker_returns.loc[day, list(beta_series.index)].dropna()
                if len(day_returns) < min_cross_section:
                    continue

                move = float(test_moves.loc[day])
                if move == 0.0:
                    continue
                oriented = day_returns * np.sign(move)
                aligned_betas = beta_series.loc[day_returns.index]

                rho = spearmanr(aligned_betas.to_numpy(), oriented.to_numpy()).statistic
                if not np.isfinite(rho):
                    continue
                rhos.append(float(rho))

                demeaned_beta = aligned_betas - aligned_betas.mean()
                demeaned_return = oriented - oriented.mean()
                sign_rates.append(
                    float((np.sign(demeaned_beta) == np.sign(demeaned_return)).mean())
                )
                raw_sign_rates.append(float((np.sign(aligned_betas) == np.sign(oriented)).mean()))
                cross_sections.append(len(day_returns))

            if len(rhos) < min_shock_days:
                results.append(
                    _no_verdict(
                        driver.driver_id,
                        variant,
                        f"insufficient power: {len(rhos)} usable out-of-sample shock days, "
                        f"need {min_shock_days}",
                        n_tickers_fit=len(betas),
                        n_shock_days=len(rhos),
                        fit_index=fit_index,
                        test_index=test_index,
                    )
                )
                continue

            mean_rho = float(np.mean(rhos))
            t_rank, p_rank = _one_sided_greater(rhos, 0.0)
            t_sign, p_sign = _one_sided_greater(sign_rates, 0.5)

            passed = mean_rho > 0 and p_rank is not None and p_rank < alpha
            if passed:
                verdict = VERDICT_SKILL
                reason = (
                    f"mean rank correlation {mean_rho:+.4f} over {len(rhos)} out-of-sample shock "
                    f"days, one-sided p={p_rank:.2e} < Bonferroni alpha {alpha:.6f}"
                )
            else:
                verdict = VERDICT_NO_SKILL
                p_text = f"{p_rank:.4f}" if p_rank is not None else "undefined"
                reason = (
                    f"mean rank correlation {mean_rho:+.4f} over {len(rhos)} out-of-sample shock "
                    f"days, one-sided p={p_text} (Bonferroni alpha {alpha:.6f}) — "
                    "no demonstrated out-of-sample forecast skill"
                )

            results.append(
                DriverForecastQuality(
                    driver=driver.driver_id,
                    beta_variant=variant,
                    verdict=verdict,
                    reason=reason,
                    n_tickers_fit=len(betas),
                    n_shock_days_tested=len(rhos),
                    min_cross_section=min(cross_sections) if cross_sections else None,
                    mean_rank_correlation=mean_rho,
                    t_rank=t_rank,
                    p_rank_one_sided=p_rank,
                    mean_sign_rate_demeaned=float(np.mean(sign_rates)) if sign_rates else None,
                    t_sign=t_sign,
                    p_sign_one_sided=p_sign,
                    mean_sign_rate_raw_diagnostic=(
                        float(np.mean(raw_sign_rates)) if raw_sign_rates else None
                    ),
                    fit_start=fit_index[0].date(),
                    fit_end=fit_index[-1].date(),
                    test_start=test_index[0].date(),
                    test_end=test_index[-1].date(),
                )
            )

    return results


def _no_verdict(
    driver_id: str,
    variant: str,
    reason: str,
    *,
    n_tickers_fit: int = 0,
    n_shock_days: int = 0,
    fit_index: pd.Index | None = None,
    test_index: pd.Index | None = None,
) -> DriverForecastQuality:
    """A NO VERDICT is NOT a negative and must never be reported as one. It
    says the pre-registered test could not be run at the declared power, which
    is a different claim from "this driver showed no skill"."""
    return DriverForecastQuality(
        driver=driver_id,
        beta_variant=variant,
        verdict=VERDICT_NO_VERDICT,
        reason=reason,
        n_tickers_fit=n_tickers_fit,
        n_shock_days_tested=n_shock_days,
        min_cross_section=None,
        mean_rank_correlation=None,
        t_rank=None,
        p_rank_one_sided=None,
        mean_sign_rate_demeaned=None,
        t_sign=None,
        p_sign_one_sided=None,
        mean_sign_rate_raw_diagnostic=None,
        fit_start=fit_index[0].date() if fit_index is not None and len(fit_index) else None,
        fit_end=fit_index[-1].date() if fit_index is not None and len(fit_index) else None,
        test_start=test_index[0].date() if test_index is not None and len(test_index) else None,
        test_end=test_index[-1].date() if test_index is not None and len(test_index) else None,
    )
