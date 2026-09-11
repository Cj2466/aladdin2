"""RULE-FREE PATTERN SCAN vs. PLACEBO — the scanner, the two placebos, and
the two mechanical gates of `data/research_runs/pattern_scan_2026-09-11/`.

This module is NOT a candidate signal family. It implements one
pre-registered experiment whose contract is
`data/research_runs/pattern_scan_2026-09-11/PREREGISTRATION.md` (written and
merged before any scan was run) as amended by
`ADDENDUM_01_PLACEBO_TARGET_AND_UNDERSPECIFIED_POINTS.md` in the same
directory. Every constant below is quoted from a numbered section of that
pre-registration; none of them may be changed now that real-arm numbers
exist (§8). Where this module had to decide something the pre-registration
left open, the decision is in ADDENDUM 01, dated before the first number,
and the docstring here names the addendum item rather than re-arguing it.

WHAT IS BEING TESTED (§1). The owner's hypothesis is that scanning the price
chart for recurring shapes, without imposing a theory, finds what is really
there. The alternative this must beat is that the patterns a scanner finds
live in the scanner and in noise. So every statistic below is computed twice
by the SAME code path: once on the real return matrix, and once on each of
40 placebo matrices (20 sign-flip draws, 20 time-shuffle draws) that
preserve everything about the data except time-ordered information.
"Beyond the envelope" means above the maximum of the 20 draws, an empirical
p < 1/21 under exchangeability (§5).

THE ALPHABET (§3), stated once and not tuned:
    r_{i,t} = close_t / close_{t-1} - 1
    sigma_{i,t} = sample std (ddof=1) of r over the 20 bars strictly before t
    z_{i,t} = r_{i,t} / sigma_{i,t}
    b_{i,t} = D if z < -0.5 ; F if -0.5 <= z <= 0.5 ; U if z > 0.5
    pattern = the ordered tuple (b_{t-k+1}, ..., b_t), k in {3, 5, 8}
             = 27 + 243 + 6561 = 6831 patterns per panel
No other feature (volume, level, trend, calendar) enters, by design.

THE OUTCOME (§3) is cross-sectionally demeaned:
    y_{i,t+1} = r_{i,t+1} - mean_j r_{j,t+1} over names alive at t+1
so a pattern has to predict RELATIVE movement; market drift and
survivorship-induced drift leave both arms alike. Primary horizon h = 1;
h = 5 (sum of the next five demeaned returns) is reported, not gating (§6).

THE STATISTIC (§3) is t_p = mean(R_p) / NeweyWest-SE(R_p, lag = h), where
R_p is the equal-weight average of y_{i,t+1} over the names carrying pattern
p at t. The HAC estimator is the ordinary Newey-West (1987) Bartlett-kernel
variance of a sample mean; `newey_west_t_of_mean` is validated against
statsmodels' own HAC in `tests/test_pattern_scan_placebo.py` rather than
trusted as a transcription (CLAUDE.md: never a formula from memory).

WHY THE HOLDOUT IS A SEPARATE CALL. `run_discovery` never touches the
holdout window; `run_holdout` refuses to run without a discovery result
handed to it. That is a structural guarantee of §4's "the holdout is touched
exactly once, after §5 is complete and committed", not a convention.
"""

from __future__ import annotations

import hashlib
import json
import warnings
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Constants quoted from PREREGISTRATION.md. None is tunable (§8).
# ---------------------------------------------------------------------------

SIGMA_WINDOW = 20          # §3 "the 20 bars strictly before t"; §2 burn-in
Z_THRESHOLD = 0.5          # §3 "D if z < -0.5, F if -0.5 <= z <= 0.5, U if z > 0.5"
K_VALUES: tuple[int, ...] = (3, 5, 8)   # §3
N_BINS = 3                 # D / F / U -> base-3 encoding (§3)
BIN_LETTERS = ("D", "F", "U")
TOTAL_PATTERNS = sum(N_BINS**k for k in K_VALUES)   # 6831 (§3)

HORIZON_PRIMARY = 1        # §3 "Primary horizon h = 1 bar"
HORIZON_SECONDARY = 5      # §3 "Secondary h = 5 bars ... reported, not gating"
HORIZONS: tuple[int, ...] = (HORIZON_PRIMARY, HORIZON_SECONDARY)

N_PLACEBO_DRAWS = 20       # §5 "20 seeded draws of each (seeds 1...20)"
PLACEBO_SEEDS: tuple[int, ...] = tuple(range(1, N_PLACEBO_DRAWS + 1))

TOP_N_HOLDOUT = 20         # §6 "the 20 measurable patterns with the largest |t_p|"
GATE1_T_THRESHOLDS = (3.0, 4.0)   # §6 N3 / N4
GATE2_T_FLOOR = 2.0        # §6 "PASS iff t(H_real) >= 2.0 AND ..."

NON_DEGENERACY_MAX_IDENTICAL_FRACTION = 0.05   # §5 control non-degeneracy proof

