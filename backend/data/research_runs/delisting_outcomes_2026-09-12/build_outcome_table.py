import csv
import gzip
import json
import statistics
from collections import defaultdict
from datetime import date as ddate
from pathlib import Path

STORE = Path("/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend/data/price_store_alpaca/v1")
DEAD_NAMES_CSV = Path("data/research_runs/delisting_outcomes_2026-09-12/dead_names.csv")
RAW_CACHE = Path("data/research_runs/delisting_outcomes_2026-09-12/corporate_actions_raw.json.gz")
OUT_CSV = Path("data/research_runs/delisting_outcomes_2026-09-12/delisting_outcomes.csv")
SUSPECT_CSV = Path("data/research_runs/delisting_outcomes_2026-09-12/suspect_rows.csv")

_price_cache = {}

TYPE_PRIORITY = {"stock_and_cash_merger": 0, "stock_merger": 1, "cash_merger": 2}


def acquirer_close_on(symbol, date):
    """Look up symbol's close on `date` in the full store (not just dead names).
    Falls back to nearest prior trading day within 5 calendar days if exact date absent
    (Alpaca bars may not exist on holidays / the effective_date itself if it's a weekend
    for the record date convention used by the vendor)."""
    key = symbol
    if key not in _price_cache:
        fp = STORE / f"{symbol}.csv.gz"
        rows = {}
        if fp.exists():
            with gzip.open(fp, "rt", newline="") as f:
                for row in csv.DictReader(f):
                    rows[row["date"]] = float(row["close"])
        _price_cache[key] = rows
    rows = _price_cache[key]
    if date in rows:
        return rows[date], date, "exact"
    dates_sorted = sorted(d for d in rows if d <= date)
    if dates_sorted:
        nearest = dates_sorted[-1]
        d1 = ddate.fromisoformat(nearest)
        d2 = ddate.fromisoformat(date)
        if (d2 - d1).days <= 5:
            return rows[nearest], nearest, "nearest_prior"
    return None, None, "not_found"


def group_by_symbol(records, symbol_field="acquiree_symbol"):
    g = defaultdict(list)
    for r in records:
        g[r[symbol_field]].append(r)
    return g


def _event_date(kind, r):
    if kind == "name_change":
        return r.get("process_date")
    if kind in ("reverse_split", "forward_split"):
        return r.get("ex_date") or r.get("process_date")
    if kind == "redemption":
        return r.get("payable_date") or r.get("process_date")
    if kind == "worthless_removal":
        return r.get("process_date")
    return r.get("effective_date")


def select_event_record(ticker, last_bar, cash_g, stock_g, stock_cash_g, other_by_symbol):
    """Gather EVERY candidate corporate-action record for this ticker -- the three
    merger types plus name_change/reverse_split/forward_split/redemption/
    worthless_removal -- and pick whichever single event is closest in date to
    last_bar (the date the ticker actually stopped trading). This matters
    because a ticker can carry a merger record from a totally unrelated,
    much-earlier or much-later event on a DIFFERENT cusip (a reused ticker,
    e.g. GV: a 2020-12-30 cash_merger on cusip 381370105 is unrelated to the
    real reason a LATER GV, cusip 92838F200, stopped trading in 2026 -- a
    2026-07-31 name_change to GVHGF), or a stock_merger record with a blank
    acquirer_symbol that is actually a same-day/near-day de-SPAC rename
    (ARYA -> NAUT, 2021-06-10) rather than a genuine third-party acquisition.
    Within a tied date (the same deal recorded once as a bare cash_merger
    "cash-in-lieu-of-fractional-shares" sweep AND once as the real
    stock_and_cash_merger, e.g. ANH/Ready Capital 2021-03-19), prefer the
    richer merger type over a bare cash_merger, and prefer any merger type
    over a same-day non-merger action (a name_change/split recorded on the
    same day as a real merger is presumably describing the same event, and
    the merger record carries the value information).
    Returns (family, type, record, n_total_candidates) where family is
    "merger" or "other", or None if there is no candidate record at all.
    """
    candidates = []  # list of (family, type, record, date_str)
    for typ, gdict in (
        ("cash_merger", cash_g),
        ("stock_merger", stock_g),
        ("stock_and_cash_merger", stock_cash_g),
    ):
        for r in gdict.get(ticker, []):
            candidates.append(("merger", typ, r, r["effective_date"]))
    for typ, r in other_by_symbol.get(ticker, []):
        dt = _event_date(typ, r)
        if dt:
            candidates.append(("other", typ, r, dt))

    if not candidates:
        return None

    last_bar_d = ddate.fromisoformat(last_bar)
    by_date = defaultdict(list)
    for fam, typ, r, dt in candidates:
        by_date[dt].append((fam, typ, r))

    best_date = min(by_date.keys(), key=lambda dt: abs((ddate.fromisoformat(dt) - last_bar_d).days))
    group = by_date[best_date]

    def sort_key(item):
        fam, typ, _r = item
        if fam == "merger":
            return (0, TYPE_PRIORITY[typ])
        return (1, 0)

    group_sorted = sorted(group, key=sort_key)
    chosen_family, chosen_type, chosen_record = group_sorted[0]
    return chosen_family, chosen_type, chosen_record, len(candidates)


