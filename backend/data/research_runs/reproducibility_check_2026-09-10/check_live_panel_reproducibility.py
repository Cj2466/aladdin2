"""Does the point-in-time work of 2026-09-09/10 actually deliver what it was
for? Build each live family's panel TWICE and require the two to be identical.

    set -a; . ./.env; set +a
    ./venv/bin/python data/research_runs/reproducibility_check_2026-09-10/check_live_panel_reproducibility.py

WHY THIS EXISTS. Three nights of work went into making inputs immutable: the
price store's share-basis guard and coverage ledger (`c298dd3`, `7002a41`), the
not-yet-final-bar rule (`1f8307f`), the EDGAR fact store (`ef6584a`) and the
submissions store (`dfeb161`). Every one of those was justified by a measured
defect, but none of them was ever checked against the property they exist to
produce: **the same request, made twice, returns the same panel.** Individual
unit tests prove each guard in isolation; this proves the composition.

WHAT IT MEASURES. For every live cross-sectional registration's family, it calls
`adapter.build_live_panel(today)` twice in the same process and compares:

  * the panel's last row date and ticker count,
  * a SHA-256 over the close matrix, serialised deterministically,
  * the same over every other frame the panel carries.

A difference is a real finding either way round: identical means the stores are
serving frozen data as designed; different means something in the path is still
reaching the vendor and getting a different answer, which is exactly the class
of defect this project has hit three times.

HONEST LIMIT. Two calls in one process share any in-process cache, so this
cannot distinguish "the store served it twice" from "an in-memory cache served
it twice". It is the weaker of the two available checks. The stronger one —
comparing across processes and across days — is what the stores' `first_seen`
column exists for, and it cannot be run until a second day has passed. This
check is therefore a NECESSARY condition, not a sufficient one, and the report
says so rather than claiming more.

READ-ONLY with respect to the database: no registration is read for its state,
nothing is written. It does hit the network the first time a panel is built for
anything the stores do not already cover.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_BACKEND))

import pandas as pd

from app.services.research_lab.cross_sectional_forward_registry import (
    get_family_adapter,
)
from app.time_utils import utcnow_naive

HERE = Path(__file__).resolve().parent

# The four families holding a live forward registration, as recorded in
# cross_sectional_forward_validation_registrations. Hard-coded rather than
# queried so this script never touches the live table.
LIVE_FAMILIES = (
    "quality_cbop",
    "short_interest_ratio",
    "lazy_prices_jaccard_full",
    "cross_sectional_crypto",
)


def frame_digest(frame: pd.DataFrame) -> str:
    """A stable hash of a DataFrame's values, index and columns.

    Sorted on both axes and rendered at full float precision, so the digest
    depends on the data and not on column order or a repr's rounding."""
    ordered = frame.sort_index(axis=0).sort_index(axis=1)
    payload = "\n".join(
        [
            "|".join(str(c) for c in ordered.columns),
            "|".join(ordered.index.astype(str)),
            ordered.to_csv(float_format="%.17g"),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def panel_digests(panel) -> dict[str, str | int | None]:
    """Every frame the panel carries, hashed, plus its scalar descriptors."""
    out: dict[str, str | int | None] = {
        "last_row_date": str(getattr(panel, "last_row_date", None)),
        "n_tickers": getattr(panel, "n_tickers", None),
    }
    data = getattr(panel, "data", None)
    if data is None:
        return out
    for name in sorted(dir(data)):
        if name.startswith("_"):
            continue
        value = getattr(data, name, None)
        if isinstance(value, pd.DataFrame):
            out[f"data.{name}"] = frame_digest(value)
        elif isinstance(value, pd.Series):
            out[f"data.{name}"] = frame_digest(value.to_frame())
    return out


def main() -> int:
    today = utcnow_naive().date()
    now = datetime.now(UTC)
    print(f"building each live family's panel twice, as of {today} (UTC)\n")
    results: dict[str, dict] = {}
    for family in LIVE_FAMILIES:
        entry: dict = {}
        try:
            adapter = get_family_adapter(family)
        except Exception as exc:  # noqa: BLE001 — report and continue
            print(f"{family}: adapter unavailable: {exc}")
            results[family] = {"error": f"adapter unavailable: {exc}"}
            continue
        try:
            first = panel_digests(adapter.build_live_panel(today))
            second = panel_digests(adapter.build_live_panel(today))
        except Exception as exc:  # noqa: BLE001 — a panel that cannot build is a finding, not a crash
            print(f"{family}: panel build failed: {type(exc).__name__}: {exc}")
            results[family] = {"error": f"{type(exc).__name__}: {exc}"}
            continue
        differing = sorted(k for k in set(first) | set(second) if first.get(k) != second.get(k))
        entry = {
            "identical": not differing,
            "differing_keys": differing,
            "first": first,
            "second": second,
        }
        results[family] = entry
        status = "IDENTICAL" if not differing else f"DIFFERS on {differing}"
        print(f"{family:28s} rows_to {first.get('last_row_date')}  n_tickers {first.get('n_tickers')}  -> {status}")

    built = [f for f, r in results.items() if "error" not in r]
    identical = [f for f in built if results[f]["identical"]]
    print(f"\npanels built: {len(built)} of {len(LIVE_FAMILIES)} | identical on rebuild: {len(identical)} of {len(built)}")

    payload = {
        "run_at": now.isoformat(timespec="minutes"),
        "as_of": today.isoformat(),
        "families": results,
        "summary": {
            "built": len(built),
            "identical": len(identical),
            "failed": [f for f, r in results.items() if "error" in r],
        },
        "limit": (
            "Two builds in ONE process. This cannot separate a store hit from an in-process "
            "cache hit; it is a necessary condition for reproducibility, not a sufficient one. "
            "The cross-day check is what first_seen exists for and needs a second day."
        ),
    }
    out = HERE / f"live_panel_reproducibility_{now.strftime('%Y-%m-%dT%H%MZ')}.json"
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"written {out.relative_to(_BACKEND)}")
    return 0 if len(identical) == len(built) else 1


if __name__ == "__main__":
    raise SystemExit(main())
