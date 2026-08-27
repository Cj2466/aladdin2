from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class CrossSectionalTrialResult(Base):
    """Shared results cache for every cross-sectional / timing family's
    per-spec screening output — the same "typed columns for what a
    leaderboard genuinely needs, JSON for the rest" shape as ExperimentRun,
    extended to the family shape instead of the pairs/momentum shape.

    Built 2026-08-27 to close a real, confirmed gap: every cross-sectional
    family this project has built (Commodities, Buyback, Bonds, FX, IVOL,
    D1, D2, Round C, Crypto, Vol-Regime, Index-removal, Small/mid-cap,
    Correlation Risk Premium) computed real per-spec results with NO
    database table to persist them to — every number only ever existed as
    ad-hoc script output in a temp scratchpad. That gap caused two real
    incidents the same day it was found: a local dev database wipe
    silently destroyed 249 real experiment_runs rows, and a synthetic
    RNG-generated regression-test fixture (no relation to any real
    backtest) got mistaken for real archived results by a later analysis,
    producing a fabricated "positive finding" that only fell apart under
    adversarial re-verification. See
    app.services.research_lab.cross_sectional_persistence for the writer
    and its own docstring for the exact contract this table exists to
    enforce (real production data only, verified at write time, never
    silently accepting a value that looks like a test fixture).

    Not user-scoped — shared across every screening run, same reasoning as
    ExperimentRun and RiskResult (a family's own trial result isn't
    private to whoever happened to run the screen)."""

    __tablename__ = "cross_sectional_trial_results"

    id: Mapped[int] = mapped_column(primary_key=True)

    # e.g. "correlation_risk_premium", "vol_regime", "round_c", "buyback" —
    # matches the family module's own established short name, not enforced
    # against a fixed enum (new families get added; a typo here is caught
    # by nothing having that family_key, not by a DB constraint rejecting
    # the row).
    family_key: Mapped[str] = mapped_column(String(64), index=True)

    # The family's own spec/pattern identifier (CrpScreeningResult.spec_id,
    # CrossSectionalScreeningResult.pattern_id, etc.) — unique WITHIN a
    # family_key + run, not globally, since two different runs of the same
    # family (e.g. after a code fix) both get their own rows rather than
    # overwriting each other. See run_tag below for telling those runs
    # apart.
    trial_id: Mapped[str] = mapped_column(String(128), index=True)

    computed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # A free-text tag identifying which invocation produced this row (e.g.
    # a script name, or a date-stamped label) — NOT a foreign key to
    # anything, since these are run from ad-hoc scripts with no shared job
    # table. Its real job is letting a later query say "these 15 rows are
    # one screening pass" without relying on computed_at timestamps lining
    # up exactly, and letting a human reading the table see at a glance
    # this came from a real production run, not a stray test.
    run_tag: Mapped[str] = mapped_column(String(128), index=True)

    sharpe_annualized: Mapped[float] = mapped_column(Float)
    n_observations: Mapped[int] = mapped_column(Integer)  # n_trading_days in every family so far

    # The family's own pre-declared trial count AT THE TIME this row was
    # written — not recomputed later. A family can grow across sessions
    # (Phase A's pattern count did, 212 -> a later, separately-tracked
    # count); this column is this row's honest denominator, not "whatever
    # the family's size is today."
    n_trials: Mapped[int] = mapped_column(Integer)

    # Both permanently nullable, matching DeflatedSharpeResult's own
    # contract: dsr is None below MIN_TRIALS_FOR_DSR, and that's correct
    # modeling, not a gap to backfill.
    dsr: Mapped[float | None] = mapped_column(Float, nullable=True)
    psr_vs_zero: Mapped[float | None] = mapped_column(Float, nullable=True)

    # The complete per-spec result object, family-specific fields and all
    # (asdict of whatever dataclass the family module produced) — this
    # table's results_json equivalent.
    full_result_json: Mapped[str] = mapped_column(Text)
