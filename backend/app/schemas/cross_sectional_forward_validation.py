from typing import Literal

from pydantic import BaseModel, Field


class CrossSectionalForwardValidationRegisterRequest(BaseModel):
    """A registration is a REFERENCE to an already-declared spec, never a
    re-statement of one — see cross_sectional_forward_registry's module
    docstring. So the request body carries no signal parameters, no cost
    assumptions and no universe: those are resolved from the family's own
    registry at registration time, which is the only way the forward run and
    the backtest can be guaranteed to be the same strategy.

    `rationale` is required and has no default, deliberately. A
    forward-validation slot is a claim on real calendar time; a registration
    that cannot say why this hypothesis was worth it, out of its family's
    n_trials siblings, is indistinguishable from an automatic one."""

    family_key: str = Field(min_length=1, max_length=50)
    pattern_id: str = Field(min_length=1, max_length=80)
    rationale: str = Field(min_length=20, max_length=20_000)


class CrossSectionalForwardValidationRegistrationOut(BaseModel):
    id: int
    family_key: str
    pattern_id: str
    module_path: str
    spec_family: str
    citation: str
    universe_rule: str
    family_n_trials: int
    registration_rationale: str
    spec_snapshot: dict
    config_snapshot: dict
    # "retired" is the only member of this vocabulary a human puts there
    # rather than the runner — see cross_sectional_forward_validation_service.
    # RETIRED_STATUS. It must be listed here or the listing endpoint would
    # start 500ing on a row it can perfectly well describe.
    status: Literal[
        "in_progress", "forward_validated", "underperforming", "spec_drift", "retired"
    ]
    started_at: str
    last_processed_date: str | None
    n_forward_trading_days: int
    n_formations: int
    min_trading_days_threshold: int
    graduated_at: str | None
    # The book currently held, as counts rather than the full weight dicts —
    # the dicts live in carry_state_json and are auditable there.
    n_long: int
    n_short: int
    days_into_current_hold: int | None
    holding_days: int
    # None below MIN_FORWARD_DAYS_FOR_SHARPE realized days: a Sharpe off a
    # handful of returns misrepresents precision the data cannot support,
    # the same rule the pairs path applies.
    sharpe_forward_so_far: float | None
    periods_per_year: float
    equity: float
    is_system: bool


class CrossSectionalForwardValidationRegisterResponse(CrossSectionalForwardValidationRegistrationOut):
    created: bool


class CrossSectionalFamilyOut(BaseModel):
    family_key: str
    module_path: str
    universe_rule: str
    n_trials: int
    pattern_ids: list[str]
