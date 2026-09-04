from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class CrossSectionalForwardValidationRegistration(Base):
    """A standing decision to track one CROSS-SECTIONAL spec forward in real
    time, one real trading day at a time.

    WHY A PARALLEL TABLE RATHER THAN A TYPE DISCRIMINATOR ON
    forward_validation_registrations — the design decision this class is.
    Both were considered; the parallel table wins on three counts, and the
    third is decisive.

     1. NO COLUMN MEANS THE SAME THING IN BOTH. The pairs/momentum table's
        payload is ticker_a, ticker_b, fit_window_days, entry_z, exit_z —
        five NOT NULL columns, every one of which is meaningless for a
        cross-sectional spec, which has no pair, no fit window and no
        z-thresholds. A discriminator would mean making all five nullable
        (an ALTER on a live table whose rows are mid-flight) or filling them
        with sentinels. Sentinels in a table the live runner reads is how a
        silent mis-tick happens.
     2. THE CARRY STATE IS A DIFFERENT SHAPE. carry_state_json over there is
        a serialized engine.WalkForwardState (scalar position, one open
        trade). Here it is a serialized
        cross_sectional_forward.CrossSectionalForwardState (a dict of signed
        per-ticker weights, a formation clock, a pending turnover charge, a
        financing base). The same column name holding two incompatible
        schemas discriminated by a sibling column is exactly the ambiguity
        that makes a deserialization bug possible.
     3. THE LIVE PATH CANNOT SEE THESE ROWS AT ALL, and that is a proof, not
        a promise. ForwardValidationRunner._load_active_registrations selects
        from forward_validation_registrations filtered ONLY on status. Put
        cross-sectional rows in that table and every one of them is loaded
        by the live pairs runner until someone remembers to add a
        discriminator filter — i.e. correctness of the live, already-shipped
        mechanism would newly depend on a WHERE clause that did not exist
        before. A separate table makes that impossible by construction:
        the pairs runner's query is unchanged and structurally cannot
        return a row of this kind.

    Everything else deliberately mirrors ForwardValidationRegistration
    field-for-field (user-scoped like AlertRule, a (user_id, config_hash)
    uniqueness constraint, a snapshotted graduation threshold, the same
    status vocabulary plus one) so the two are obviously siblings."""

    __tablename__ = "cross_sectional_forward_validation_registrations"
    __table_args__ = (
        UniqueConstraint("user_id", "config_hash", name="uq_xs_forward_validation_user_config"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    # THE REFERENCE — see cross_sectional_forward_registry's module
    # docstring. These two strings are the source of truth: every tick
    # resolves them into the family's OWN spec object, so there is exactly
    # one declaration of the strategy and this row never duplicates it.
    family_key: Mapped[str] = mapped_column(String(50), index=True)
    pattern_id: Mapped[str] = mapped_column(String(80), index=True)
    # Where a reader should look to see that declaration, and what the spec
    # said it was — stored so the row is auditable without importing code.
    module_path: Mapped[str] = mapped_column(String(160))
    spec_family: Mapped[str] = mapped_column(String(60))
    citation: Mapped[str] = mapped_column(Text)
    # The eligibility rule in words. A data-driven universe's eligible SET
    # changes daily by design, so the rule is the only stable statement of
    # what universe this registration is trading.
    universe_rule: Mapped[str] = mapped_column(Text)
    # The family's own pre-declared DSR denominator at registration time —
    # the multiple-comparisons context a forward registration exists to get
    # past, kept on the row so it can never be quietly forgotten.
    family_n_trials: Mapped[int]

    config_hash: Mapped[str] = mapped_column(String(64))
    # Drift detection (see the registry module docstring): re-derived every
    # tick and compared. A mismatch parks the row in status "spec_drift"
    # rather than continuing to accumulate a track record that would be a
    # blend of two different strategies.
    spec_fingerprint: Mapped[str] = mapped_column(String(64))
    config_fingerprint: Mapped[str] = mapped_column(String(64))
    spec_snapshot_json: Mapped[str] = mapped_column(Text)
    config_snapshot_json: Mapped[str] = mapped_column(Text)

    # WHY this registration exists, in prose, written at registration time.
    # Not decoration: a forward-validation slot is a claim about which
    # hypothesis was worth real calendar time, and a row that cannot say why
    # it was created is indistinguishable from an automatic one.
    registration_rationale: Mapped[str] = mapped_column(Text)

    # "in_progress" | "forward_validated" | "underperforming" | "spec_drift"
    #   | "retired"
    # The first four are EARNED by the forward data (the runner writes them).
    # "retired" is written only by a deliberate human withdrawal of the
    # registration — see cross_sectional_forward_validation_service.
    # RETIRED_STATUS for why a withdrawal is a status transition rather than a
    # DELETE. No migration was needed to add it: this is a plain VARCHAR(30)
    # with no CHECK constraint and no enum type.
    status: Mapped[str] = mapped_column(String(30), default="in_progress", index=True)
    # Snapshotted at creation exactly as on the pairs path — a later change
    # to the threshold constants never retroactively alters an in-flight
    # registration. See cross_sectional_forward_validation_service.
    # graduation_threshold_for for why this is not simply
    # MIN_FORWARD_VALIDATION_TRADING_DAYS for a strategy that reforms every
    # holding_days rows rather than trading daily.
    min_trading_days_threshold: Mapped[int]
    # Counts REALIZED days only — a formation day with nothing yet to
    # realize against it is recorded in day_results_json but is not a day of
    # out-of-sample track record.
    n_forward_trading_days: Mapped[int] = mapped_column(default=0)
    n_formations: Mapped[int] = mapped_column(default=0)

    started_at: Mapped[date] = mapped_column(Date)
    last_processed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_ticked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    graduated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Serialized CrossSectionalForwardState (cross_sectional_forward.
    # serialize_cross_sectional_forward_state) — what lets a tick resume
    # holding exactly the book the previous tick left it holding.
    carry_state_json: Mapped[str] = mapped_column(Text)
    day_results_json: Mapped[str] = mapped_column(Text, default="[]")
    formations_json: Mapped[str] = mapped_column(Text, default="[]")
