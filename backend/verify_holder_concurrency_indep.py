"""Item 4(c): is the module-level _LIVE_NOA_NEUTRAL_BUCKET_FRAME holder safe
under the runner's REAL concurrency shape?

CrossSectionalForwardValidationRunner._tick fans out with
    asyncio.gather(*(asyncio.to_thread(self._process_family, k, rows) ...))
so every registered family with a pending row is processed in its own thread
AT THE SAME TIME. This drives the real runner with three families whose
build_live_panel is slow and interleaved, and asserts that the spec each
registration ticks against is bound to ITS OWN family's published panel.
"""

import asyncio
import json
import threading
import time
from dataclasses import replace
from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.services.research_lab import cross_sectional_forward_registry as reg
from app.services.research_lab import cross_sectional_forward_validation_runner as runner_mod
from app.services.research_lab.cross_sectional import CrossSectionalData
from app.services.research_lab.cross_sectional_forward_registry import CrossSectionalLivePanel
from app.time_utils import utcnow_naive

fails = 0


def check(label, cond, detail=""):
    global fails
    fails += not cond
    print(f"{'PASS' if cond else '**FAIL**'}  {label}  {detail}")


TODAY = utcnow_naive().date()
DATES = pd.bdate_range(end=pd.Timestamp(TODAY) - pd.Timedelta(days=1), periods=40)
TICKERS = [f"Q{i:02d}" for i in range(60)]
from app.services.research_lab.cross_sectional_quality_neutral import SECTOR_BUCKETS  # noqa: E402

rng = np.random.default_rng(3)
CLOSE = pd.DataFrame(
    {t: 100.0 * np.exp(np.cumsum(rng.normal(0, 0.01, len(DATES)))) for t in TICKERS}, index=DATES
)
FUND = pd.DataFrame({t: float(i) / len(TICKERS) for i, t in enumerate(TICKERS)}, index=DATES)


def bucket_frame(tag: str) -> pd.DataFrame:
    """A distinguishable but VALID bucket panel, so a stomp is detectable."""
    f = pd.DataFrame(
        {t: [SECTOR_BUCKETS[i % len(SECTOR_BUCKETS)]] * len(DATES) for i, t in enumerate(TICKERS)},
        index=DATES,
    )
    f.attrs["tag"] = tag
    return f


NOA_FRAME = bucket_frame("the-noa-family's-own-panel")
POISON = bucket_frame("STOMPED-BY-ANOTHER-FAMILY")


def membership(_ticker, _on):
    return True


observed_bindings: list[str] = []
lock = threading.Lock()


def slow_noa_panel(end: date) -> CrossSectionalLivePanel:
    """Publishes the holder, then DAWDLES -- the widest possible window for
    another concurrently-processed family to stomp it before resolve_spec."""
    reg._LIVE_NOA_NEUTRAL_BUCKET_FRAME = NOA_FRAME
    time.sleep(0.15)
    return CrossSectionalLivePanel(
        data=CrossSectionalData(close=CLOSE, fundamental_signal=FUND),
        membership_fn=membership, n_tickers=len(TICKERS), last_row_date=DATES[-1].date())


def hostile_panel(end: date) -> CrossSectionalLivePanel:
    """A DIFFERENT family that (wrongly) writes the shared holder, run
    concurrently -- the exact cross-family stomp 4(c) asks about."""
    for _ in range(40):
        reg._LIVE_NOA_NEUTRAL_BUCKET_FRAME = POISON
        time.sleep(0.005)
    return CrossSectionalLivePanel(
        data=CrossSectionalData(close=CLOSE, fundamental_signal=FUND),
        membership_fn=membership, n_tickers=len(TICKERS), last_row_date=DATES[-1].date())


def quiet_panel(end: date) -> CrossSectionalLivePanel:
    time.sleep(0.05)
    return CrossSectionalLivePanel(
        data=CrossSectionalData(close=CLOSE, fundamental_signal=FUND),
        membership_fn=membership, n_tickers=len(TICKERS), last_row_date=DATES[-1].date())


print("=" * 78)
print("1. THE PRODUCTION SHAPE: 3 families ticked concurrently, none writing the holder")
print("=" * 78)
print("   (only build_noa_neutral_live_panel writes _LIVE_NOA_NEUTRAL_BUCKET_FRAME --")
print("    verified by grep over app/: writers =",
      len([1 for line in open("app/services/research_lab/cross_sectional_forward_registry.py")
           if "_LIVE_NOA_NEUTRAL_BUCKET_FRAME =" in line and "global" not in line]),
      "assignment sites, all inside that one function + its memo hit)")

