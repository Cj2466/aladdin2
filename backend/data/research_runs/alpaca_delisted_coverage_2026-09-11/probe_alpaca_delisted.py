"""Does Alpaca's SIP daily-bar history cover DELISTED names? (P2 on the paid-decisions list)

Re-uses the ipo_lockup feasibility sample of 2026-09-06 (56 IPO companies, four buckets,
probed against yfinance then: 37.5% overall, 0/6 on the known-delisted anchors) and probes
the SAME windows against AlpacaProvider (feed=sip, 1Day bars). Alpaca history begins
2016-01-04, so a window ending before that is UNTESTABLE here and is reported as such,
never counted as a miss. Run from the MAIN checkout's backend with its .env sourced:
    set -a; . ./.env; set +a; ./venv/bin/python data/research_runs/alpaca_delisted_coverage_2026-09-11/probe_alpaca_delisted.py
Writes alpaca_delisted_probe.json next to this file. No DB writes, no store writes."""
from __future__ import annotations

import json
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[2]
sys.path.insert(0, str(BACKEND))

from app.services.market_data.alpaca_provider import AlpacaProvider

ALPACA_FIRST_DAY = date(2016, 1, 4)
SAMPLE = BACKEND / "data/research_runs/ipo_lockup_samples/section_c_price_availability_detail.json"
WINDOW_DAYS = 10  # calendar days either side of the lockup date, as the 2026-09-06 probe used a short window


def probe(provider: AlpacaProvider, ticker: str, start: date, end: date) -> dict:
    frames, missing = provider.get_stock_bars([ticker], "1Day", start, end)
    frame = frames.get(ticker)
    if frame is None or frame.empty:
        return {"resolved": False, "n_rows": 0, "missing_flag": ticker in missing}
    return {
        "resolved": True,
        "n_rows": len(frame),
        "first": str(frame.index[0].date()),
        "last": str(frame.index[-1].date()),
        "median_close": float(frame["close"].median()),
    }


def main() -> None:
    rows = json.loads(SAMPLE.read_text())
    provider = AlpacaProvider()
    out = []
    for r in rows:
        lock = date.fromisoformat(r["lockup_date_approx"])
        w_start, w_end = lock - timedelta(days=WINDOW_DAYS), lock + timedelta(days=WINDOW_DAYS)
        rec = {k: r[k] for k in ("ticker", "name", "ipo_date", "lockup_date_approx", "bucket", "a_priori_label")}
        rec["yfinance_2026_09_06"] = {
            "lockup_resolved": r["lockup_window_probe"]["resolved"],
            "recent_resolved": r["recent_window_probe"]["resolved"],
        }
        rec["lockup_testable_on_alpaca"] = w_end >= ALPACA_FIRST_DAY
        if rec["lockup_testable_on_alpaca"]:
            rec["alpaca_lockup_window"] = probe(provider, r["ticker"], max(w_start, ALPACA_FIRST_DAY), w_end)
        # full-history probe: what does Alpaca hold for this symbol at all since 2016?
        # end = the last complete UTC day: the free SIP tier returns 403 for any request touching "today"
        rec["alpaca_full_history"] = probe(provider, r["ticker"], ALPACA_FIRST_DAY, datetime.now(UTC).date() - timedelta(days=1))
        out.append(rec)
        print(r["ticker"], r["bucket"], "lockup:", rec.get("alpaca_lockup_window", "untestable(<2016)"), "| full:", rec["alpaca_full_history"].get("n_rows"), rec["alpaca_full_history"].get("last"))
    testable = [x for x in out if x["lockup_testable_on_alpaca"]]
    summary = {
        "written_utc": datetime.now(UTC).isoformat(),
        "n_sample": len(out),
        "n_lockup_testable_on_alpaca": len(testable),
        "alpaca_lockup_hit_rate_pct_on_testable": round(100 * sum(x["alpaca_lockup_window"]["resolved"] for x in testable) / len(testable), 1) if testable else None,
        "yfinance_lockup_hit_rate_pct_on_same_testable": round(100 * sum(x["yfinance_2026_09_06"]["lockup_resolved"] for x in testable) / len(testable), 1) if testable else None,
        "by_bucket_testable": {},
        "anchor_delisted_full_history": [
            {"ticker": x["ticker"], "label": x["a_priori_label"], **x["alpaca_full_history"]} for x in out if x["bucket"] == "anchor_delisted"
        ],
        "caveat": "A symbol re-used by a later company returns that company's bars under the same string; a delisted name's history must be cut at its own delisting date, which this probe does NOT do automatically (see anchor 'last' dates vs the a_priori_label).",
    }
    for b in sorted({x["bucket"] for x in testable}):
        xs = [x for x in testable if x["bucket"] == b]
        summary["by_bucket_testable"][b] = {
            "n": len(xs),
            "alpaca_hits": sum(x["alpaca_lockup_window"]["resolved"] for x in xs),
            "yfinance_hits": sum(x["yfinance_2026_09_06"]["lockup_resolved"] for x in xs),
        }
    (HERE / "alpaca_delisted_probe.json").write_text(json.dumps({"summary": summary, "rows": out}, indent=2))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
