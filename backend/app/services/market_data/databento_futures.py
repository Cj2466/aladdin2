"""Databento historical OHLCV-1d ingestion plan for the TSMOM futures
universe -- CME Globex (GLBX.MDP3) for the 31 CME-Group roots and ICE
Futures U.S. (IFUS.IMPACT) for KC/SB/CT. Built 2026-09-07 for the
futures-data-sourcing task. NOTHING HERE HAS BEEN RUN AGAINST A LIVE KEY:
this project has no Databento account, and creating one (and spending its
credit) is the project owner's decision. The module is written so that
pasting DATABENTO_API_KEY into backend/.env and installing the `databento`
package is all that remains.

FACTS VERIFIED 2026-09-07 IN THIS SESSION (sources named per line):
  * "Sign up and get $125 in free credits" ... credits "expire 6 months
    after signup and each team is eligible for one set of credits"
    (databento.com/pricing, fetched live). Historical data is
    "usage-based pricing ($/GB)" with "No subscription required".
  * Historical usage-based pricing "will remain one of Databento's core
    features" after the April 2025 move of LIVE CME data to subscription
    plans ($179/mo Standard) -- the prior run's "USD 179/mo" figure was
    the LIVE plan, not historical (databento.com/blog/introducing-new-cme-
    pricing-plans and .../upcoming-changes-to-pricing-plans-in-january-2025,
    via search snippets).
  * ES on GLBX.MDP3: "Since 2010-06-06 UTC"; KC on IFUS.IMPACT: "Since
    2018-12-23 UTC"; both list OHLCV-1d among schemas (catalog pages
    databento.com/catalog/cme/GLBX.MDP3/futures/ES and
    databento.com/catalog/ifus/IFUS.IMPACT/futures/KC, fetched live).
  * The Python client (databento 0.86.0 wheel, read from source, not
    installed): Historical.metadata.get_cost "Request the cost in US
    dollars for historical streaming or batched files ... This cost
    respects any discounts provided by flat rate plans"; parameters
    dataset, start, end, symbols, schema (includes 'ohlcv-1d'), stype_in;
    Historical.metadata.list_unit_prices "List unit prices for each feed
    mode and data schema in US dollars per gigabyte";
    Historical.metadata.get_billable_size "the billable uncompressed raw
    binary size". Both endpoints need the key (hist.databento.com answers
    401 {"detail":"Not authenticated"} without one -- probed live).
  * SType.PARENT: 'A Databento-specific symbology for referring to a group
    of symbols by one "parent" symbol, e.g. ES.FUT to refer to all ES
    futures.' SType.CONTINUOUS: 'one symbol may point to different
    instruments at different points of time, e.g. to always refer to the
    front month future.' (databento_dbn 0.69.0 _lib.pyi docstrings.)
    CONTINUOUS symbols are NOT used here: they are the same shape as
    Yahoo's `=F` (a front-month splice) and this project chains
    individual contracts per MOP (2012) Section 2.1 instead.
  * DBN OHLCV record size: OHLCVMsg.size_hint() == 56 bytes (databento_dbn
    0.69.0, called in this session). That is the basis of the SIZE
    ESTIMATE below; the DOLLAR figure needs list_unit_prices with a key.

SIZE ESTIMATE (an estimate, labelled as such): per-contract daily bars for
31 roots x ~16 years x ~250 days x (contracts with trades that day, taken
as 8) ~= 1.0e6 records x 56 B ~= 56 MB for GLBX.MDP3, plus KC/SB/CT
~7 yrs x 250 x 8 x 3 x 56 B ~= 2 MB for IFUS.IMPACT. At the "from $0.50
per gigabyte" floor quoted on databento.com/historical (search snippet)
that is cents; even at 100x that unit price it is under USD 10, i.e.
inside the USD 125 credit by a wide margin. estimate_cost() below turns
this into Databento's own number the moment a key exists.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

GLBX_DATASET = "GLBX.MDP3"
IFUS_DATASET = "IFUS.IMPACT"
SCHEMA = "ohlcv-1d"
STYPE_IN = "parent"
GLBX_START = date(2010, 6, 6)
IFUS_START = date(2018, 12, 23)
FREE_CREDIT_USD = 125.0
OHLCV_RECORD_BYTES = 56

GLBX_ROOTS = [
    "ES", "NQ", "YM", "RTY", "ZT", "ZF", "ZN", "ZB", "6E", "6J", "6B", "6A", "6C", "6S",
    "CL", "BZ", "NG", "HO", "RB", "GC", "SI", "HG", "PL", "PA",
    "ZC", "ZS", "ZW", "ZL", "ZM", "LE", "HE",
]
IFUS_ROOTS = ["KC", "SB", "CT"]


@dataclass(frozen=True)
class RequestPlan:
    dataset: str
    symbols: list[str]  # parent symbols, e.g. "ES.FUT"
    start: date
    end: date
    schema: str = SCHEMA
    stype_in: str = STYPE_IN

    def as_kwargs(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "symbols": self.symbols,
            "schema": self.schema,
            "stype_in": self.stype_in,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
        }


def parent_symbol(root: str) -> str:
    return f"{root}.FUT"


def build_plans(end: date) -> list[RequestPlan]:
    return [
        RequestPlan(GLBX_DATASET, [parent_symbol(r) for r in GLBX_ROOTS], GLBX_START, end),
        RequestPlan(IFUS_DATASET, [parent_symbol(r) for r in IFUS_ROOTS], IFUS_START, end),
    ]


def estimated_bytes(plan: RequestPlan, *, contracts_per_day: int = 8, trading_days_per_year: int = 250) -> int:
    """Back-of-envelope size, labelled an estimate everywhere it is printed."""
    years = (plan.end - plan.start).days / 365.25
    return int(len(plan.symbols) * years * trading_days_per_year * contracts_per_day * OHLCV_RECORD_BYTES)


def api_key_from_env() -> str | None:
    return os.environ.get("DATABENTO_API_KEY") or None


def make_client(key: str | None = None):
    """Import lazily: `databento` is not a project dependency yet."""
    key = key or api_key_from_env()
    if not key:
        raise RuntimeError("DATABENTO_API_KEY is not set; paste it into backend/.env")
    import databento

    return databento.Historical(key)


def estimate_cost(client, plans: list[RequestPlan]) -> list[dict[str, Any]]:
    """Databento's own USD cost and billable size per plan, plus the unit
    price table, via the documented metadata endpoints. Spends nothing."""
    out = []
    for p in plans:
        kw = p.as_kwargs()
        out.append(
            {
                "dataset": p.dataset,
                "symbols": p.symbols,
                "start": kw["start"],
                "end": kw["end"],
                "schema": p.schema,
                "cost_usd": float(client.metadata.get_cost(**kw)),
                "billable_bytes": int(client.metadata.get_billable_size(**kw)),
                "unit_prices": client.metadata.list_unit_prices(p.dataset),
                "estimated_bytes_offline": estimated_bytes(p),
            }
        )
    return out


def pull_ohlcv_1d(client, plan: RequestPlan, out_dir: Path) -> dict[str, Any]:
    """timeseries.get_range -> DataFrame -> one CSV per root under
    <out_dir>/<dataset>/. Symbol column carries the raw contract symbol
    (e.g. ESH0), so a MOP Section 2.1 chain can be built per contract."""
    store = client.timeseries.get_range(**plan.as_kwargs())
    frame = store.to_df()
    frame = frame.reset_index()
    frame["root"] = frame["symbol"].astype(str).str.extract(r"^([A-Z0-9]+?)[FGHJKMNQUVXZ]\d{1,2}$")[0]
    target = out_dir / plan.dataset
    target.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for root, g in frame.groupby("root"):
        g.to_csv(target / f"{root}.csv", index=False)
        counts[str(root)] = len(g)
    return {"dataset": plan.dataset, "rows": len(frame), "per_root": counts}


def dry_run_summary(end: date | None = None) -> pd.DataFrame:
    end = end or datetime.now(UTC).date()
    rows = []
    for p in build_plans(end):
        rows.append({"dataset": p.dataset, "n_roots": len(p.symbols), "start": p.start, "end": end, "schema": p.schema, "stype_in": p.stype_in, "estimated_MB": round(estimated_bytes(p) / 1e6, 1)})
    return pd.DataFrame(rows)