ARM_REAL = "real"
ARM_P1 = "P1_sign_flip"
ARM_P2 = "P2_time_shuffle"


@dataclass(frozen=True)
class PanelSpec:
    """The per-panel numbers §2/§3/§4/§6 fix. Constructed only by the two
    module-level constants below; a caller does not get to invent a panel."""

    key: str
    label: str
    min_names: int            # §3 measurability: names required on a bar
    min_bars: int             # §3 measurability: bars required in discovery
    periods_per_year: float   # §3 "252 for E, 8760 for C"
    cost_bp_one_way: float    # §6 "5 bp one-way on E and 10 bp on C"
    discovery_start: str      # §4
    discovery_end: str
    holdout_start: str
    holdout_end: str


PANEL_E = PanelSpec(
    key="E",
    label="US equities, daily (point-in-time price store)",
    min_names=10,
    min_bars=250,
    periods_per_year=252.0,
    cost_bp_one_way=5.0,
    discovery_start="2016-01-04",
    discovery_end="2022-12-31",
    holdout_start="2023-01-03",
    holdout_end="2026-09-08",
)

PANEL_C = PanelSpec(
    key="C",
    label="Binance spot, hourly",
    min_names=5,
    min_bars=2000,
    periods_per_year=8760.0,
    cost_bp_one_way=10.0,
    discovery_start="2019-09-08",
    discovery_end="2023-12-31",
    holdout_start="2024-01-01",
    holdout_end="2026-09-11",
)


# ---------------------------------------------------------------------------
# 1. Pattern encoding (§3) — base-3, most recent bin least significant.
# ---------------------------------------------------------------------------

def pattern_offset(k: int) -> int:
    """Where pattern ids for this k start, so the three k blocks concatenate
    into one 0..6830 id space: k=3 -> 0..26, k=5 -> 27..269, k=8 -> 270..6830."""
    if k not in K_VALUES:
        raise ValueError(f"k={k} is not one of the pre-registered {K_VALUES}")
    return sum(N_BINS**j for j in K_VALUES if j < k)


def encode_pattern(bins: Sequence[int]) -> int:
    """Base-3 code of the ordered tuple (b_{t-k+1}, ..., b_t): the LAST bin
    (the most recent bar) is the least significant digit, so the same digit
    weight 3**j always means "j bars ago" regardless of k."""
    code = 0
    for j, b in enumerate(reversed(bins)):   # j = 0 is b_t
        if b not in (0, 1, 2):
            raise ValueError(f"bin {b!r} is not one of 0/1/2 (D/F/U)")
        code += int(b) * (N_BINS**j)
    return code


def decode_pattern(code: int, k: int) -> tuple[int, ...]:
    """Inverse of `encode_pattern` — the round trip is asserted in the tests."""
    if not 0 <= code < N_BINS**k:
        raise ValueError(f"code {code} out of range for k={k}")
    digits = []
    for _ in range(k):
        digits.append(code % N_BINS)
        code //= N_BINS
    return tuple(reversed(digits))          # (b_{t-k+1}, ..., b_t)


def pattern_label(code: int, k: int) -> str:
    """'UUU', 'DFFUD', ... — the human-readable form used in the CSVs."""
    return "".join(BIN_LETTERS[b] for b in decode_pattern(code, k))


def pattern_id(code: int, k: int) -> int:
    return pattern_offset(k) + int(code)


def split_pattern_id(pid: int) -> tuple[int, int]:
    for k in K_VALUES:
        off = pattern_offset(k)
        if off <= pid < off + N_BINS**k:
            return k, pid - off
    raise ValueError(f"pattern id {pid} is outside 0..{TOTAL_PATTERNS - 1}")


# ---------------------------------------------------------------------------
# 2. Newey-West HAC t of a sample mean.
# ---------------------------------------------------------------------------

def newey_west_t_of_mean(x: np.ndarray, lag: int) -> tuple[float, float, float]:
    """(t, mean, HAC standard error) for the mean of `x`, Bartlett kernel,
    truncation `lag` — the Newey-West (1987) HAC variance of an OLS
    regression on a constant, which is what §3's "NeweyWest-SE(R_p, lag = h)"
    is. Written out rather than called from statsmodels because it runs
    ~300k times per panel; `test_newey_west_matches_statsmodels_hac` pins it
    against statsmodels' own HAC so this is a validated transcription, not a
    remembered one.

    `x` must already be the gap-free sequence of realized bars (ADDENDUM 01
    item B: autocovariances are taken over consecutive REALIZATIONS).
    Returns (nan, mean, nan) when the sample is too short for the lag or the
    HAC long-run variance comes out non-positive, rather than a number that
    would silently be garbage."""
    x = np.asarray(x, dtype=float)
    n = x.size
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    mean = float(x.mean())
    if n < max(lag + 2, 3):
        return float("nan"), mean, float("nan")
    e = x - mean
    s = float(e @ e) / n                       # gamma_0
    for l in range(1, min(lag, n - 1) + 1):
        weight = 1.0 - l / (lag + 1.0)         # Bartlett
        s += 2.0 * weight * float(e[l:] @ e[:-l]) / n
    if not np.isfinite(s) or s <= 0.0:
        return float("nan"), mean, float("nan")
    se = float(np.sqrt(s / n))
    if se == 0.0:
        return float("nan"), mean, se
    return mean / se, mean, se