def main():
    with open(DEAD_NAMES_CSV) as f:
        dead = list(csv.DictReader(f))

    with gzip.open(RAW_CACHE, "rt") as f:
        raw = json.load(f)
    ca = raw["corporate_actions"]

    cash_g = group_by_symbol(ca.get("cash_mergers", []))
    stock_g = group_by_symbol(ca.get("stock_mergers", []))
    stock_cash_g = group_by_symbol(ca.get("stock_and_cash_mergers", []))

    other_by_symbol = defaultdict(list)
    for r in ca.get("reverse_splits", []):
        other_by_symbol[r["symbol"]].append(("reverse_split", r))
    for r in ca.get("forward_splits", []):
        other_by_symbol[r["symbol"]].append(("forward_split", r))
    for r in ca.get("name_changes", []):
        other_by_symbol[r["old_symbol"]].append(("name_change", r))
    for r in ca.get("redemptions", []):
        other_by_symbol[r["symbol"]].append(("redemption", r))
    for r in ca.get("worthless_removals", []):
        other_by_symbol[r["symbol"]].append(("worthless_removal", r))

    out_rows = []
    suspects = []
    counts = {"cash_merger": 0, "stock_merger": 0, "stock_and_cash_merger": 0, "other_action": 0, "no_action_found": 0}
    cash_merger_returns = []
    multi_record_tickers = []

    for d in dead:
        ticker = d["ticker"]
        last_bar = d["last_bar"]
        last_close = float(d["last_close"])

        row = {
            "ticker": ticker,
            "last_bar": last_bar,
            "last_close": last_close,
            "outcome": None,
            "effective_date": "",
            "acquirer_symbol": "",
            "cash_rate": "",
            "exchange_ratio": "",
            "acquirer_close_used": "",
            "acquirer_close_date": "",
            "price_lookup_method": "",
            "final_value_per_share": "",
            "implied_final_return": "",
            "notes": "",
        }

        sel = select_event_record(ticker, last_bar, cash_g, stock_g, stock_cash_g, other_by_symbol)

        if sel is not None and sel[0] == "other":
            _, chosen_type, r, n_candidates = sel
            eff_date = _event_date(chosen_type, r)
            amb_note = (
                f" [{n_candidates} corporate-action records found across all types for this symbol; "
                f"picked the {chosen_type} record whose date is closest to last_bar]"
                if n_candidates > 1
                else ""
            )
            if n_candidates > 1:
                multi_record_tickers.append((ticker, n_candidates, chosen_type))
            row.update(
                outcome="other_action",
                effective_date=eff_date or "",
                notes=(
                    f"non-merger corporate action: {chosen_type}; no cash/stock value implied by this type"
                    + amb_note
                ),
            )
            counts["other_action"] += 1

        elif sel is not None and sel[0] == "merger":
            _, chosen_type, r, n_candidates = sel
            ambiguous = n_candidates > 1
            amb_note = (
                f" [{n_candidates} corporate-action records found across all types for this symbol; "
                f"picked the {chosen_type} record whose effective_date is closest to last_bar "
                "-- likely a reused ticker or a residual/fractional-share sweep alongside the "
                "real deal, see corporate_actions_raw.json.gz]"
                if ambiguous
                else ""
            )
            if ambiguous:
                multi_record_tickers.append((ticker, n_candidates, chosen_type))

            if chosen_type == "cash_merger":
                rate = float(r["rate"])
                row.update(
                    outcome="cash_merger",
                    effective_date=r["effective_date"],
                    acquirer_symbol=r.get("acquirer_symbol", ""),
                    cash_rate=rate,
                    final_value_per_share=rate,
                    implied_final_return=rate / last_close - 1,
                    notes=amb_note.strip(),
                )
                counts["cash_merger"] += 1
                cash_merger_returns.append(rate / last_close - 1)

            elif chosen_type == "stock_and_cash_merger":
                cash_rate = float(r.get("cash_rate", 0) or 0)
                acquirer_rate = float(r.get("acquirer_rate", 0) or 0)
                acquiree_rate = float(r.get("acquiree_rate", 1) or 1)
                ratio = acquirer_rate / acquiree_rate if acquiree_rate else None
                acquirer_symbol = r.get("acquirer_symbol", "")
                eff_date = r["effective_date"]
                aclose, adate, method = (None, None, "no_acquirer_symbol")
                if acquirer_symbol:
                    aclose, adate, method = acquirer_close_on(acquirer_symbol, eff_date)
                stock_component = ratio * aclose if (ratio is not None and aclose is not None) else None
                final_value = cash_rate + stock_component if stock_component is not None else None
                row.update(
                    outcome="stock_and_cash_merger",
                    effective_date=eff_date,
                    acquirer_symbol=acquirer_symbol,
                    cash_rate=cash_rate,
                    exchange_ratio=ratio if ratio is not None else "",
                    acquirer_close_used=aclose if aclose is not None else "",
                    acquirer_close_date=adate if adate else "",
                    price_lookup_method=method,
                    final_value_per_share=final_value if final_value is not None else "",
                    implied_final_return=(final_value / last_close - 1) if final_value is not None else "",
                    notes=(
                        "cash+stock component; stock leg valued at acquirer close (approximation, see limitations)."
                        + amb_note
                    ),
                )
                counts["stock_and_cash_merger"] += 1

            elif chosen_type == "stock_merger":
                acquirer_rate = float(r.get("acquirer_rate", 0) or 0)
                acquiree_rate = float(r.get("acquiree_rate", 1) or 1)
                ratio = acquirer_rate / acquiree_rate if acquiree_rate else None
                acquirer_symbol = r.get("acquirer_symbol", "")
                eff_date = r["effective_date"]
                aclose, adate, method = (None, None, "no_acquirer_symbol")
                if acquirer_symbol:
                    aclose, adate, method = acquirer_close_on(acquirer_symbol, eff_date)
                final_value = ratio * aclose if (ratio is not None and aclose is not None) else None
                base_note = (
                    "valued at acquirer close on effective_date read from the price store (approximation, see limitations)"
                    if final_value is not None
                    else "acquirer close not found in store"
                )
                row.update(
                    outcome="stock_merger",
                    effective_date=eff_date,
                    acquirer_symbol=acquirer_symbol,
                    exchange_ratio=ratio if ratio is not None else "",
                    acquirer_close_used=aclose if aclose is not None else "",
                    acquirer_close_date=adate if adate else "",
                    price_lookup_method=method,
                    final_value_per_share=final_value if final_value is not None else "",
                    implied_final_return=(final_value / last_close - 1) if final_value is not None else "",
                    notes=base_note + amb_note,
                )
                counts["stock_merger"] += 1

        else:
            row.update(outcome="no_action_found")
            counts["no_action_found"] += 1

        out_rows.append(row)

        ifr = row["implied_final_return"]
        if isinstance(ifr, float) and not (-0.90 <= ifr <= 2.00):
            suspects.append(dict(row))

    fieldnames = [
        "ticker",
        "last_bar",
        "last_close",
        "outcome",
        "effective_date",
        "acquirer_symbol",
        "cash_rate",
        "exchange_ratio",
        "acquirer_close_used",
        "acquirer_close_date",
        "price_lookup_method",
        "final_value_per_share",
        "implied_final_return",
        "notes",
    ]
    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(out_rows)

    with open(SUSPECT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(suspects)

    print("COUNTS:", counts)
    print("total:", sum(counts.values()), "vs dead names:", len(dead))
    print(f"tickers with >1 merger-type candidate record: {len(multi_record_tickers)}")
    for t, n, typ in multi_record_tickers:
        print(f"  {t}: {n} candidates, chose {typ}")

    if cash_merger_returns:
        s = sorted(cash_merger_returns)
        n = len(s)

        def pct(p):
            idx = min(n - 1, max(0, round(p * (n - 1))))
            return s[idx]

        print("cash_merger implied_final_return stats:")
        print("  n =", n)
        print("  min =", s[0])
        print("  q1 (25th pctile) =", pct(0.25))
        print("  median =", statistics.median(s))
        print("  q3 (75th pctile) =", pct(0.75))
        print("  max =", s[-1])
    print("suspect rows:", len(suspects))
    for sr in suspects:
        print(" SUSPECT:", sr["ticker"], sr["outcome"], sr["implied_final_return"], sr["last_bar"], sr["last_close"])


if __name__ == "__main__":
    main()
