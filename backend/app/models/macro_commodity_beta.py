from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class MacroCommodityBeta(Base):
    """One ticker's measured historical sensitivity to one macro/commodity
    driver, as of one recompute date — "Project 2, Layer 1".

    This table is a LOOKUP TABLE, not a signal. It records a descriptive
    statistic (an OLS beta), and nothing that reads it may present a row as
    a recommendation. The pre-registration
    (data/research_runs/macro_beta_PREREGISTRATION.txt) fixes the estimator,
    the windows and the evaluation rule; this docstring only covers the
    schema decisions.

    APPEND-ONLY, AND THAT IS A HARD CONTRACT RATHER THAN AN IMPLEMENTATION
    DETAIL. Every recompute INSERTs a fresh as_of_date generation. Nothing is
    ever UPDATEd in place and nothing is ever deleted. Two reasons, both
    load-bearing:

      1. Beta drift over time is itself the auditable artifact. "This name's
         oil beta doubled over the last year" is only answerable if the old
         value still exists.
      2. A later phase is designed to record which beta value it acted on. If
         a recompute could overwrite history, that record would silently stop
         matching the table, and an after-the-fact reconstruction of "what did
         we believe when we acted" would be impossible. Overwriting would
         quietly destroy the provenance the whole design depends on.

    So there is deliberately NO unique constraint on (driver, ticker) and no
    upsert path anywhere in this family — a repeated write on the same
    as_of_date is a duplicate row, which is recoverable, rather than a
    destroyed prior generation, which is not.

    Not user-scoped, same reasoning as CrossSectionalTrialResult and
    MacroObservation: a measured market relationship is public reference data,
    identical for every user, and is not private to whoever triggered the
    recompute.

    BETA UNITS ARE NOT COMPARABLE ACROSS DRIVERS, and any consumer that
    forgets this will produce nonsense. For a "price" driver (an ETF or the
    DTWEXBGS index level) beta is dimensionless — return per unit of driver
    return. For a "rate" driver (DGS10, T10Y2Y, DFII10, T10YIE,
    BAMLH0A0HYM2) it is return per BASIS POINT of level change, numerically
    ~1e-4 the size. Ranking by |beta| is therefore only ever meaningful
    WITHIN a single driver, which is why the read API is scoped to one driver
    per request rather than offering a global leaderboard.
    """

    __tablename__ = "macro_commodity_betas"

    # Serves the one read pattern the API has: newest generation for a single
    # driver. Deliberately NOT unique — see the append-only note above; a
    # uniqueness constraint here would invite an upsert, and an upsert would
    # destroy the very history this table exists to keep.
    #
    # Plain ascending, NOT "as_of_date DESC" as the design sketch wrote it.
    # A DESC modifier makes this an EXPRESSION index, which Alembic's
    # autogenerate cannot compare against the reflected schema — it logs
    # "Generating approximate signature for index" and then reports a
    # drop+recreate of this index on EVERY `alembic check` run, forever.
    # Measured directly here before choosing: with DESC, `alembic check`
    # fails against a database that is genuinely up to date. A permanently
    # false drift signal would train future migration authors to ignore the
    # one tool that catches real drift. The DESC bought nothing to offset
    # that — B-tree indexes are traversable in both directions, so an
    # ORDER BY ... DESC uses this index just as well ascending.
    __table_args__ = (
        Index(
            "ix_macro_commodity_betas_driver_ticker_as_of",
            "driver",
            "ticker",
            "as_of_date",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # The driver_id from macro_beta.MACRO_DRIVERS (e.g. "oil_uso",
    # "credit_spread"), not the underlying symbol — the symbol backing a
    # driver could in principle be re-proxied, and the driver identity is
    # what a consumer queries by.
    driver: Mapped[str] = mapped_column(String(64), index=True)
    ticker: Mapped[str] = mapped_column(String(20), index=True)

    # The last trading day of the estimation window this beta was fit on —
    # NOT the day the job happened to run (that is computed_at). Keeping
    # these distinct is what lets a reader honestly say "this is the beta as
    # of 2026-08-31" rather than implying the recompute date.
    as_of_date: Mapped[date] = mapped_column(Date, index=True)

    # Length of the estimation window in TRADING days (settings default 252).
    # Snapshotted per row so that changing the setting later never
    # retroactively relabels what an existing row was actually computed over.
    window_days: Mapped[int] = mapped_column(Integer)

    beta_full_sample: Mapped[float] = mapped_column(Float)

    # NULL means NOT ESTIMABLE — fewer than MIN_OBS_SHOCK_DAYS usable shock
    # days, or zero driver variance across them. It must never be read as
    # zero: zero is a real measured answer ("this name does not move with the
    # driver on shock days") and NULL is the absence of one. Conflating them
    # would turn missing data into a confident claim of no sensitivity.
    beta_shock_days: Mapped[float | None] = mapped_column(Float, nullable=True)

    correlation_full_sample: Mapped[float] = mapped_column(Float)

    n_observations_full_sample: Mapped[int] = mapped_column(Integer)
    n_observations_shock_days: Mapped[int] = mapped_column(Integer)

    # Plain OLS t-stat on the slope. Deliberately NOT HAC/Newey-West and NOT
    # heteroskedasticity-robust, and it is an IN-SAMPLE number. It is stored
    # as a cheap "is this beta distinguishable from zero at all" filter and
    # for no stronger purpose; no verdict this family reports depends on it.
    # The out-of-sample test in macro_beta.evaluate_out_of_sample_forecast_quality
    # is the only place any predictive claim is made.
    t_stat_full_sample: Mapped[float] = mapped_column(Float)

    # Fraction of the window's shock days on which the ticker's actual return
    # had the same sign as beta_full_sample * driver_move predicted. IN-SAMPLE
    # and descriptive only — it has no p-value and gates nothing. NULL when
    # there were no usable shock days to compute it over.
    sign_agreement: Mapped[float | None] = mapped_column(Float, nullable=True)

    computed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