def annualized_sharpe(x: np.ndarray, periods_per_year: float) -> float:
    x = np.asarray(x, dtype=float)
    if x.size < 2:
        return float("nan")
    sd = float(x.std(ddof=1))
    if not np.isfinite(sd) or sd == 0.0:
        return float("nan")
    return float(x.mean()) / sd * float(np.sqrt(periods_per_year))


# ---------------------------------------------------------------------------
# 3. Panel object: returns in, bins/outcomes derived by the SAME code path
#    for every arm (ADDENDUM 01 item A).
# ---------------------------------------------------------------------------

@dataclass
class ScanPanel:
    """One arm's return matrix plus everything the scanner derives from it.

    `returns` is (T, N) with NaN wherever a name has no usable return on that
    bar. Rows are bars in ascending time order, columns are names. The real
    arm passes the raw returns; a placebo arm passes a transform of the SAME
    raw returns, and every derived quantity below is recomputed identically
    (ADDENDUM 01 item A)."""

    dates: pd.DatetimeIndex
    names: tuple[str, ...]
    returns: np.ndarray
    codes: dict[int, np.ndarray] = field(default_factory=dict)     # k -> (T,N) int64, -1 invalid
    outcomes: dict[int, np.ndarray] = field(default_factory=dict)  # h -> (T,N) float, NaN invalid

    @property
    def n_bars(self) -> int:
        return len(self.dates)

    @property
    def n_names(self) -> int:
        return len(self.names)


def cross_sectional_demeaned(returns: np.ndarray) -> np.ndarray:
    """y_{i,t} = r_{i,t} - mean_j r_{j,t} over the names alive at t (§3).
    A bar with no live name yields all-NaN rather than a divide-by-zero."""
    with np.errstate(invalid="ignore"), warnings.catch_warnings():
        # An all-NaN bar (every name dead) is a legitimate state here, not a
        # defect; nanmean's "Mean of empty slice" warning would be noise.
        warnings.simplefilter("ignore", RuntimeWarning)
        row_mean = np.nanmean(np.where(np.isfinite(returns), returns, np.nan), axis=1)
    return returns - row_mean[:, None]


def rolling_sigma(returns: np.ndarray, window: int = SIGMA_WINDOW) -> np.ndarray:
    """sigma_{i,t} = sample std (ddof=1) of r over the `window` bars STRICTLY
    before t, requiring all `window` of them to exist (§3; ADDENDUM 01 F).
    pandas' default min_periods == window is exactly that requirement, and
    the shift(1) is what makes it strictly prior."""
    frame = pd.DataFrame(returns)
    return frame.rolling(window).std(ddof=1).shift(1).to_numpy()


def bin_matrix(returns: np.ndarray) -> np.ndarray:
    """(T, N) int8 of D=0 / F=1 / U=2, -1 where z is undefined (§3)."""
    sigma = rolling_sigma(returns)
    with np.errstate(invalid="ignore", divide="ignore"):
        z = np.divide(returns, sigma, out=np.full_like(returns, np.nan), where=np.isfinite(sigma) & (sigma > 0.0))
    bins = np.full(returns.shape, -1, dtype=np.int8)
    ok = np.isfinite(z)
    bins[ok & (z < -Z_THRESHOLD)] = 0
    bins[ok & (z >= -Z_THRESHOLD) & (z <= Z_THRESHOLD)] = 1
    bins[ok & (z > Z_THRESHOLD)] = 2
    return bins


def code_matrix(bins: np.ndarray, k: int) -> np.ndarray:
    """(T, N) int64 base-3 code of the last k bins ending at t, -1 where any
    of the k bins is missing. Vectorised as a rolling base-3 sum: digit
    weight 3**j is the bin j bars ago, matching `encode_pattern`."""
    n_rows = bins.shape[0]
    code = np.zeros(bins.shape, dtype=np.int64)
    valid = np.ones(bins.shape, dtype=bool)
    for j in range(k):
        shifted = np.full(bins.shape, -1, dtype=np.int8)
        if j == 0:
            shifted = bins
        elif j < n_rows:
            shifted[j:] = bins[: n_rows - j]
        valid &= shifted >= 0
        code += np.where(shifted >= 0, shifted.astype(np.int64), 0) * (N_BINS**j)
    return np.where(valid, code, -1)


