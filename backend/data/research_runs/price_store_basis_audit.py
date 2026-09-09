"""Audit the shared point-in-time price store for SHARE-BASIS defects
(price_store.py section 4b) and, on request, repair named tickers.

    ./venv/bin/python data/research_runs/price_store_basis_audit.py
    ./venv/bin/python data/research_runs/price_store_basis_audit.py --since 2025-06-01
    ./venv/bin/python data/research_runs/price_store_basis_audit.py --repair APH MNST RUSHA

AUDIT (read-only): every stored ticker is checked for the two things an
as-traded series must satisfy around a split — the ex-date jump is about
1/ratio, and no non-split day nearby moves by a split-sized amount. Findings
are printed and written next to this script as
price_store_basis_audit_<date>.json so the state of the store on that day is
committed evidence.

REPAIR (explicit, per ticker, evidence kept): the stored file is COPIED to
data/price_store/quarantine/<date>/ first, then resync_ticker discards it,
then the ticker is re-fetched over the widest window the coverage ledger had
recorded for it, and the audit is re-run on the result. A repair that does
not come back clean is reported as such; nothing is retried automatically.

Why this exists: on 2026-09-09 three tickers (APH, MNST, RUSHA) were found
frozen at the wrong basis for their entire history with a few later rows at
the right one — fabricated +96%/-51% daily returns inside live research
windows. See REPRODUCIBILITY_GAP_ROOT_CAUSE_2026-09-09.md in
dormant_pool_2026-09-09/ for the measurement.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

import pandas as pd

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

from app.services.market_data.price_store import (
    PriceStore,
    PriceStoreReport,
    audit_frame,
    audit_store,
)
from app.services.market_data.yfinance_provider import YFinanceProvider

HERE = Path(__file__).resolve().parent
logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def run_audit(since: date | None) -> dict[str, list[str]]:
    store = PriceStore()
    findings = audit_store(store.store_dir, since=since)
    print(f"store: {store.store_dir}")
    print(f"tickers with findings: {len(findings)}")
    for ticker, items in sorted(findings.items()):
        print(f"  {ticker}")
        for item in items:
            print(f"    - {item}")
    return findings


def confirm_against_vendor(tickers: list[str]) -> dict[str, dict]:
    """THE decisive check for an audit finding: reconstruct the ticker from a
    fresh vendor download with the store bypassed and compare it row by row
    with what is stored. A sound ticker agrees on (nearly) every overlapping
    row; a basis-defective one disagrees on most rows by one constant ratio.
    Read-only; the store is not touched."""
    store = PriceStore()
    live_provider = YFinanceProvider(price_store=PriceStore(None))
    today = date.today()  # noqa: DTZ011
    out: dict[str, dict] = {}
    for ticker in tickers:
        stored = store.read_ticker(ticker)
        if stored is None or stored.empty:
            out[ticker] = {"verdict": "nothing stored"}
            continue
        start = min(stored.index).date()
        raw = live_provider._download_raw_with_actions([ticker], start, today)
        bundle = live_provider._per_ticker_fields(raw, [ticker]).get(ticker) if raw is not None and not raw.empty else None
        if bundle is None or "close" not in bundle:
            out[ticker] = {"verdict": "vendor returned nothing"}
            continue
        live = PriceStore.to_as_traded(bundle, bundle.get("split", pd.Series(dtype=float)))
        joined = stored[["close"]].join(live[["close"]], rsuffix="_live", how="inner")
        ratio = (joined["close"] / joined["close_live"]).astype(float)
        off = ratio[(ratio - 1.0).abs() > 0.01]
        counts = ratio.round(4).value_counts().head(4)
        out[ticker] = {
            "overlap_rows": len(joined),
            "rows_off_basis": len(off),
            "ratio_counts": {str(k): int(v) for k, v in counts.items()},
            "off_basis_first": off.index.min().date().isoformat() if len(off) else None,
            "off_basis_last": off.index.max().date().isoformat() if len(off) else None,
            "verdict": "BASIS-DEFECTIVE" if len(off) > 0.5 * len(joined) else ("some rows differ" if len(off) else "consistent with vendor"),
        }
        print(f"{ticker}: {out[ticker]['verdict']} — {out[ticker].get('rows_off_basis')}/{out[ticker].get('overlap_rows')} rows off, ratios {out[ticker].get('ratio_counts')}")
    return out


def repair(tickers: list[str]) -> dict[str, dict]:
    store = PriceStore()
    provider = YFinanceProvider(price_store=store)
    today = date.today()  # noqa: DTZ011
    quarantine = store.store_dir.parent / "quarantine" / today.isoformat()
    outcomes: dict[str, dict] = {}
    for ticker in tickers:
        coverage = store.read_coverage().get(ticker, [])
        starts = [date.fromisoformat(low) for low, _ in coverage] or [date(1993, 12, 22)]
        before = store.read_ticker(ticker)
        before_findings = audit_frame(before) if before is not None else ["(nothing stored)"]
        copied = store.quarantine_ticker(ticker, quarantine)
        store.resync_ticker(ticker)
        _frames, missing = provider.get_daily_ohlcv([ticker], min(starts), today)
        after = store.read_ticker(ticker)
        after_findings = audit_frame(after) if after is not None else ["(nothing fetched)"]
        report: PriceStoreReport | None = getattr(provider, "last_store_report", None)
        outcomes[ticker] = {
            "quarantined_copy": str(copied) if copied else None,
            "refetch_start": min(starts).isoformat(),
            "rows_before": 0 if before is None else len(before),
            "rows_after": 0 if after is None else len(after),
            "findings_before": before_findings,
            "findings_after": after_findings,
            "missing_after_refetch": ticker in missing,
            "store_report": report.describe() if report else None,
            "clean": after is not None and not after_findings and ticker not in missing,
        }
        print(f"{ticker}: rows {outcomes[ticker]['rows_before']} -> {outcomes[ticker]['rows_after']}, "
              f"clean={outcomes[ticker]['clean']}, quarantined at {copied}")
        for item in after_findings:
            print(f"    still: {item}")
    return outcomes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=None, help="only split events on/after this date (YYYY-MM-DD)")
    ap.add_argument("--confirm", nargs="*", default=None, help="tickers to compare row-by-row with a fresh vendor reconstruction (read-only)")
    ap.add_argument("--repair", nargs="*", default=None, help="tickers to quarantine, resync and re-fetch")
    ap.add_argument("--rebound-coverage", action="store_true",
                    help="shrink every coverage window that runs past the ticker's newest stored row (the 2026-09-10 defect); prints and records what changed")
    args = ap.parse_args()
    since = date.fromisoformat(args.since) if args.since else None
    today = date.today()  # noqa: DTZ011
    payload: dict = {"run_at": today.isoformat(), "since": args.since}
    if args.rebound_coverage:
        store = PriceStore()
        changed = store.rebound_coverage(as_of=today)
        payload["rebound_coverage"] = {"n_changed": len(changed), "changed": changed}
        print(f"rebound coverage: {len(changed)} window(s) shrunk; e.g. {list(changed.items())[:5]}")
    if args.repair:
        payload["repair"] = repair(args.repair)
    payload["audit"] = run_audit(since)
    if args.confirm:
        payload["confirm"] = confirm_against_vendor(args.confirm)
    out = HERE / f"price_store_basis_audit_{today.isoformat()}.json"
    out.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    print(f"written {out.relative_to(_BACKEND)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
