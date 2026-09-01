from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class MacroEventDetection(Base):
    """One Stage-A scan result for ONE source, from ONE EventScannerRunner
    tick — "Project 2", Layer 2, Phase 2.2.

    WHAT THIS TABLE IS FOR, AND WHY IT RECORDS NON-EVENTS
    ========================================================================
    Phase 2.2 exists to answer one question honestly: HOW OFTEN DO THESE
    THRESHOLDS ACTUALLY TRIP? Every threshold constant in
    services/macro_event/drivers.py is an uncalibrated order-of-magnitude
    guess, and the plan's exit criterion for this phase is a human looking at
    a couple of weeks of REAL trigger rates and deciding whether they are sane
    (not zero, not dozens a day).

    That decision is only sound if the denominator is real. So a row is
    written for EVERY source on EVERY tick — `triggered=False` rows are the
    majority and are the entire point, not noise. A table holding only the
    moments something tripped would make the trigger RATE unrecoverable: you
    would know the numerator and be guessing the denominator, which is exactly
    the calibration error this phase exists to prevent.

    APPEND-ONLY, same contract as MacroCommodityBeta. Nothing here is ever
    UPDATEd or DELETEd. The observation window's value is destroyed by any
    rewrite of its own history.

    THRESHOLDS ARE SNAPSHOTTED, NOT REFERENCED
    ========================================================================
    trigger_threshold stores the numeric threshold IN FORCE AT THE MOMENT OF
    THE CHECK, copied onto the row. It is deliberately not read back from
    settings at query time. The whole purpose of the observation window is to
    change these constants afterwards; if the row pointed at a live setting,
    the first recalibration would retroactively rewrite what every historical
    row "meant", and the observation window's own evidence would be destroyed
    by the decision it was collected to inform.

    escalated IS A PLACEHOLDER AND IS ALWAYS FALSE IN THIS PHASE
    ========================================================================
    Stage B (the LLM call) is Phase 2.3 and DOES NOT EXIST YET. The column is
    written now so that the Phase-2.3 migration is not forced to alter a table
    that already holds real observation data. Nothing in this phase can set it
    True, and test_event_scanner_runner.py pins that.

    Not user-scoped, same reasoning as MacroCommodityBeta and MacroObservation:
    a world-state observation is public reference data, identical for every
    user, and is not private to whoever's process happened to observe it.
    """

    __tablename__ = "macro_event_detections"

    # Serves the two read patterns this phase has: the API's most-recent-first
    # page (detected_at), and the calibration question "how often did THIS
    # source/metric trip" (source, detected_at). Plain ascending, never DESC —
    # a DESC modifier makes this an EXPRESSION index that Alembic's
    # autogenerate cannot compare against a reflected schema, producing a
    # permanent false drift signal on every `alembic check`. That exact
    # mistake is documented at length on MacroCommodityBeta; a B-tree is
    # traversable in both directions, so ORDER BY detected_at DESC uses this
    # ascending index perfectly well.
    __table_args__ = (
        Index("ix_macro_event_detections_source_detected_at", "source", "detected_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # When the SCAN ran, not when any underlying event happened in the world.
    # A GDELT article window or an EDGAR filing carries its own timestamp
    # inside raw_metrics_json; conflating the two would make the observed
    # trigger rate a function of upstream publication lag rather than of this
    # scanner's own behaviour.
    detected_at: Mapped[datetime] = mapped_column(DateTime, index=True)

    # Which of the three independent Stage-A trigger sources produced this
    # row: one of drivers.SOURCE_* ("numeric", "gdelt", "edgar").
    #
    # EXACTLY ONE ROW PER SOURCE PER TICK, always three rows per tick, so a
    # tick is reconstructible as the rows sharing a detected_at and each
    # source's trigger rate is a straight count over its own rows. Writing one
    # row per SUBJECT instead would have duplicated the same full snapshot
    # blob 19 times for the numeric source alone; the subject-level detail
    # that a per-threshold calibration needs is inside raw_metrics_json, where
    # it is stored once.
    source: Mapped[str] = mapped_column(String(32), index=True)

    # WHICH SUBJECT TRIPPED, when one did — the driver_id ("oil_uso"), vol
    # metric key ("vix"), GDELT theme key ("energy") or EDGAR form type
    # ("8-K") that this row's headline trigger is attributed to.
    #
    # A source checks MANY subjects per tick (the numeric source alone checks
    # 19), so this names the single most significant trip — the one with the
    # largest exceedance over its own threshold — and NOT the complete set.
    # The per-subject detail for EVERY subject checked, tripped or not, lives
    # in raw_metrics_json, which is what a per-threshold calibration reads.
    #
    # NULL when nothing tripped, and also when the source failed before it
    # could attribute a subject (`error` distinguishes those two).
    driver: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # What the headline trigger measured: "daily_pct_change",
    # "daily_bps_change", "article_volume_zscore", "tone_shift",
    # "filing_count" — the constants in drivers.py. NULL whenever `driver` is.
    trigger_metric: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # The measured value and the threshold it was compared against, both as of
    # this check. NULL when the source errored and produced no measurement —
    # which is distinct from a measured 0.0 and must never be coerced to one,
    # the same missing-vs-measured discipline MacroCommodityBeta.beta_shock_days
    # documents.
    trigger_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    trigger_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Whether this source's check tripped on this tick. The column the whole
    # calibration decision is a rate over.
    triggered: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    # PLACEHOLDER FOR STAGE B (Phase 2.3), always False here — see the class
    # docstring. Not nullable: "Stage B did not escalate this" is a true
    # statement in this phase, not missing data.
    escalated: Mapped[bool] = mapped_column(Boolean, default=False)

    # The FULL snapshot for this source on this tick, as JSON text — every
    # metric read, not only the one that tripped. This is what makes the
    # observation window re-analysable against thresholds nobody has thought
    # of yet: a future calibration can replay "what WOULD have tripped at
    # 2.5% instead of 4%" without having needed to guess right in advance.
    #
    # Text rather than a JSON column type deliberately: this project runs
    # SQLite locally and Postgres in production, and sa.JSON's cross-dialect
    # behaviour differs (Postgres parses to dict, SQLite round-trips text).
    # Storing the serialized document keeps a row byte-identical on both, and
    # nothing in this phase queries INTO the JSON.
    raw_metrics_json: Mapped[str] = mapped_column(Text)

    # Set when this source's check FAILED (network timeout, malformed payload).
    # A failing source writes a row with triggered=False and this populated,
    # rather than writing nothing: a silent gap would be indistinguishable
    # from "checked and nothing tripped", and would quietly bias the observed
    # trigger rate downward — the fail-closed-per-source discipline this
    # project already applies elsewhere.
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