def forward_outcome(demeaned: np.ndarray, h: int) -> np.ndarray:
    """(T, N): the outcome attached to FORMATION bar t, i.e. y_{t+1} for
    h = 1 and sum(y_{t+1..t+h}) for h > 1 (§3). NaN where any of the h bars
    is missing, so a partially-observed sum never enters a statistic."""
    n_rows = demeaned.shape[0]
    out = np.zeros(demeaned.shape, dtype=float)
    ok = np.ones(demeaned.shape, dtype=bool)
    for step in range(1, h + 1):
        shifted = np.full(demeaned.shape, np.nan)
        if step < n_rows:
            shifted[: n_rows - step] = demeaned[step:]
        ok &= np.isfinite(shifted)
        out += np.where(np.isfinite(shifted), shifted, 0.0)
    return np.where(ok, out, np.nan)


def build_panel(dates: pd.DatetimeIndex, names: Sequence[str], returns: np.ndarray) -> ScanPanel:
    """Everything the scanner needs, derived once per arm by one code path."""
    panel = ScanPanel(dates=pd.DatetimeIndex(dates), names=tuple(names), returns=np.asarray(returns, dtype=float))
    bins = bin_matrix(panel.returns)
    for k in K_VALUES:
        panel.codes[k] = code_matrix(bins, k)
    demeaned = cross_sectional_demeaned(panel.returns)
    for h in HORIZONS:
        panel.outcomes[h] = forward_outcome(demeaned, h)
    return panel


# ---------------------------------------------------------------------------
# 4. Placebos (§5). Applied to the raw return matrix; see ADDENDUM 01 item A.
# ---------------------------------------------------------------------------

def sign_flip(returns: np.ndarray, seed: int) -> np.ndarray:
    """P1 — every r_{i,t} times an independent +-1 (§5). Magnitudes, the
    NaN mask (so each name's history length) and the cross-sectional
    dispersion of |r| survive; every form of sign predictability does not."""
    rng = np.random.default_rng(seed)
    flips = rng.integers(0, 2, size=returns.shape).astype(float) * 2.0 - 1.0
    return returns * flips


def time_shuffle(returns: np.ndarray, seed: int) -> np.ndarray:
    """P2 — each name's return series independently permuted in time (§5).
    Only the observed entries are permuted among the observed positions, so
    each name's history length and NaN mask are preserved exactly while all
    temporal structure, volatility clustering included, is destroyed."""
    rng = np.random.default_rng(seed)
    out = np.array(returns, dtype=float, copy=True)
    for col in range(out.shape[1]):
        column = out[:, col]
        idx = np.flatnonzero(np.isfinite(column))
        if idx.size > 1:
            column[idx] = column[idx[rng.permutation(idx.size)]]
    return out


PLACEBOS = {ARM_P1: sign_flip, ARM_P2: time_shuffle}


def placebo_returns(returns: np.ndarray, arm: str, seed: int) -> np.ndarray:
    if arm == ARM_REAL:
        return returns
    if arm not in PLACEBOS:
        raise ValueError(f"unknown arm {arm!r}; expected one of {[ARM_REAL, *PLACEBOS]}")
    return PLACEBOS[arm](returns, seed)


# ---------------------------------------------------------------------------
# 5. The scan itself.
# ---------------------------------------------------------------------------

@dataclass
class PatternStat:
    pattern_id: int
    k: int
    code: int
    label: str
    t_stat: float
    mean: float
    sharpe_annualized: float
    n_bars: int
    mean_names: float


@dataclass
class ScanResult:
    """One (panel, arm, horizon) discovery scan."""

    panel_key: str
    arm: str
    seed: int
    horizon: int
    window: str
    n_formation_bars: int
    n_measurable: int
    n_unmeasurable: int
    n_t_ge_3: int
    n_t_ge_4: int
    t_max_abs: float
    sigma_sr_annualized: float
    patterns: list[PatternStat]

    def top(self, n: int) -> list[PatternStat]:
        ranked = sorted(
            (p for p in self.patterns if np.isfinite(p.t_stat)),
            key=lambda p: abs(p.t_stat),
            reverse=True,
        )
        return ranked[:n]


def _window_mask(dates: pd.DatetimeIndex, start: str, end: str) -> np.ndarray:
    return np.asarray((dates >= pd.Timestamp(start)) & (dates <= pd.Timestamp(end)), dtype=bool)


def _formation_mask(window_mask: np.ndarray, h: int) -> np.ndarray:
    """Formation bars whose WHOLE outcome window t+1..t+h also sits in the
    window (ADDENDUM 01 item D) — this is what stops the last discovery bar
    from reading the first holdout bar's return."""
    mask = window_mask.copy()
    for step in range(1, h + 1):
        shifted = np.zeros_like(window_mask)
        if step < window_mask.size:
            shifted[: window_mask.size - step] = window_mask[step:]
        mask &= shifted
    return mask


