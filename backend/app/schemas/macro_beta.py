from pydantic import BaseModel

# Server-authored and structurally non-optional on every response below, so no
# frontend change can drop it. A beta is a DESCRIPTIVE measurement, not a
# recommendation, and this endpoint is read by a later phase whose whole risk
# is over-reading it.
MACRO_BETA_EVIDENCE_DISCLAIMER = (
    "Historical sensitivity only — a descriptive OLS beta, not a trading signal, "
    "not a forecast, and not a recommendation. Betas are estimated on a rolling "
    "window of daily data and are noisy. See "
    "data/research_runs/macro_beta_PREREGISTRATION.txt for the estimator and the "
    "pre-registered out-of-sample evaluation, and the run report for which drivers "
    "did and did not demonstrate out-of-sample forecast skill."
)


class MacroBetaRowOut(BaseModel):
    driver: str
    ticker: str
    as_of_date: str
    window_days: int
    beta_full_sample: float
    # None means NOT ESTIMABLE (too few usable shock days), never zero. A
    # consumer that coerces this to 0.0 is asserting "no sensitivity", which
    # is a measured claim this row does not make.
    beta_shock_days: float | None
    correlation_full_sample: float
    n_observations_full_sample: int
    n_observations_shock_days: int
    t_stat_full_sample: float
    sign_agreement: float | None


class MacroDriverOut(BaseModel):
    driver_id: str
    source: str
    symbol: str
    kind: str  # "price" (beta is dimensionless) | "rate" (beta is per basis point)
    label: str
    mechanism: str


class MacroBetaResponse(BaseModel):
    driver: MacroDriverOut
    as_of_date: str
    # Ranked by |beta| WITHIN this one driver. Betas are not comparable across
    # drivers of different kinds (see MacroCommodityBeta's docstring), which is
    # why this endpoint is scoped to exactly one driver and offers no global
    # ranking.
    rows: list[MacroBetaRowOut]
    disclaimer: str


class MacroDriverCatalogResponse(BaseModel):
    drivers: list[MacroDriverOut]
    disclaimer: str
