"""THE DORMANT POOL — where a candidate that failed an UNDERPOWERED test
waits for the data to grow, instead of being closed.

WHY (measured, 2026-09-09). criteria_fix_2026-09-09 showed that at this
project's sample lengths 0 of 50 families had 80% power to detect a true
Sharpe of 0.5 at the 0.95 bar. A failure there is "not yet visible", not
"absent". The rule this module implements:

    An underpowered statistical failure cannot close a candidate. A failure
    from a test with >= dsr_power.POWER_FLOOR power at the claimed effect
    (a definite_negative whose scorecard `power` block passes) may close.
    Mechanism evidence (the mechanism is gone from the data, structurally
    untradeable, or the source itself predicts no forecastability) may
    close regardless of power.

HOW. The backtest window every family used grows by a month every month.
The EXTENSION SEGMENT — data after `window_end_at_entry` — is out-of-sample
for the frozen spec: the spec was selected on the original window, so no
selection happened on the extension. The pool's statistic is therefore

    PSR_ext = probabilistic_sharpe_ratio(SR_ext, 0, n_ext, skew_ext, kurt_ext)

on the frozen spec's realized net per-period returns over the CUMULATIVE
extension, with N = 1: one pre-registered spec, one pre-registered test,
nothing to deflate. deflated_sharpe.probabilistic_sharpe_ratio is called
as-is.

NO PEEKING. Looks happen only when the extension reaches k * LOOK_PERIODS
observations of the family's own calendar, k = 1..K_MAX. Promotion at look k
requires PSR_ext >= C_K[bucket], a CONSTANT per-look boundary calibrated by
simulation so that a true-zero edge is promoted at ANY of the K_MAX looks
with probability <= ALPHA — nothing here is a published group-sequential
formula implemented from memory; the boundary is the empirical (1-ALPHA)
quantile of max_k PSR_ext,k over 20 000 null paths, and tests read it back
from the committed run output so it cannot drift from what was validated.
The naive alternative (look at the 0.95 bar every year, promote the first
time it clears) has a 17% family-wise false-promotion rate under a pure
null; that is exactly the kill-switch error in reverse.

TWO BUCKETS, chosen at ENTRY from the ORIGINAL window (so the choice cannot
peek at the extension): LOW (lag-1 autocorrelation phi_hat <= PHI_BUCKET_CUT)
covers 98% of the project's persisted spec series (95th percentile 0.070,
max 0.247, none >= 0.3); HIGH keeps a boundary calibrated at phi = 0.3. See
data/research_runs/dormant_pool_2026-09-09/ for the pre-registration, the
amendment that introduced the buckets, the three gate runs (run 1 FAILED
under AR(1) and is kept), and the result memo.

WHAT PROMOTION IS. A move to Active — a forward-tracking slot. It is NOT a
pass to capital: the capital bar (DSR >= 0.95 at the highest ladder rung,
every other scorecard layer) is untouched by this module.

WHAT THIS MODULE DOES NOT DO. It does not re-run any family. Re-scoring
needs a reproducible runner per family; an entry without one is recorded
rescorable=False and never evaluated — recorded, not silently skipped. It
does not decide who enters: every entry in the manifest is an owner
decision, and the manifest ships empty.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.services.research_lab.deflated_sharpe import (
    compute_return_stats,
    probabilistic_sharpe_ratio,
)
from app.services.research_lab.metrics import TRADING_DAYS_PER_YEAR

SCHEMA = "dormant_pool/v1"
MANIFEST_PATH = Path(__file__).resolve().parents[3] / "data" / "research_runs" / "dormant_pool_2026-09-09" / "dormant_pool_manifest.json"
GATES_OUTPUT_PATH = Path(__file__).resolve().parents[3] / "data" / "research_runs" / "dormant_pool_2026-09-09" / "dormant_pool_gates_output.txt"

ALPHA = 0.05
K_MAX = 10
# One look per year of the family's OWN calendar: 252 observations for an
# exchange-calendar family, 365 for a 24/7 one. Expressed as a fraction of
# periods_per_year so the two never disagree with the family's snapshot.
LOOK_YEARS = 1.0
PHI_BUCKET_CUT = 0.10

BUCKET_LOW = "LOW"
BUCKET_HIGH = "HIGH"

# Run 3 of dormant_pool_gates.py (seed 20260909, 20 000 null paths per
# model). LOW = max over {normal, t(4), AR(1) 0.1}; HIGH = AR(1) 0.3.
# tests/test_dormant_pool.py parses dormant_pool_gates_output.txt and fails
# if these constants differ from what that run printed.
C_K = {BUCKET_LOW: 0.99397, BUCKET_HIGH: 0.99894}

PLACEHOLDER_PATTERNS = (
    re.compile(r"^\s*$"),
    re.compile(r"\bTODO\b", re.IGNORECASE),
    re.compile(r"\bTBD\b", re.IGNORECASE),
    re.compile(r"<[^>]*>"),
)


class DormantPoolError(ValueError):
    """The manifest or an entry is unusable. Raised, never defaulted: a
    silently-defaulted pool entry would promote or park a family on a field
    nobody wrote."""


def assign_bucket(phi_hat_entry: float) -> str:
    if not np.isfinite(phi_hat_entry):
        raise DormantPoolError(f"phi_hat_entry must be finite, got {phi_hat_entry}")
    return BUCKET_LOW if phi_hat_entry <= PHI_BUCKET_CUT else BUCKET_HIGH


def lag1_autocorrelation(returns: pd.Series) -> float:
    """phi_hat on the ORIGINAL-window net returns, measured at entry."""
    x = pd.Series(returns, dtype=float).dropna().to_numpy()
    if len(x) < 3:
        raise DormantPoolError(f"need >= 3 observations for lag-1 autocorrelation, got {len(x)}")
    x = x - x.mean()
    denom = float(np.dot(x, x))
    if denom == 0:
        raise DormantPoolError("degenerate (constant) return series")
    return float(np.dot(x[:-1], x[1:]) / denom)


@dataclass(frozen=True)
class DormantEntry:
    family_key: str
    pattern_id: str
    spec_fingerprint: str
    config_fingerprint: str
    window_end_at_entry: date
    entered_at: date
    periods_per_year: float
    phi_hat_entry: float
    bucket: str
    pit_ok: bool
    rescorable: bool
    mechanism_review: str  # where the "mechanism not shown absent" finding is recorded
    entry_rationale: str

    @property
    def look_periods(self) -> int:
        return round(LOOK_YEARS * self.periods_per_year)

    @property
    def boundary(self) -> float:
        return C_K[self.bucket]


@dataclass(frozen=True)
class LookResult:
    n_extension: int
    look_index: int  # 0 = no look due yet
    psr_ext: float | None
    sharpe_ext_annualized: float | None
    boundary: float
    promoted: bool
    note: str


def evaluate_look(extension_net_returns: pd.Series, entry: DormantEntry) -> LookResult:
    """The pool's one decision. `extension_net_returns` is the frozen spec's
    realized net per-period returns strictly AFTER window_end_at_entry, in
    order. PSR_ext is displayed whenever >= 2 observations exist; a
    PROMOTION can only happen at a scheduled look (n_ext >= k * look_periods,
    k <= K_MAX), and never for an entry whose data path is not point-in-time
    or which has no reproducible runner."""
    x = pd.Series(extension_net_returns, dtype=float).dropna()
    n = len(x)
    look_index = min(n // entry.look_periods, K_MAX) if entry.look_periods > 0 else 0

    psr = None
    sharpe_ann = None
    stats = compute_return_stats(x) if n >= 2 else None
    if stats is not None:
        sr = float(x.mean() / x.std(ddof=1))
        if np.isfinite(sr):
            psr = probabilistic_sharpe_ratio(sr, 0.0, stats.n, stats.skewness, stats.kurtosis)
            sharpe_ann = sr * float(np.sqrt(entry.periods_per_year))

    if not entry.rescorable:
        return LookResult(n, look_index, psr, sharpe_ann, entry.boundary, False, "not rescorable: no reproducible runner recorded")
    if not entry.pit_ok:
        return LookResult(n, look_index, psr, sharpe_ann, entry.boundary, False, "pit_ok is false: extension data path not point-in-time; displayed only")
    if look_index == 0:
        return LookResult(n, look_index, psr, sharpe_ann, entry.boundary, False, f"no look due: {n} < {entry.look_periods} extension observations")
    if psr is None:
        return LookResult(n, look_index, psr, sharpe_ann, entry.boundary, False, "PSR_ext unmeasurable (degenerate series)")
    promoted = psr >= entry.boundary
    return LookResult(
        n, look_index, psr, sharpe_ann, entry.boundary, promoted,
        f"look {look_index}/{K_MAX}: PSR_ext {psr:.5f} {'>=' if promoted else '<'} C_K[{entry.bucket}] {entry.boundary:.5f}",
    )


# --- manifest ---------------------------------------------------------------


def _require(payload: dict[str, Any], key: str, where: str) -> Any:
    if key not in payload:
        raise DormantPoolError(f"{where}: required field {key!r} is missing")
    return payload[key]


def _require_text(payload: dict[str, Any], key: str, where: str) -> str:
    value = _require(payload, key, where)
    if not isinstance(value, str):
        raise DormantPoolError(f"{where}.{key}: expected a string")
    for pattern in PLACEHOLDER_PATTERNS:
        if pattern.search(value):
            raise DormantPoolError(f"{where}.{key} is still a placeholder ({value!r})")
    return value


def _require_bool(payload: dict[str, Any], key: str, where: str) -> bool:
    value = _require(payload, key, where)
    if not isinstance(value, bool):
        raise DormantPoolError(f"{where}.{key}: expected true or false, got {value!r}")
    return value


def _require_number(payload: dict[str, Any], key: str, where: str) -> float:
    value = _require(payload, key, where)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DormantPoolError(f"{where}.{key}: expected a number, got {value!r}")
    return float(value)


def parse_entry(payload: dict[str, Any], where: str = "<entry>") -> DormantEntry:
    phi = _require_number(payload, "phi_hat_entry", where)
    bucket = _require_text(payload, "bucket", where)
    if bucket not in C_K:
        raise DormantPoolError(f"{where}.bucket must be one of {sorted(C_K)}, got {bucket!r}")
    if bucket != assign_bucket(phi):
        raise DormantPoolError(
            f"{where}.bucket says {bucket!r} but phi_hat_entry={phi} assigns {assign_bucket(phi)!r} "
            f"(cut {PHI_BUCKET_CUT}). The bucket is computed from the entry-time phi, never chosen."
        )
    ppy = _require_number(payload, "periods_per_year", where)
    if ppy <= 0:
        raise DormantPoolError(f"{where}.periods_per_year must be positive")
    try:
        window_end = date.fromisoformat(_require_text(payload, "window_end_at_entry", where))
        entered = date.fromisoformat(_require_text(payload, "entered_at", where))
    except ValueError as exc:
        raise DormantPoolError(f"{where}: dates must be ISO YYYY-MM-DD") from exc
    if entered < window_end:
        raise DormantPoolError(f"{where}: entered_at {entered} precedes window_end_at_entry {window_end}")
    return DormantEntry(
        family_key=_require_text(payload, "family_key", where),
        pattern_id=_require_text(payload, "pattern_id", where),
        spec_fingerprint=_require_text(payload, "spec_fingerprint", where),
        config_fingerprint=_require_text(payload, "config_fingerprint", where),
        window_end_at_entry=window_end,
        entered_at=entered,
        periods_per_year=ppy,
        phi_hat_entry=phi,
        bucket=bucket,
        pit_ok=_require_bool(payload, "pit_ok", where),
        rescorable=_require_bool(payload, "rescorable", where),
        mechanism_review=_require_text(payload, "mechanism_review", where),
        entry_rationale=_require_text(payload, "entry_rationale", where),
    )


def load_manifest(path: Path | None = None) -> list[DormantEntry]:
    path = path or MANIFEST_PATH
    payload = json.loads(path.read_text())
    if payload.get("schema") != SCHEMA:
        raise DormantPoolError(f"{path}: declares schema {payload.get('schema')!r}, this module reads {SCHEMA!r}")
    entries_raw = payload.get("entries")
    if not isinstance(entries_raw, list):
        raise DormantPoolError(f"{path}: 'entries' must be a list")
    entries = [parse_entry(e, f"{path}.entries[{i}]") for i, e in enumerate(entries_raw)]
    keys = [(e.family_key, e.pattern_id) for e in entries]
    if len(set(keys)) != len(keys):
        raise DormantPoolError(f"{path}: duplicate (family_key, pattern_id) entries")
    return entries


def boundaries_from_gate_output(path: Path | None = None) -> dict[str, float]:
    """Read C_K back from the committed run output — the test that C_K
    above equals what was actually validated."""
    text = (path or GATES_OUTPUT_PATH).read_text()
    found: dict[str, float] = {}
    for line in text.splitlines():
        m = re.search(r"boundary C_K\[(LOW|HIGH) [^\]]*\] = ([0-9.]+)", line)
        if m:
            found[m.group(1)] = float(m.group(2))
    if set(found) != set(C_K):
        raise DormantPoolError(f"gate output {path or GATES_OUTPUT_PATH} does not print both boundaries; found {found}")
    return found


__all__ = [
    "ALPHA",
    "BUCKET_HIGH",
    "BUCKET_LOW",
    "C_K",
    "K_MAX",
    "LOOK_YEARS",
    "PHI_BUCKET_CUT",
    "TRADING_DAYS_PER_YEAR",
    "DormantEntry",
    "DormantPoolError",
    "LookResult",
    "assign_bucket",
    "boundaries_from_gate_output",
    "evaluate_look",
    "lag1_autocorrelation",
    "load_manifest",
    "parse_entry",
]
