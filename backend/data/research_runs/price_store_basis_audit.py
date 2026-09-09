"""Audit the shared point-in-time price store for SHARE-BASIS defects
(price_store.py section 4b) and, on request, repair named tickers.

    ./venv/bin/python data/research_runs/price_store_basis_audit.py
    ./venv/bin/python data/research_runs/price_store_basis_audit.py --since 2025-06-01
    ./venv/bin/python data/research_runs/price_store_basis_audit.py --repair APH MNST RUSHA
    ./venv/bin/python data/research_runs/price_store_basis_audit.py --drop-unfinal
    ./venv/bin/python data/research_runs/price_store_basis_audit.py --confirm-recent 5

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

DROP-UNFINAL (section 4c repair): every row dated on or after the current
UTC date is removed from every ticker (a bar dated today cannot be final —
on 2026-09-10 a local-date "through today" request had frozen the 9th's
mid-session snapshot for 611 tickers) and the coverage ledger is rebounded
so those days are asked again once they are final. The dropped rows are
written into the JSON as evidence.

CONFIRM-RECENT N (read-only): one batch vendor download of the last N
business days for every stored ticker, compared close by close with the
store — the whole-store check that no other not-yet-final bar was ever
frozen. Run it after the New York close (>= 21:00 UTC) so the vendor's own
bars are final.

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
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

from app.services.market_data.price_store import (
    PriceStore,
    PriceStoreReport,
    audit_frame,
    audit_store,
    utc_today,
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
    today = utc_today()
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
    today = utc_today()
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


def drop_unfinal(as_of: date) -> dict:
    store = PriceStore()
    dropped = store.drop_unfinal_rows(as_of=as_of)
    n_rows = sum(len(f) for f in dropped.values())
    print(f"drop-unfinal as of {as_of}: {n_rows} row(s) removed from {len(dropped)} ticker(s)")
    return {
        "as_of": as_of.isoformat(),
        "n_tickers": len(dropped),
        "n_rows": n_rows,
        "dropped": {
            ticker: [
                {"date": ts.date().isoformat(), **{c: (None if pd.isna(v) else float(v)) for c, v in row.items()}}
                for ts, row in frame.iterrows()
            ]
            for ticker, frame in dropped.items()
        },
    }


def confirm_recent(n_days: int, *, batch_size: int = 400) -> dict:
    """Compare every stored ticker's last `n_days` business days with a fresh
    vendor batch download (store bypassed). Read-only."""
    store = PriceStore()
    live_provider = YFinanceProvider(price_store=PriceStore(None))
    today = utc_today()
    start = (pd.Timestamp(today) - pd.tseries.offsets.BDay(n_days)).date()
    tickers = sorted(p.name[: -len(".csv.gz")] for p in store.store_dir.glob("*.csv.gz"))
    out: dict = {"start": start.isoformat(), "end": today.isoformat(), "n_tickers": len(tickers),
                 "compared_rows": 0, "differing_rows": [], "vendor_missing": [], "stored_missing_days": {}}
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        raw = live_provider._download_raw_with_actions(batch, start, today)
        bundles = live_provider._per_ticker_fields(raw, batch) if raw is not None and not raw.empty else {}
        for ticker in batch:
            bundle = bundles.get(ticker)
            stored = store.read_ticker(ticker)
            if bundle is None or "close" not in bundle:
                out["vendor_missing"].append(ticker)
                continue
            live = PriceStore.to_as_traded(bundle, bundle.get("split", pd.Series(dtype=float)))
            # DROP THE VENDOR'S PADDING BEFORE COMPARING ANYTHING. yfinance
            # aligns a multi-ticker batch onto the UNION of its members'
            # trading calendars, and this store's universe contains crypto
            # (BCH-USD, LINK-USD, ...) which trades every day — so an equity
            # in the same batch comes back with NaN-close rows on Saturdays,
            # Sundays and market holidays. Measured 2026-09-09: AAPL fetched
            # alone over 09-02..09-09 returns 4 rows; AAPL fetched alongside
            # BTC-USD returns 7, the extra three being Sat 09-05, Sun 09-06
            # and Labor Day 09-07 with a NaN close. The first run of this
            # check reported all 1,592 tickers as "missing" those three days
            # for exactly that reason — a defect in THIS SCRIPT, not in the
            # store, which was independently confirmed to hold 0 NaN-close
            # rows across 6,852,849 rows and weekend rows only for crypto.
            live = live.loc[live.index < pd.Timestamp(today)]
            live = live.loc[live["close"].notna()]
            if stored is None or stored.empty:
                continue
            window = stored.loc[stored.index >= pd.Timestamp(start)]
            joined = window[["close", "volume"]].join(live[["close", "volume"]], rsuffix="_live", how="inner")
            out["compared_rows"] += len(joined)
            off = joined[((joined["close"] - joined["close_live"]).abs() / joined["close_live"].abs()) > 0.001]
            for ts, row in off.iterrows():
                out["differing_rows"].append({"ticker": ticker, "date": ts.date().isoformat(),
                                              "stored_close": float(row["close"]), "vendor_close": float(row["close_live"]),
                                              "stored_volume": float(row["volume"]), "vendor_volume": float(row["volume_live"])})
            missing = sorted(
                d.date().isoformat()
                for d in live.index.difference(window.index)
                if d >= pd.Timestamp(start)
            )
            if missing:
                out["stored_missing_days"][ticker] = missing
        print(f"confirm-recent: {min(i + batch_size, len(tickers))}/{len(tickers)} tickers, "
              f"{out['compared_rows']} rows compared, {len(out['differing_rows'])} differ", flush=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=None, help="only split events on/after this date (YYYY-MM-DD)")
    ap.add_argument("--confirm", nargs="*", default=None, help="tickers to compare row-by-row with a fresh vendor reconstruction (read-only)")
    ap.add_argument("--repair", nargs="*", default=None, help="tickers to quarantine, resync and re-fetch")
    ap.add_argument("--rebound-coverage", action="store_true",
                    help="shrink every coverage window that runs past the ticker's newest stored row (the 2026-09-10 defect); prints and records what changed")
    ap.add_argument("--drop-unfinal", action="store_true",
                    help="remove every row dated on/after the current UTC date from every ticker and rebound the ledger (section 4c repair)")
    ap.add_argument("--confirm-recent", type=int, default=None, metavar="N",
                    help="compare the last N business days of every ticker with a fresh vendor batch (read-only)")
    args = ap.parse_args()
    since = date.fromisoformat(args.since) if args.since else None
    now = datetime.now(UTC)
    today = now.date()
    payload: dict = {"run_at": now.isoformat(timespec="minutes"), "since": args.since}
    if args.drop_unfinal:
        payload["drop_unfinal"] = drop_unfinal(today)
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
    if args.confirm_recent:
        payload["confirm_recent"] = confirm_recent(args.confirm_recent)
    out = HERE / f"price_store_basis_audit_{today.isoformat()}.json"
    if out.exists():  # one file per run, never overwrite an earlier day's committed evidence
        out = HERE / f"price_store_basis_audit_{now.strftime('%Y-%m-%dT%H%MZ')}.json"
    out.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    print(f"written {out.relative_to(_BACKEND)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
