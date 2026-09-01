from pydantic import BaseModel

# Server-authored and structurally non-optional on the response below, mirroring
# MACRO_BETA_EVIDENCE_DISCLAIMER: a field the API contract requires, so no
# frontend change can drop it.
#
# The wording is deliberately blunt about what a row here is and is not. During
# Phase 2.2 a "detection" is ONLY the record that an uncalibrated number
# crossed an arbitrary line. It is not a judgment, not a forecast, and not a
# recommendation, and nothing downstream of it exists yet.
MACRO_EVENT_EVIDENCE_DISCLAIMER = (
    "Stage-A mechanical detection log only. EVERY TRIGGER THRESHOLD BEHIND THESE "
    "ROWS IS AN UNCALIBRATED GUESS — none is derived from a measured "
    "distribution, a backtest, or any published result, because the data needed "
    "to calibrate them is what this phase is collecting. A `triggered=true` row "
    "therefore means only that a number crossed a line somebody guessed, NOT "
    "that a significant event occurred. No reasoning, judgment, or security "
    "selection has been applied: Stage B (the LLM reasoning step) is a later "
    "phase and does not exist yet, so `escalated` is always false here. Nothing "
    "in this phase can place a trade or spend money. Most rows are deliberately "
    "non-triggers: the full per-tick snapshot is recorded so that the real "
    "trigger RATE has an honest denominator, which is the only basis on which "
    "these thresholds will later be calibrated."
)


class MacroEventDetectionOut(BaseModel):
    id: int
    detected_at: str
    # One of "numeric", "gdelt", "edgar" — the three independent Stage-A
    # sources. A single tick appears as the rows sharing a detected_at.
    source: str
    # The specific subject checked within that source (a driver_id, a GDELT
    # theme key, or a watched EDGAR form type). None only when the source
    # failed before it could attribute a subject.
    driver: str | None
    trigger_metric: str | None
    # None means NOT MEASURED (the source errored), never a measured zero.
    trigger_value: float | None
    # The threshold in force AT THE MOMENT OF THE CHECK, snapshotted onto the
    # row — deliberately not read back from live settings, so recalibrating a
    # constant later never retroactively rewrites what this row meant.
    trigger_threshold: float | None
    triggered: bool
    # Placeholder for Stage B (Phase 2.3). Always false in this phase.
    escalated: bool
    # The FULL snapshot for this source on this tick, as a JSON string —
    # every metric read, not only the one that tripped, so a future
    # calibration can replay alternative thresholds against real history.
    raw_metrics_json: str
    # Populated when this source's check failed. The row still exists so a
    # failure is never silently indistinguishable from "nothing tripped".
    error: str | None


class MacroEventDetectionsResponse(BaseModel):
    detections: list[MacroEventDetectionOut]
    # Total matching rows, so a caller can page without guessing when to stop.
    total: int
    limit: int
    offset: int
    disclaimer: str