def _cell_table(codes: np.ndarray, outcome: np.ndarray, rows: np.ndarray, n_codes: int):
    """Group the valid (bar, pattern) cells of one k.

    Returns (bar_index, code, cell_mean, cell_count) with the cells sorted by
    (bar, code) — which `np.unique` gives for free, because the key is
    bar * n_codes + code. Grouping by sorting rather than a dense
    (T x n_codes) accumulator is what keeps the hourly crypto panel
    (61k bars x 6561 codes) inside memory."""
    sub_codes = codes[rows]
    sub_outcome = outcome[rows]
    valid = (sub_codes >= 0) & np.isfinite(sub_outcome)
    if not valid.any():
        empty_i = np.zeros(0, dtype=np.int64)
        return empty_i, empty_i, np.zeros(0), empty_i
    bar_idx, _ = np.nonzero(valid)
    keys = bar_idx.astype(np.int64) * n_codes + sub_codes[valid].astype(np.int64)
    values = sub_outcome[valid].astype(float)
    uniq, inverse, counts = np.unique(keys, return_inverse=True, return_counts=True)
    sums = np.bincount(inverse, weights=values, minlength=uniq.size)
    return uniq // n_codes, uniq % n_codes, sums / counts, counts


def _series_by_code(code_of_cell: np.ndarray, cell_mean: np.ndarray, cell_count: np.ndarray, bar_of_cell: np.ndarray):
    """Regroup time-ordered cells into one time-ordered series per code.
    `code_of_cell` arrives sorted by (bar, code), so a STABLE sort on code
    leaves each code's cells in ascending bar order."""
    order = np.argsort(code_of_cell, kind="stable")
    codes_sorted = code_of_cell[order]
    uniq_codes, starts, counts = np.unique(codes_sorted, return_index=True, return_counts=True)
    return uniq_codes, starts, counts, order, cell_mean[order], cell_count[order], bar_of_cell[order]


def scan_window(
    panel: ScanPanel,
    spec: PanelSpec,
    *,
    horizon: int,
    window: tuple[str, str],
    window_label: str,
    arm: str = ARM_REAL,
    seed: int = 0,
    min_bars: int | None = None,
) -> ScanResult:
    """Every measurable pattern's t, Sharpe, bar count and mean membership
    over one window. `min_bars=None` uses the pre-registered discovery floor;
    the holdout call passes 1, because the bar floor is a discovery-window
    SELECTION rule and is not re-applied out of sample (ADDENDUM 01 item G)."""
    bar_floor = spec.min_bars if min_bars is None else int(min_bars)
    window_mask = _window_mask(panel.dates, *window)
    formation = _formation_mask(window_mask, horizon)
    rows = np.flatnonzero(formation)
    outcome = panel.outcomes[horizon]

    stats: list[PatternStat] = []
    n_unmeasurable = 0
    for k in K_VALUES:
        n_codes = N_BINS**k
        bar_of, code_of, cell_mean, cell_count = _cell_table(panel.codes[k], outcome, rows, n_codes)
        keep = cell_count >= spec.min_names
        if not keep.any():
            n_unmeasurable += n_codes
            continue
        bar_of, code_of, cell_mean, cell_count = bar_of[keep], code_of[keep], cell_mean[keep], cell_count[keep]
        uniq_codes, starts, counts, _order, means_sorted, counts_sorted, _bars_sorted = _series_by_code(
            code_of, cell_mean, cell_count, bar_of
        )
        n_measurable_k = 0
        for code, start, count in zip(uniq_codes, starts, counts):
            if count < bar_floor:
                continue
            n_measurable_k += 1
            series = means_sorted[start : start + count]
            t_stat, mean, _se = newey_west_t_of_mean(series, horizon)
            stats.append(
                PatternStat(
                    pattern_id=pattern_id(int(code), k),
                    k=k,
                    code=int(code),
                    label=pattern_label(int(code), k),
                    t_stat=float(t_stat),
                    mean=float(mean),
                    sharpe_annualized=annualized_sharpe(series, spec.periods_per_year),
                    n_bars=int(count),
                    mean_names=float(counts_sorted[start : start + count].mean()),
                )
            )
        n_unmeasurable += n_codes - n_measurable_k

    finite_t = np.array([abs(p.t_stat) for p in stats if np.isfinite(p.t_stat)], dtype=float)
    sharpes = np.array([p.sharpe_annualized for p in stats if np.isfinite(p.sharpe_annualized)], dtype=float)
    return ScanResult(
        panel_key=spec.key,
        arm=arm,
        seed=seed,
        horizon=horizon,
        window=window_label,
        n_formation_bars=int(rows.size),
        n_measurable=len(stats),
        n_unmeasurable=int(n_unmeasurable),
        n_t_ge_3=int((finite_t >= GATE1_T_THRESHOLDS[0]).sum()),
        n_t_ge_4=int((finite_t >= GATE1_T_THRESHOLDS[1]).sum()),
        t_max_abs=float(finite_t.max()) if finite_t.size else float("nan"),
        sigma_sr_annualized=float(sharpes.std(ddof=1)) if sharpes.size > 1 else float("nan"),
        patterns=stats,
    )


