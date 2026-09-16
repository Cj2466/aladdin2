#!/usr/bin/env python
"""Test B collector. Governed by PROTOCOL_2026-09-16.md (@46c48ad),
DEFINITIONS_VERIFIED_2026-09-16.md (@3c4a0e9) and ADDENDUM_01_WINDOWS (@9d3691b),
all committed before this file produced a number.

Collects, per (ticker, session):
  window A (Q1-Q3 only) full regular session 14:30-21:00Z
  window B (all buckets) 17:00-17:05Z midday

and reduces each to statistics. Raw quotes are NOT persisted (volume); every
statistic is written to JSON, one row per ticker-day, appended incrementally so
an interruption is resumable and partial work is never lost.

Nothing here decides anything. The decision rules are section 7 of the protocol.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
COST_CSV = HERE.parent / "a2_cost_2026-09-15" / "a2_per_ticker_cost.csv"
OUT = HERE / "collected_rows.jsonl"
META = HERE / "collection_meta.json"

BASE = "https://data.alpaca.markets"
FEED = "sip"
LAST_DAY = "2026-09-11"          # A2's last bar date, protocol section 3
N_DAYS = 10
PER_BUCKET = {"Q1 least liquid": 40, "Q2": 40, "Q3": 40,
              "Q4": 10, "Q5 most liquid": 10}
PRIMARY = {"Q1 least liquid", "Q2", "Q3"}          # window A + parts 2/3
SESSION = ("14:30:00", "21:00:00")
MIDDAY = ("17:00:00", "17:05:00")
PAGE = 10000
SLEEP = 0.30
MAX_PAGES = 400


def headers() -> dict[str, str]:
    k, s = os.environ.get("ALPACA_API_KEY"), os.environ.get("ALPACA_API_SECRET")
    if not k or not s:
        raise SystemExit("ALPACA_API_KEY / ALPACA_API_SECRET not in environment")
    return {"APCA-API-KEY-ID": k, "APCA-API-SECRET-KEY": s}


def get_pages(client: httpx.Client, sym: str, kind: str, start: str, end: str,
              hdr: dict) -> tuple[list[dict], bool]:
    """Paginate one endpoint over one window. Returns (items, truncated)."""
    items: list[dict] = []
    token = None
    for _ in range(MAX_PAGES):
        p = {"start": start, "end": end, "limit": PAGE, "feed": FEED}
        if token:
            p["page_token"] = token
        for attempt in range(5):
            r = client.get(f"/v2/stocks/{sym}/{kind}", params=p, headers=hdr, timeout=90.0)
            if r.status_code == 429:
                time.sleep(2.0 * (attempt + 1))
                continue
            break
        if r.status_code != 200:
            raise RuntimeError(f"{sym} {kind} HTTP {r.status_code}: {r.text[:200]}")
        d = r.json()
        items.extend(d.get(kind) or [])
        token = d.get("next_page_token")
        time.sleep(SLEEP)
        if not token:
            return items, False
    return items, True


def ts(s: str) -> float:
    """RFC3339 with variable fractional digits -> epoch seconds."""
    if s.endswith("Z"):
        s = s[:-1]
    if "." in s:
        head, frac = s.split(".", 1)
        frac = (frac + "000000000")[:9]
        return datetime.fromisoformat(head).replace(tzinfo=timezone.utc).timestamp() + int(frac) / 1e9
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp()


# ADDENDUM_02: CTA CTS Output Spec 2015-11-06 p.118, OPEN/LAST/HIGH/LOW table.
# Every code whose CONSOLIDATED LAST is NO or footnoted, plus the auction and
# reopening prints, which are LAST-eligible but are not executions against a
# continuous two-sided quote. Blank bytes are category fillers, not conditions.
EXCLUDE_CONDITIONS = set("BCHLMNOPQRTUVZ456789")
ODD_LOT = "I"


def trade_ok(tr: dict, allow_odd_lot: bool) -> bool:
    """F1 strict when allow_odd_lot is False; F2 retail when True."""
    codes = tr.get("c") or []
    if any(c in EXCLUDE_CONDITIONS for c in codes):
        return False
    if not allow_odd_lot and ODD_LOT in codes:
        return False
    return True


def valid(q: dict) -> bool:
    """A usable two-sided NBBO. Crossed/locked and zero quotes are not."""
    b, a = q.get("bp") or 0.0, q.get("ap") or 0.0
    return b > 0 and a > 0 and a > b


def time_weighted_half_bp(quotes: list[dict], t0: float, t1: float,
                          seed: dict | None) -> tuple[float | None, float]:
    """Time-weighted half-spread in bp over [t0,t1], carrying each NBBO forward
    until the next update (the vendor sends updates, not a continuous state).
    Returns (half_bp, covered_fraction_of_window)."""
    state = seed if seed and valid(seed) else None
    num = 0.0
    covered = 0.0
    cur = t0
    for q in quotes:
        t = ts(q["t"])
        if t <= t0:
            if valid(q):
                state = q
            continue
        if t >= t1:
            break
        if state is not None:
            dt = t - cur
            mid = (state["bp"] + state["ap"]) / 2.0
            num += dt * ((state["ap"] - state["bp"]) / 2.0 / mid * 10000.0)
            covered += dt
        cur = t
        if valid(q):
            state = q
    if state is not None and cur < t1:
        dt = t1 - cur
        mid = (state["bp"] + state["ap"]) / 2.0
        num += dt * ((state["ap"] - state["bp"]) / 2.0 / mid * 10000.0)
        covered += dt
    if covered <= 0:
        return None, 0.0
    return num / covered, covered / (t1 - t0)


def effective_half_bp(trades: list[dict], quotes: list[dict], t0: float, t1: float,
                      seed: dict | None, allow_odd_lot: bool = True) -> tuple[float | None, int]:
    """Share-weighted |P - M| / M in bp, M = last NBBO at or before the trade.
    This is HALF the Rule 605 effective spread, relative, in bp. See
    DEFINITIONS_VERIFIED_2026-09-16.md for the three logged deviations."""
    state = seed if seed and valid(seed) else None
    qi = 0
    num = 0.0
    den = 0.0
    n = 0
    qs = [(ts(q["t"]), q) for q in quotes]
    for tr in trades:
        t = ts(tr["t"])
        if t < t0 or t >= t1:
            continue
        if not trade_ok(tr, allow_odd_lot):
            continue
        while qi < len(qs) and qs[qi][0] <= t:
            if valid(qs[qi][1]):
                state = qs[qi][1]
            qi += 1
        if state is None:
            continue
        mid = (state["bp"] + state["ap"]) / 2.0
        if mid <= 0:
            continue
        sz = float(tr.get("s") or 0)
        if sz <= 0:
            continue
        num += sz * abs(float(tr["p"]) - mid) / mid * 10000.0
        den += sz
        n += 1
    return (num / den if den > 0 else None), n


def session_dates(client: httpx.Client, hdr: dict) -> list[str]:
    """The N_DAYS most recent complete regular sessions ending LAST_DAY, taken
    from SPY's own daily bars so the exchange calendar is the source."""
    r = client.get("/v2/stocks/SPY/bars",
                   params={"start": "2026-07-01", "end": LAST_DAY, "timeframe": "1Day",
                           "limit": 200, "feed": FEED}, headers=hdr, timeout=60.0)
    r.raise_for_status()
    days = [b["t"][:10] for b in r.json()["bars"]]
    days = [d for d in days if d <= LAST_DAY]
    return days[-N_DAYS:]