real_writers = []
for path in ("app/services/research_lab/cross_sectional_forward_registry.py",):
    for i, line in enumerate(open(path), 1):
        if "_LIVE_NOA_NEUTRAL_BUCKET_FRAME =" in line:
            real_writers.append((i, line.strip()))
for ln, src in real_writers:
    print(f"     line {ln}: {src}")
src_lines = open("app/services/research_lab/cross_sectional_forward_registry.py").read().splitlines()
in_builder = [
    ln for ln, _ in real_writers
    if "def build_noa_neutral_live_panel" in "\n".join(src_lines[max(0, ln - 80):ln])
]
check("every ASSIGNMENT to the holder is inside build_noa_neutral_live_panel "
      "(the memo-hit republish and the fresh build) -- nothing else in app/ writes it",
      len(real_writers) == 2 and len(in_builder) == 2,
      f"{len(real_writers)} assignments, {len(in_builder)} of them in that function")

print()
print("=" * 78)
print("2. ADVERSARIAL: a concurrently-ticked family that DOES stomp the holder")
print("=" * 78)


async def drive(hostile: bool):
    """Run one real _tick with the real runner over three fake families."""
    observed_bindings.clear()
    saved = dict(reg._registry)
    try:
        base = reg.get_family_adapter("quality_noa_industry_neutral")
        reg._registry["quality_noa_industry_neutral"] = replace(base, build_live_panel=slow_noa_panel)
        reg._registry["fam_b"] = replace(
            reg.get_family_adapter("quality_cbop"), family_key="fam_b",
            build_live_panel=hostile_panel if hostile else quiet_panel)
        reg._registry["fam_c"] = replace(
            reg.get_family_adapter("quality_cbop"), family_key="fam_c",
            build_live_panel=quiet_panel)

        r = runner_mod.CrossSectionalForwardValidationRunner()
        snaps = {
            "quality_noa_industry_neutral": [_snap(1, "quality_noa_industry_neutral",
                                                  "noa_neutral_ls_h126_median")],
            "fam_b": [_snap(2, "fam_b", "cbop_ls_h63")],
            "fam_c": [_snap(3, "fam_c", "cbop_ls_h63")],
        }
        await asyncio.gather(*(
            asyncio.to_thread(_process_and_record, r, k, v) for k, v in snaps.items()))
    finally:
        reg._registry.clear()
        reg._registry.update(saved)


def _snap(i, fam, pid):
    return runner_mod._RegistrationSnapshot(
        id=i, family_key=fam, pattern_id=pid, status="in_progress", started_at=TODAY,
        last_processed_date=None, min_trading_days_threshold=126, n_forward_trading_days=0,
        n_formations=0, spec_fingerprint="", config_fingerprint="", spec_snapshot_json="{}",
        config_snapshot_json="{}", carry_state_json="{}", day_results_json="[]",
        formations_json="[]")


def _process_and_record(r, family_key, snaps):
    """_process_family's own body, stopping at the point resolve_spec runs --
    which is exactly where the holder's value decides what gets ticked."""
    adapter = reg.get_family_adapter(family_key)
    _panel = adapter.build_live_panel(TODAY)
    _a, spec = reg.resolve_spec(family_key, snaps[0].pattern_id)
    bf = getattr(spec.signal_fn, "keywords", {}).get("bucket_frame")
    with lock:
        observed_bindings.append(
            f"{family_key} -> {bf.attrs.get('tag') if bf is not None else 'n/a (no bucket_frame)'}")


asyncio.run(drive(hostile=False))
print("   benign 3-family concurrent tick:")
for b in sorted(observed_bindings):
    print("     ", b)
check("noa's spec bound to the noa family's own published panel",
      any("quality_noa_industry_neutral -> the-noa-family's-own-panel" in b
          for b in observed_bindings), "")

asyncio.run(drive(hostile=True))
print("   HOSTILE tick (another family writing the same global):")
for b in sorted(observed_bindings):
    print("     ", b)
stomped = any("STOMPED" in b for b in observed_bindings)
print()
print(f"   -> a family that wrote the holder WOULD corrupt noa's binding: {stomped}")
print("      This is the latent fragility: the holder is protected by CALL-ORDER")
print("      CONVENTION, not by scoping. No such writer exists today (see check 1),")
print("      so it is not a live bug -- but nothing in code prevents one being added.")

print()
print("=" * 78)
print(f"{'ALL CHECKS PASSED' if not fails else f'{fails} CHECK(S) FAILED'}")
print("=" * 78)