def run_discovery(
    panel: ScanPanel,
    spec: PanelSpec,
    *,
    arm: str = ARM_REAL,
    seed: int = 0,
    horizons: Iterable[int] = HORIZONS,
) -> dict[int, ScanResult]:
    """The §5 half of the experiment: the discovery window only, for one arm.
    Never reads a holdout bar — `_window_mask` is bounded by §4's discovery
    dates and `_formation_mask` drops any formation bar whose outcome window
    would cross the boundary."""
    return {
        h: scan_window(
            panel,
            spec,
            horizon=h,
            window=(spec.discovery_start, spec.discovery_end),
            window_label="discovery",
            arm=arm,
            seed=seed,
        )
        for h in horizons
    }


# ---------------------------------------------------------------------------
# 6. Gate 1 (§6).
# ---------------------------------------------------------------------------

@dataclass
class Gate1Result:
    panel_key: str
    horizon: int
    n3_real: int
    n4_real: int
    tmax_real: float
    n3_placebo_max: int
    n4_placebo_max: int
    tmax_placebo_max: float
    n3_placebo: list[int]
    tmax_placebo: list[float]
    passed: bool
    detail: str


def evaluate_gate1(real: ScanResult, placebo: Sequence[ScanResult]) -> Gate1Result:
    """§6 GATE 1 (existence): PASS iff N3_real > max_draws N3_P1 AND
    Tmax_real > max_draws Tmax_P1. Read off mechanically; no judgement."""
    if not placebo:
        raise ValueError("GATE 1 needs the placebo draws — an unopposed real arm is not a gate")
    n3 = [r.n_t_ge_3 for r in placebo]
    n4 = [r.n_t_ge_4 for r in placebo]
    tmax = [r.t_max_abs for r in placebo]
    n3_max, n4_max = max(n3), max(n4)
    tmax_max = float(np.nanmax(tmax))
    passed = bool(real.n_t_ge_3 > n3_max and real.t_max_abs > tmax_max)
    return Gate1Result(
        panel_key=real.panel_key,
        horizon=real.horizon,
        n3_real=real.n_t_ge_3,
        n4_real=real.n_t_ge_4,
        tmax_real=real.t_max_abs,
        n3_placebo_max=n3_max,
        n4_placebo_max=n4_max,
        tmax_placebo_max=tmax_max,
        n3_placebo=n3,
        tmax_placebo=tmax,
        passed=passed,
        detail=(
            f"N3 real {real.n_t_ge_3} vs placebo max {n3_max}; "
            f"Tmax real {real.t_max_abs:.4f} vs placebo max {tmax_max:.4f}"
        ),
    )


# ---------------------------------------------------------------------------
# 7. Holdout (§6) — a SEPARATE call that refuses to run without discovery.
# ---------------------------------------------------------------------------

@dataclass
class HoldoutResult:
    panel_key: str
    arm: str
    seed: int
    horizon: int
    n_bars: int
    n_patterns: int
    t_stat: float
    mean: float
    sharpe_annualized: float
    t_stat_after_cost: float
    mean_after_cost: float
    mean_turnover: float
    top_pattern_ids: list[int]
    top_labels: list[str]
    top_signs: list[int]
    top_discovery_t: list[float]
    top_holdout_t: list[float]


