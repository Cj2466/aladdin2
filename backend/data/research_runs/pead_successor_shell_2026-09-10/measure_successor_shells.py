"""MEASUREMENT ONLY. How exposed is cross_sectional_pead to successor-shell CIKs,
and what could a submissions-side trigger actually key on?

    ./venv/bin/python data/research_runs/pead_successor_shell_2026-09-10/measure_successor_shells.py

WHY. `cross_sectional_pead.load_cik_map` resolves tickers through SEC's current
ticker -> CIK map with no successor-shell resolution. After a holding-company
reorganisation that map points at the NEWLY REGISTERED successor, which holds
none of the operating history. `edgar_xbrl_provider` fixed this for COMPANYFACTS
on 2026-09-02 (`dcdf864`) using a trigger the submissions endpoint cannot
reproduce: "the successor carries no ANNUAL XBRL FACTS, so use the CIK that
filed most of them". Submissions carries a filing index, not facts.

WHAT THIS DOES AND DOES NOT DO. It measures the exposure and characterises the
candidates. It does NOT pick a trigger and does NOT change any resolution:
choosing the rule is a construction decision, and `edgar_xbrl_provider`'s own
docstring already records that its measured population gave no basis for the
threshold such a rule would need. Deciding it from two examples would be worse.

Read-only. Uses the point-in-time submissions store built 2026-09-10, so it
costs one request (the ticker map) rather than 503.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_BACKEND))

from app.services.market_data.edgar_submissions_store import EdgarSubmissionsStore
from app.services.research_lab.cross_sectional_pead import (
    PEAD_SEC_USER_AGENT,
    load_cik_map,
)
from app.services.research_lab.ticker_universe import SCREENING_UNIVERSE

HERE = Path(__file__).resolve().parent

# Forms a registrant with real operating history necessarily accumulates. A
# successor shell registered this year has none of them yet.
PERIODIC_FORMS = ("10-K", "10-K/A")


def main() -> int:
    store = EdgarSubmissionsStore()
    cik_map = load_cik_map(PEAD_SEC_USER_AGENT)
    now = datetime.now(UTC)

    per_ticker: dict[str, dict] = {}
    for ticker in sorted(SCREENING_UNIVERSE):
        cik = cik_map.get(ticker)
        if cik is None:
            continue
        _name, _tickers, rows = store.read_rows(cik)
        if not rows:
            continue
        forms = Counter(r["form"] for r in rows if r.get("form"))
        per_ticker[ticker] = {
            "cik": cik,
            "n_filings": len(rows),
            "earliest_filing": min(r["filingDate"] for r in rows),
            "latest_filing": max(r["filingDate"] for r in rows),
            "n_10k": sum(forms.get(f, 0) for f in PERIODIC_FORMS),
            "n_10q": forms.get("10-Q", 0),
            "top_forms": dict(forms.most_common(6)),
        }

    zero_10k = {t: v for t, v in per_ticker.items() if v["n_10k"] == 0}
    tenk_hist = Counter(min(v["n_10k"], 10) for v in per_ticker.values())

    print(f"tickers with stored filings: {len(per_ticker)} of {len(SCREENING_UNIVERSE)}")
    print(f"tickers whose ENTIRE stored history holds ZERO 10-K: {len(zero_10k)}")
    for ticker, v in sorted(zero_10k.items(), key=lambda kv: kv[1]["n_filings"]):
        print(f"   {ticker:6s} CIK {v['cik']:>9d}  {v['n_filings']:>4d} filings since "
              f"{v['earliest_filing']}  forms={v['top_forms']}")
    print(f"\n10-K count distribution (capped at 10): {sorted(tenk_hist.items())}")

    payload = {
        "run_at": now.isoformat(timespec="minutes"),
        "universe_size": len(SCREENING_UNIVERSE),
        "tickers_with_stored_filings": len(per_ticker),
        "zero_10k_tickers": zero_10k,
        "ten_k_count_distribution": {str(k): v for k, v in sorted(tenk_hist.items())},
        "note": (
            "Measurement only. The zero-10-K signal does NOT separate a successor shell "
            "from a genuinely recent listing; see the memo beside this file."
        ),
    }
    out = HERE / f"successor_shell_measurement_{now.strftime('%Y-%m-%dT%H%MZ')}.json"
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"written {out.relative_to(_BACKEND)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