def sample_tickers() -> list[dict]:
    rows = list(csv.DictReader(COST_CSV.open()))
    buckets: dict[str, list[dict]] = {}
    for r in rows:
        buckets.setdefault(r["liquidity_bucket"], []).append(r)
    picked = []
    for b, n in PER_BUCKET.items():
        rs = sorted(buckets[b], key=lambda r: r["symbol"])
        step = max(1, len(rs) // n)
        for r in rs[::step][:n]:
            picked.append({"symbol": r["symbol"], "bucket": b,
                           "median_close": float(r["median_close"]),
                           "median_dollar_volume": float(r["median_dollar_volume"]),
                           "edge_floored_half_bp": float(r["edge_floored_half_bp"]),
                           "tick_floor_half_bp": float(r["tick_floor_half_bp"])})
    return picked


def main() -> int:
    hdr = headers()
    done = set()
    if OUT.exists():
        for line in OUT.open():
            try:
                d = json.loads(line)
                done.add((d["symbol"], d["day"]))
            except json.JSONDecodeError:
                pass
    with httpx.Client(base_url=BASE) as client:
        days = session_dates(client, hdr)
        picked = sample_tickers()
        META.write_text(json.dumps(
            {"protocol": "PROTOCOL_2026-09-16.md @46c48ad + ADDENDUM_01 @9d3691b",
             "generated_utc": datetime.now(timezone.utc).isoformat(),
             "days": days, "n_days": len(days),
             "tickers": picked, "n_tickers": len(picked),
             "window_A": SESSION, "window_B": MIDDAY, "feed": FEED}, indent=1))
        print(f"days={days}\ntickers={len(picked)} already_done={len(done)}", flush=True)

        fh = OUT.open("a")
        for tk in picked:
            sym, bucket = tk["symbol"], tk["bucket"]
            primary = bucket in PRIMARY
            for day in days:
                if (sym, day) in done:
                    continue
                row = dict(tk); row["day"] = day
                a0, a1 = ts(f"{day}T{SESSION[0]}"), ts(f"{day}T{SESSION[1]}")
                b0, b1 = ts(f"{day}T{MIDDAY[0]}"), ts(f"{day}T{MIDDAY[1]}")
                try:
                    if primary:
                        q, qt = get_pages(client, sym, "quotes", f"{day}T{SESSION[0]}Z",
                                          f"{day}T{SESSION[1]}Z", hdr)
                        t, tt = get_pages(client, sym, "trades", f"{day}T{SESSION[0]}Z",
                                          f"{day}T{SESSION[1]}Z", hdr)
                        row["truncated"] = qt or tt
                        row["n_quotes"], row["n_trades"] = len(q), len(t)
                        qa, qb = q, [x for x in q if b0 <= ts(x["t"]) < b1]
                        seed_b = None
                        for x in q:
                            if ts(x["t"]) <= b0 and valid(x):
                                seed_b = x
                        ta, tb = t, [x for x in t if b0 <= ts(x["t"]) < b1]
                    else:
                        # anchor: seed from 14:30 then the midday window only
                        q, qt = get_pages(client, sym, "quotes", f"{day}T{MIDDAY[0]}Z",
                                          f"{day}T{MIDDAY[1]}Z", hdr)
                        t, tt = get_pages(client, sym, "trades", f"{day}T{MIDDAY[0]}Z",
                                          f"{day}T{MIDDAY[1]}Z", hdr)
                        row["truncated"] = qt or tt
                        row["n_quotes"], row["n_trades"] = len(q), len(t)
                        qa = qb = q
                        ta = tb = t
                        seed_b = None
                        if not any(valid(x) for x in q):
                            sq, _ = get_pages(client, sym, "quotes", f"{day}T{SESSION[0]}Z",
                                              f"{day}T{MIDDAY[0]}Z", hdr)
                            for x in sq:
                                if valid(x):
                                    seed_b = x

                    if primary:
                        row["A_quoted_half_bp"], row["A_covered"] = time_weighted_half_bp(qa, a0, a1, None)
                        row["A_eff_half_bp_F2"], row["A_n_eff_F2"] = effective_half_bp(ta, qa, a0, a1, None, True)
                        row["A_eff_half_bp_F1"], row["A_n_eff_F1"] = effective_half_bp(ta, qa, a0, a1, None, False)
                        vq = [x for x in qa if valid(x) and a0 <= ts(x["t"]) < a1]
                        row["A_min_ask"] = min((x["ap"] for x in vq), default=None)
                        row["A_max_bid"] = max((x["bp"] for x in vq), default=None)
                        if vq:
                            f = vq[0]
                            row["open_bid"], row["open_ask"] = f["bp"], f["ap"]
                            row["open_t"] = f["t"]
                        vt = [x for x in ta if a0 <= ts(x["t"]) < a1 and trade_ok(x, True)]
                        row["close_price"] = vt[-1]["p"] if vt else None
                        row["n_trades_kept_F2"] = len(vt)
                        row["n_valid_quotes"] = len(vq)
                    row["B_quoted_half_bp"], row["B_covered"] = time_weighted_half_bp(qb, b0, b1, seed_b)
                    row["B_eff_half_bp_F2"], row["B_n_eff_F2"] = effective_half_bp(tb, qb, b0, b1, seed_b, True)
                    row["B_eff_half_bp_F1"], row["B_n_eff_F1"] = effective_half_bp(tb, qb, b0, b1, seed_b, False)
                    if row["B_quoted_half_bp"] is None:
                        row["no_quote_state"] = True
                    row["error"] = None
                except Exception as exc:  # recorded, never silently skipped
                    row["error"] = f"{type(exc).__name__}: {exc}"[:300]
                fh.write(json.dumps(row) + "\n")
                fh.flush()
            print(f"{sym:6s} {bucket:16s} done", flush=True)
        fh.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