def _oriented_pattern_series(
    panel: ScanPanel,
    spec: PanelSpec,
    horizon: int,
    codes_by_k: dict[int, list[tuple[int, int]]],
    rows: np.ndarray,
) -> dict[tuple[int, int], tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """For each requested (k, code): (bar indices, portfolio return, member
    count) over the holdout bars, honouring the same per-bar name floor
    (ADDENDUM 01 item G)."""
    outcome = panel.outcomes[horizon]
    series: dict[tuple[int, int], tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    for k, wanted in codes_by_k.items():
        if not wanted:
            continue
        n_codes = N_BINS**k
        bar_of, code_of, cell_mean, cell_count = _cell_table(panel.codes[k], outcome, rows, n_codes)
        keep = cell_count >= spec.min_names
        bar_of, code_of, cell_mean, cell_count = bar_of[keep], code_of[keep], cell_mean[keep], cell_count[keep]
        for code, _sign in wanted:
            sel = code_of == code
            series[(k, code)] = (rows[bar_of[sel]], cell_mean[sel], cell_count[sel])
    return series


def _membership_weights(
    panel: ScanPanel,
    spec: PanelSpec,
    top: Sequence[tuple[int, int, int]],
    rows: np.ndarray,
) -> np.ndarray:
    """(len(rows), n_names) implied name weights of the equal-weight top-20
    book, w_{i,t} = (1/P_t) * sum_p sign_p * 1[i in p at t] / n_{p,t}
    (ADDENDUM 01 item H). Used only by the naive cost arm."""
    weights = np.zeros((rows.size, panel.n_names), dtype=float)
    present = np.zeros(rows.size, dtype=float)
    for k, code, sign in top:
        member = panel.codes[k][rows] == code
        counts = member.sum(axis=1)
        ok = counts >= spec.min_names
        if not ok.any():
            continue
        contrib = np.zeros_like(weights)
        safe = np.where(counts > 0, counts, 1)
        contrib[ok] = member[ok] * (float(sign) / safe[ok][:, None])
        weights += contrib
        present += ok.astype(float)
    live = present > 0
    weights[live] /= present[live][:, None]
    return weights


def run_holdout(
    panel: ScanPanel,
    spec: PanelSpec,
    discovery: ScanResult | None,
    *,
    arm: str = ARM_REAL,
    seed: int = 0,
    top_n: int = TOP_N_HOLDOUT,
    charge_cost: bool = True,
) -> HoldoutResult:
    """§6's holdout leg for ONE arm: take that arm's own top-`top_n`
    discovery patterns, orient each by the sign of its discovery mean, and
    equal-weight-average the oriented portfolios over the holdout window.

    `discovery` is mandatory and is checked, not defaulted: §4 fixes that the
    holdout is touched exactly once, after discovery is complete. A call with
    `None` (or with a discovery result from the wrong panel/arm/horizon, or
    one computed on a window other than the discovery window) raises."""
    if discovery is None:
        raise ValueError(
            "run_holdout requires the discovery ScanResult whose top patterns are being "
            "tested — the holdout is touched once, after discovery (PREREGISTRATION §4). "
            "There is deliberately no default."
        )
    if discovery.window != "discovery":
        raise ValueError(f"discovery result was computed on window {discovery.window!r}, not 'discovery'")
    if discovery.panel_key != spec.key:
        raise ValueError(f"discovery result is for panel {discovery.panel_key!r}, not {spec.key!r}")
    if discovery.arm != arm or discovery.seed != seed:
        raise ValueError(
            f"discovery result is for arm {discovery.arm!r}/seed {discovery.seed} but the holdout "
            f"was asked for {arm!r}/{seed} — each arm is held out against its OWN top-{top_n} (§6)"
        )

    horizon = discovery.horizon
    chosen = discovery.top(top_n)
    if not chosen:
        raise ValueError("discovery produced no measurable pattern with a finite t; nothing to hold out")
    top = [(p.k, p.code, 1 if p.mean >= 0 else -1) for p in chosen]

    window_mask = _window_mask(panel.dates, spec.holdout_start, spec.holdout_end)
    rows = np.flatnonzero(_formation_mask(window_mask, horizon))

    codes_by_k: dict[int, list[tuple[int, int]]] = {k: [] for k in K_VALUES}
    for k, code, sign in top:
        codes_by_k[k].append((code, sign))
    series = _oriented_pattern_series(panel, spec, horizon, codes_by_k, rows)

    row_pos = {int(r): i for i, r in enumerate(rows)}
    acc = np.zeros(rows.size, dtype=float)
    present = np.zeros(rows.size, dtype=float)
    per_pattern_t: list[float] = []
    for (k, code, sign), stat in zip(top, chosen):
        bars, values, _counts = series.get((k, code), (np.zeros(0, dtype=np.int64), np.zeros(0), np.zeros(0)))
        oriented = values * float(sign)
        if bars.size:
            idx = np.array([row_pos[int(b)] for b in bars], dtype=np.int64)
            acc[idx] += oriented
            present[idx] += 1.0
        t_p, _m, _se = newey_west_t_of_mean(oriented, horizon)
        per_pattern_t.append(float(t_p))
        del stat

    live = present > 0
    book = acc[live] / present[live]
    t_stat, mean, _se = newey_west_t_of_mean(book, horizon)

    t_cost, mean_cost, mean_turnover = float("nan"), float("nan"), float("nan")
    if charge_cost and live.any():
        weights = _membership_weights(panel, spec, top, rows)[live]
        turnover = np.abs(np.diff(weights, axis=0, prepend=np.zeros((1, weights.shape[1])))).sum(axis=1)
        net = book - turnover * spec.cost_bp_one_way * 1e-4
        t_cost, mean_cost, _ = newey_west_t_of_mean(net, horizon)
        mean_turnover = float(turnover.mean())

    return HoldoutResult(
        panel_key=spec.key,
        arm=arm,
        seed=seed,
        horizon=horizon,
        n_bars=int(live.sum()),
        n_patterns=len(top),
        t_stat=float(t_stat),
        mean=float(mean),
        sharpe_annualized=annualized_sharpe(book, spec.periods_per_year),
        t_stat_after_cost=float(t_cost),
        mean_after_cost=float(mean_cost),
        mean_turnover=mean_turnover,
        top_pattern_ids=[p.pattern_id for p in chosen],
        top_labels=[p.label for p in chosen],
        top_signs=[s for _k, _c, s in top],
        top_discovery_t=[float(p.t_stat) for p in chosen],
        top_holdout_t=per_pattern_t,
    )


@dataclass
class Gate2Result:
    panel_key: str
    horizon: int
    t_real: float
    t_placebo_max: float
    t_placebo: list[float]
    passed: bool
    detail: str


def evaluate_gate2(real: HoldoutResult, placebo: Sequence[HoldoutResult]) -> Gate2Result:
    """§6 GATE 2 (survival): PASS iff t(H_real) >= 2.0 AND
    t(H_real) > max_d t(H_P1,d). Signed t, not |t| — §6 says the top-20 are
    oriented by their discovery sign, so a book that reverses out of sample
    must fail, not pass on magnitude."""
    if not placebo:
        raise ValueError("GATE 2 needs the placebo draws")
    ts = [r.t_stat for r in placebo]
    t_max = float(np.nanmax(ts))
    passed = bool(np.isfinite(real.t_stat) and real.t_stat >= GATE2_T_FLOOR and real.t_stat > t_max)
    return Gate2Result(
        panel_key=real.panel_key,
        horizon=real.horizon,
        t_real=float(real.t_stat),
        t_placebo_max=t_max,
        t_placebo=[float(t) for t in ts],
        passed=passed,
        detail=(
            f"t(H_real) {real.t_stat:.4f} vs floor {GATE2_T_FLOOR} and placebo max {t_max:.4f}"
        ),
    )


# ---------------------------------------------------------------------------
# 8. Control non-degeneracy (§5).
# ---------------------------------------------------------------------------

def _membership_signatures(
    panel: ScanPanel, rows: np.ndarray, k: int, salt: np.ndarray
) -> dict[int, int]:
    """{bar * n_codes + code: 64-bit signature of the member-name set}.

    The signature is the wrapping uint64 SUM of one fixed random value per
    name, which is commutative (so it does not depend on the order names
    happen to come out in) and exact (uint64 addition wraps, unlike a float
    sum). Two cells collide only with probability ~2**-64 per comparison."""
    n_codes = N_BINS**k
    codes = panel.codes[k][rows]
    valid = codes >= 0
    if not valid.any():
        return {}
    bar_idx, name_idx = np.nonzero(valid)
    keys = bar_idx.astype(np.int64) * n_codes + codes[valid].astype(np.int64)
    order = np.argsort(keys, kind="stable")
    keys_sorted = keys[order]
    uniq, starts = np.unique(keys_sorted, return_index=True)
    sigs = np.add.reduceat(salt[name_idx[order]], starts)
    return dict(zip(uniq.tolist(), sigs.tolist()))


def identical_membership_fraction(
    real: ScanPanel,
    placebo: ScanPanel,
    spec: PanelSpec,
    *,
    horizon: int = HORIZON_PRIMARY,
    k_values: Iterable[int] = K_VALUES,
    seed: int = 20260911,
) -> tuple[float, int, int]:
    """§5's control non-degeneracy proof: the fraction of (pattern, date)
    cells whose MEMBERSHIP is identical between the real panel and a placebo
    draw, over the discovery window.

    Denominator is the cells non-empty in at least one arm — counting the
    astronomically many cells empty in both would make any control look
    non-degenerate for free. Returns (fraction, n_identical, n_union)."""
    if real.names != placebo.names or len(real.dates) != len(placebo.dates):
        raise ValueError("the two panels must be the same names and bars for a membership comparison")
    window_mask = _window_mask(real.dates, spec.discovery_start, spec.discovery_end)
    rows = np.flatnonzero(_formation_mask(window_mask, horizon))
    salt = np.random.default_rng(seed).integers(0, 2**63 - 1, size=real.n_names, dtype=np.int64).astype(np.uint64)
    identical = 0
    union = 0
    for k in k_values:
        a = _membership_signatures(real, rows, k, salt)
        b = _membership_signatures(placebo, rows, k, salt)
        keys = set(a) | set(b)
        union += len(keys)
        identical += sum(1 for key in keys if key in a and key in b and a[key] == b[key])
    return (identical / union if union else float("nan")), identical, union


# ---------------------------------------------------------------------------
# 9. Small helpers the run script and the report share.
# ---------------------------------------------------------------------------

def patterns_to_frame(result: ScanResult) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "pattern_id": p.pattern_id,
                "k": p.k,
                "code": p.code,
                "label": p.label,
                "t_stat": p.t_stat,
                "mean": p.mean,
                "sharpe_annualized": p.sharpe_annualized,
                "n_bars": p.n_bars,
                "mean_names": p.mean_names,
            }
            for p in result.patterns
        ]
    ).sort_values("t_stat", key=lambda s: s.abs(), ascending=False)


def panel_fingerprint(panel: ScanPanel) -> str:
    """A sha256 over the shape, the date bounds, the names and the finite
    return values — so a report can say WHICH panel produced its numbers, per
    this project's persist-every-result rule."""
    h = hashlib.sha256()
    h.update(json.dumps({
        "shape": list(panel.returns.shape),
        "first": str(panel.dates[0].date()) if panel.n_bars else "",
        "last": str(panel.dates[-1].date()) if panel.n_bars else "",
        "names": list(panel.names),
    }, sort_keys=True).encode("utf-8"))
    finite = panel.returns[np.isfinite(panel.returns)]
    h.update(np.ascontiguousarray(finite, dtype=np.float64).tobytes())
    return h.hexdigest()
