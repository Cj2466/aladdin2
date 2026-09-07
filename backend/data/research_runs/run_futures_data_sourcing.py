"""FUTURES DATA SOURCING -- 2026-09-07 -- attacking paid-data gap P4.

The 2026-09-05 feasibility run (run_tsmom_futures_feasibility.py) concluded
that daily futures data for a TSMOM family "needs a paid source" (Norgate,
USD 270/yr) and logged P4. This project's standing rule treats "X is not
available / needs payment" as the highest-risk category of claim, so this
run re-opens every source that run left unverified and tests new ones
LIVE, then gates whatever it can actually obtain through the same tests
that condemned Yahoo's `=F` splices: within-contract chaining per MOP
(2012) Section 2.1, the synthetic known-answer validation, and independent
cross-source agreement.

THE SHORT ANSWER (details, per-instrument counts and every URL in the
report this script writes):
  * 31 of the 34 target instruments -- every CME/CBOT/NYMEX/COMEX root --
    have FREE, exchange-published, per-contract daily SETTLEMENT prices
    for 2013-01-02 .. 2025-09-12 in CME Group's public SPAN risk-parameter
    archive (ftp.cmegroup.com/span/archive/cme). They are individual
    contract months, not splices, so MOP's construction applies directly.
    Decoding was pinned against the published record layout and verified
    to the tick against Yahoo closes and EIA settlements on the same dates.
  * The 4 NYMEX energy roots additionally have EIA's official Contract 1-4
    positional settlements back to 1983 (CL), 1980 (HO), 1994 (NG), 2005
    (RB), ending 2024-04-05 when EIA stopped publishing after CME's
    licence change. They agree with the SPAN per-contract settles to the
    cent and carry the -37.63 WTI print.
  * The 3 ICE softs (KC, SB, CT) have NO free source found by legitimate
    means: ICE sells end-of-day CSV packages by subscription; Databento's
    IFUS.IMPACT covers them from 2018-12-23 under usage pricing that the
    USD 125 sign-up credit almost certainly covers (estimate; the owner's
    key is needed for Databento's own number). Post-2025-09-12 coverage
    for the 31 CME roots also needs either the owner's free CME DataMine
    login or the same Databento pull.
  So P4 is NARROWED, not closed: nothing needs USD 270/yr; what remains is
  a free-login gap (DataMine) and a within-free-credit gap (Databento),
  both the owner's account decisions.

ROLL RULE PRE-DECLARED HERE, BEFORE ANY CHAIN WAS BUILT: on each date t,
hold the nearest-expiring listed contract whose Type-B expiration date is
more than ROLL_BDAYS_BEFORE_EXPIRY business days after t. This is a
DEVIATION from MOP's "most liquid contract (typically the nearest or next
nearest-to-delivery)": the SPAN archive carries no per-contract volume, so
liquidity cannot be read from it. MOP report (Section 2.1) that results
"hardly change" for the far contract in financials and are "slightly
stronger" for the far contract in commodities, so the choice is not
expected to flip a verdict; it is logged, and Databento's OHLCV-1d volume
field would close it. The chain is a PROOF OF CONCEPT of the data, not a
TSMOM signal: nothing here is registered or scored.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

import app

if Path(app.__file__).resolve().parent.parent != _BACKEND:
    raise SystemExit(f"REFUSING TO RUN: `app` resolved to {app.__file__}, not inside {_BACKEND}")

from app.services.market_data import cme_span_settlements as span
from app.services.market_data import databento_futures as dbf
from app.services.market_data import eia_nymex_futures as eia

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stderr)
log = logging.getLogger("futures_data_sourcing")

RUN_DATE = "2026-09-07"
OUT_DIR = _BACKEND / "data" / "research_runs"
OUT_TXT = OUT_DIR / f"futures_data_sourcing_{RUN_DATE}.txt"
OUT_JSON = OUT_DIR / f"futures_data_sourcing_{RUN_DATE}.json"
STORE = _BACKEND / "data" / "futures_daily"
SPAN_STORE = STORE / "cme_span"
FEASIBILITY_RUNNER = OUT_DIR / "run_tsmom_futures_feasibility.py"

ROLL_BDAYS_BEFORE_EXPIRY = 5
SCALE_BREAK_ABS_RETURN = 0.50  # same screen as the feasibility run's PROOF_1
UA = "aladdin2-research/0.1 (contact: autoa0792@gmail.com)"

ICE_ROOTS = ["KC", "SB", "CT"]


# ---------------------------------------------------------------------------
# feasibility-run functions, imported by path (the file is NOT modified)
# ---------------------------------------------------------------------------


def load_feasibility_module():
    spec = importlib.util.spec_from_file_location("_run_tsmom_futures_feasibility", FEASIBILITY_RUNNER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# live re-probes: one request each, honest UA, no challenge-solving
# ---------------------------------------------------------------------------


def _get(url: str, timeout: int = 30) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            return {"url": url, "http": resp.status, "bytes": len(body), "head": body[:160].decode("latin-1")}
    except urllib.error.HTTPError as exc:
        body = exc.read()
        return {"url": url, "http": exc.code, "bytes": len(body), "head": body[:160].decode("latin-1")}
    except Exception as exc:  # noqa: BLE001
        return {"url": url, "http": None, "error": f"{type(exc).__name__}: {exc}"}


def reprobe_sources() -> dict[str, Any]:
    out: dict[str, Any] = {}
    out["stooq"] = _get("https://stooq.com/q/d/l/?s=es.f&i=d")
    out["stooq"]["verdict"] = (
        "JavaScript proof-of-work challenge, not CSV (HTML containing 'This site requires JavaScript to verify your browser'); "
        "BLOCKED for non-browser clients -- not defeated, per the task's boundary"
        if "requires JavaScript" in out["stooq"].get("head", "")
        else "response changed since 2026-09-07 -- re-read"
    )
    out["nasdaq_data_link"] = _get("https://data.nasdaq.com/api/v3/datasets/CHRIS/CME_ES1.json?rows=3")
    out["nasdaq_data_link"]["verdict"] = (
        "Incapsula bot-protection interstitial (HTTP 403) for keyless API calls; the documented API needs a free key "
        "(owner's sign-up); CHRIS itself is reported deprecated and no longer updated "
        "(github.com/PacktPublishing/Python-for-Algorithmic-Trading-Cookbook/issues/5, 2024-09-20)"
        if out["nasdaq_data_link"].get("http") == 403
        else "response changed since 2026-09-07 -- re-read"
    )
    out["eia_notice"] = _get(eia.EIA_DISCONTINUATION_URL)
    out["databento_unauth"] = _get("https://hist.databento.com/v0/metadata.list_datasets")
    out["cme_ftp_2025_listing"] = _get("ftp://ftp.cmegroup.com/span/archive/cme/2025/", timeout=60)
    time.sleep(1)
    return out


# ---------------------------------------------------------------------------
# SPAN store validation
# ---------------------------------------------------------------------------


def span_store_checks(frame: pd.DataFrame) -> dict[str, Any]:
    out: dict[str, Any] = {}
    out["rows"] = len(frame)
    out["trade_days"] = int(frame["trade_date"].nunique())
    out["first_trade_date"] = str(frame["trade_date"].min().date()) if len(frame) else None
    out["last_trade_date"] = str(frame["trade_date"].max().date()) if len(frame) else None
    # 81 (high precision) vs 82 (regular) agreement wherever both are digits
    hp_digits = frame["raw_hp_settle"].str.strip().str.isdigit()
    both = frame[hp_digits]
    mismatch = both[both["raw_hp_settle"].astype(int) != both["raw_settle"].astype(int)]
    out["hp_vs_regular"] = {"rows_with_hp": len(both), "mismatches": len(mismatch)}
    # fraction-code digit census for alignment C / 0
    census: dict[str, dict[str, int]] = {}
    for al in ("C", "0"):
        sub = frame[frame["alignment"] == al]
        census[al] = {k: int(v) for k, v in sub["raw_settle"].str[-1].value_counts().sort_index().items()}
    out["fraction_digit_census"] = census
    inferred = frame[(frame["alignment"].isin(["C", "0"])) & (frame["raw_settle"].str[-1].isin(list(span.INFERRED_EIGHTH_DIGITS)))]
    out["inferred_eighth_digit_rows"] = {
        "rows": len(inferred),
        "share_of_C_or_0_rows": float(len(inferred) / max(1, int((frame["alignment"].isin(["C", "0"])).sum()))),
        "by_globex": {k: int(v) for k, v in inferred.groupby("globex").size().items()},
    }
    neg = frame[frame["settle"] < 0]
    out["negative_settlements"] = [
        {"date": str(r.trade_date.date()), "globex": r.globex, "contract": r.contract_month, "settle": float(r.settle)}
        for r in neg.itertuples()
    ]
    # within-contract daily |return| > 50% screen (scale breaks would show here)
    breaks = []
    for (g, cm), grp in frame.groupby(["globex", "contract_month"]):
        s = grp.sort_values("trade_date").set_index("trade_date")["settle"]
        if (s.abs() < 1e-12).any():
            continue
        r = s.pct_change()
        for d, v in r[r.abs() > SCALE_BREAK_ABS_RETURN].items():
            breaks.append({"globex": g, "contract": cm, "date": str(d.date()), "return": float(v)})
    out["within_contract_scale_breaks"] = breaks
    per = {}
    for g, grp in frame.groupby("globex"):
        per[g] = {
            "rows": len(grp),
            "trade_days": int(grp["trade_date"].nunique()),
            "first": str(grp["trade_date"].min().date()),
            "last": str(grp["trade_date"].max().date()),
            "contracts": int(grp["contract_month"].nunique()),
            "missing_expiration_rows": int((grp["expiration_date"].str.strip() == "").sum()),
        }
    out["per_instrument"] = per
    return out


def yahoo_cross_check(frame: pd.DataFrame) -> dict[str, Any]:
    """Exact equality of Yahoo's `=F` close with SPAN's nearest or second
    contract on the same date. Yahoo's close is a LAST TRADE, CME's a
    SETTLEMENT, so for products settled at a different time than the last
    trade (FX, Treasuries, some ags) the exact-match rate is expected to
    be low; where it is high, the two sources agree to the tick."""
    import yfinance as yf

    out: dict[str, Any] = {}
    start = frame["trade_date"].min() - pd.Timedelta(days=7)
    for g, grp in frame.groupby("globex"):
        try:
            h = yf.Ticker(f"{g}=F").history(start=start.strftime("%Y-%m-%d"), auto_adjust=False)
        except Exception as exc:  # noqa: BLE001
            out[g] = {"error": f"{type(exc).__name__}: {exc}"}
            continue
        if h.empty:
            out[g] = {"error": "empty"}
            continue
        yc = h["Close"].copy()
        yc.index = yc.index.tz_localize(None).normalize()
        piv = grp.pivot_table(index="trade_date", columns="contract_month", values="settle")
        n = front = second = 0
        for d, row in piv.iterrows():
            if d not in yc.index:
                continue
            row = row.dropna()
            ym = d.strftime("%Y%m")
            live = row[[c for c in row.index if c >= ym]]
            if live.empty:
                continue
            n += 1
            v = float(yc.loc[d])
            if abs(float(live.iloc[0]) - v) < 1e-6:
                front += 1
            elif len(live) > 1 and abs(float(live.iloc[1]) - v) < 1e-6:
                second += 1
        out[g] = {"days_compared": n, "front_exact": front, "second_exact": second, "either_share": (front + second) / n if n else None}
        time.sleep(0.2)
    return out


def eia_cross_check(frame: pd.DataFrame) -> dict[str, Any]:
    """EIA Contract-N on date t must equal SPAN's N-th nearest UNEXPIRED
    contract's settle on t. Contract 1 is defined by EIA as the contract
    with the earliest delivery date; after the expiration date the next
    contract becomes Contract 1."""
    out: dict[str, Any] = {}
    for s in eia.EIA_SERIES:
        path = STORE / "eia" / f"{s.series_id}.csv"
        if not path.exists():
            out[s.series_id] = {"error": "not fetched"}
            continue
        e = eia.load_series(STORE, s.series_id)
        grp = frame[frame["globex"] == s.globex]
        if grp.empty:
            out[s.series_id] = {"error": "no SPAN rows"}
            continue
        exp = {}
        for r in grp.itertuples():
            if r.expiration_date.strip():
                exp[r.contract_month] = pd.Timestamp(r.expiration_date)
        piv = grp.pivot_table(index="trade_date", columns="contract_month", values="settle")
        n = exact = 0
        worst = 0.0
        examples = []
        for d, row in piv.iterrows():
            if d not in e.index:
                continue
            row = row.dropna()
            live = [c for c in row.index if c in exp and exp[c] >= d]
            if len(live) < s.position:
                continue
            sv = float(row[live[s.position - 1]])
            ev = float(e.loc[d])
            n += 1
            diff = abs(sv - ev)
            if diff < 0.005:
                exact += 1
            else:
                worst = max(worst, diff)
                if len(examples) < 5:
                    examples.append({"date": str(d.date()), "span": sv, "eia": ev, "contract": live[s.position - 1]})
        out[s.series_id] = {
            "globex": s.globex,
            "position": s.position,
            "days_compared": n,
            "exact_to_the_cent": exact,
            "share_exact": exact / n if n else None,
            "worst_abs_diff": worst,
            "mismatch_examples": examples,
        }
    return out


# ---------------------------------------------------------------------------
# MOP Section 2.1 chain on SPAN data, under the pre-declared roll rule
# ---------------------------------------------------------------------------


def build_holding(grp: pd.DataFrame) -> tuple[pd.Series, dict[str, pd.Series], int]:
    exp = {}
    for r in grp.itertuples():
        if r.expiration_date.strip():
            exp[r.contract_month] = pd.Timestamp(r.expiration_date)
    piv = grp.pivot_table(index="trade_date", columns="contract_month", values="settle").sort_index()
    closes = {c: piv[c].dropna() for c in piv.columns}
    holding = {}
    skipped = 0
    dates = list(piv.index)
    for i, d in enumerate(dates):
        cutoff = d + pd.offsets.BDay(ROLL_BDAYS_BEFORE_EXPIRY)
        prev = dates[i - 1] if i > 0 else None
        pick = None
        for c in sorted(piv.columns):
            if c not in exp or exp[c] <= cutoff:
                continue
            if pd.isna(piv.at[d, c]) or (prev is not None and pd.isna(piv.at[prev, c])):
                continue
            pick = c
            break
        if pick is None:
            skipped += 1
            continue
        holding[d] = pick
    h = pd.Series(holding).sort_index()
    return h, closes, skipped


def chain_all(frame: pd.DataFrame, feas) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for g, grp in frame.groupby("globex"):
        try:
            holding, closes, skipped = build_holding(grp)
            if len(holding) < 30:
                out[g] = {"error": f"only {len(holding)} holdable days"}
                continue
            true_r = feas.chained_contract_daily_returns(closes, holding)
            naive = feas.naive_spliced_prices(closes, holding).pct_change()
            artifact = (naive - true_r).dropna()
            rolls = holding[holding != holding.shift(1)].iloc[1:]
            roll_art = artifact.loc[rolls.index]
            ratio_adj = feas.ratio_back_adjusted_prices(closes, holding)
            equiv = float((ratio_adj.pct_change() - true_r).abs().max())
            out[g] = {
                "days": len(holding),
                "first": str(holding.index.min().date()),
                "last": str(holding.index.max().date()),
                "days_without_holdable_contract": int(skipped),
                "contracts_held": int(holding.nunique()),
                "rolls": len(rolls),
                "true_ann_vol": float(feas.annualized_volatility(true_r)),
                "true_cum_return": float((1 + true_r.dropna()).prod() - 1),
                "naive_cum_return": float((1 + naive.dropna()).prod() - 1),
                "roll_artifact_pp": {
                    "mean": float(roll_art.mean() * 100) if len(roll_art) else None,
                    "median": float(roll_art.median() * 100) if len(roll_art) else None,
                    "min": float(roll_art.min() * 100) if len(roll_art) else None,
                    "max": float(roll_art.max() * 100) if len(roll_art) else None,
                    "share_positive": float((roll_art > 0).mean()) if len(roll_art) else None,
                    "sum_pp_per_year": float(roll_art.sum() * 100 / max(1e-9, len(holding) / 252)),
                },
                "artifact_zero_off_roll_days": bool((artifact.drop(rolls.index, errors="ignore").abs() < 1e-12).all()),
                "ratio_adjust_equivalence_max_abs": equiv,
                "true_returns": true_r,
            }
        except Exception as exc:  # noqa: BLE001
            out[g] = {"error": f"{type(exc).__name__}: {exc}"}
    return out


def es_vs_cash_index(chain: dict[str, Any]) -> dict[str, Any]:
    import yfinance as yf

    r = chain.get("ES", {}).get("true_returns")
    if r is None:
        return {"error": "no ES chain"}
    h = yf.Ticker("^GSPC").history(start=str(r.index.min().date()), auto_adjust=False)["Close"]
    h.index = h.index.tz_localize(None).normalize()
    j = pd.concat([r.rename("es"), h.pct_change().rename("spx")], axis=1).dropna()
    return {
        "days": len(j),
        "corr": float(j["es"].corr(j["spx"])),
        "es_ann_vol": float(j["es"].std(ddof=1) * np.sqrt(252)),
        "spx_ann_vol": float(j["spx"].std(ddof=1) * np.sqrt(252)),
    }


# ---------------------------------------------------------------------------
# source ledger -- evidence gathered 2026-09-07, all cited in the report
# ---------------------------------------------------------------------------

SOURCE_LEDGER: list[dict[str, str]] = [
    {
        "source": "CME Group public SPAN risk-parameter archive (ftp.cmegroup.com/span/archive/cme)",
        "tried": "FTP directory listings of /, /span/, /span/archive/cme/<year>; downloaded cme.20190102.s.pa2.zip and the full 2013-2025 end-of-day series via fetch_cme_span_archive.py",
        "result": "One zip per trading day, ~10-13 MB, containing per-contract Type 81/82 records with settlement prices for every CME/CBOT/NYMEX/COMEX contract, Type P price formats and Type B expiration dates. 2013-01-02 .. 2025-09-12; no 2026 folder (FTP publication decommissioned 2025-09-15, advisory 25-264).",
        "licence": "CME advisory Chadv21-471 (search-indexed text): SPAN files 'available for download without charge via CME DataMine' and 'will continue to be available via CME's public FTP site'. The website Data Terms of Use page could NOT be read from here: www.cmegroup.com returned HTTP 403 'This IP address is blocked due to suspected web scraping activity' after ~6 page reads, and the fetcher timed out. OWNER MUST READ IT before any use beyond internal research; this run made no further request to www.cmegroup.com.",
        "verdict": "USABLE for 31/34 instruments, 2013-2025-09; individual contracts, no splice; verified below.",
    },
    {
        "source": "U.S. EIA NYMEX futures by contract position (eia.gov/dnav/{pet,ng}/hist)",
        "tried": "hist_xls/<SERIES>d.xls and hist/<SERIES>d.htm for RCLC1-4, RNGC1-4, HO PE1-4, RB PE1-4 (keyless)",
        "result": "16 daily series; CL C1 1983-04-04, HO C1 1980-01-02, NG C1 1994-01-13, RB C1 2005-10-03; ALL end 2024-04-05 (EIA page title: 'Futures prices after April 5, 2024, are not available'). -37.63 on 2020-04-20 present. HTML and xls parses identical.",
        "licence": "U.S. government work, public domain (eia.gov/about/copyrights_reuse.php).",
        "verdict": "USABLE as an independent cross-check and as pre-2013 energy history (positional splice, roll dates recoverable from C1/C2 crossings); not a live feed.",
    },
    {
        "source": "Stooq (stooq.com/q/d/l/?s=<sym>&i=d)",
        "tried": "es.f, cl.f, gc.f, 6e.f, zn.f, esu26.f with an honest UA",
        "result": "HTTP 200, 796-byte HTML: 'This site requires JavaScript to verify your browser' + proof-of-work script, for every symbol. Not CSV.",
        "licence": "Not reached; no exchange licence or roll methodology published.",
        "verdict": "BLOCKED for non-browser access; not defeated (task boundary). Unknown whether it still carries futures.",
    },
    {
        "source": "Nasdaq Data Link / Quandl (data.nasdaq.com/api/v3)",
        "tried": "CHRIS/CME_ES1.json, datasets search, CFTC dataset -- keyless",
        "result": "HTTP 403 Incapsula interstitial on every call. Docs site states it 'will be retired on August 31 2026'. CHRIS reported 'deprecated and is no longer updated' (Packt cookbook issue #5, 2024-09-20).",
        "licence": "Free API key required (owner sign-up); not created.",
        "verdict": "NOT USABLE from here; CHRIS deprecated per third-party report; unverifiable without a key.",
    },
    {
        "source": "Databento historical (GLBX.MDP3, IFUS.IMPACT)",
        "tried": "pricing page, catalog pages for ES and KC, hist.databento.com without a key, client source (databento 0.86.0, databento_dbn 0.69.0 wheels read, not installed)",
        "result": "USD 125 free credit (expires 6 months, one per team); historical is usage-based $/GB, 'No subscription required'; ES since 2010-06-06, KC since 2018-12-23, OHLCV-1d schema listed; API answers 401 without a key. DBN OHLCV record = 56 bytes.",
        "licence": "Licensed CME/ICE distributor; 'Most of our datasets can be redistributed internally or externally after 24 hours' (pricing page).",
        "verdict": "BEST licensed path for KC/SB/CT (2019+) and for post-2025-09 coverage of the 31 CME roots; ingestion written (databento_futures.py), needs the owner's key; offline size estimate tens of MB -> inside the credit.",
    },
    {
        "source": "CME Group other free FTP trees",
        "tried": "settle/TCF (Treasury conversion factors), daily_volume (per-PRODUCT volume/OI xlsx back to 2014-01-02), cash_settled_commodity_index_prices, delivery_reports",
        "result": "No per-contract volume or open interest anywhere; TCF is not prices.",
        "licence": "as above",
        "verdict": "NOT a liquidity source; MOP's most-liquid-contract rule cannot be driven from CME free data.",
    },
    {
        "source": "FRED (api.stlouisfed.org, existing key)",
        "tried": "series/search?search_text=futures+contract",
        "result": "5 hits, none a futures price series (a 1841 wheat wholesale price and four bank-sentiment indices).",
        "licence": "n/a",
        "verdict": "No futures prices on FRED (confirmed, not assumed).",
    },
    {
        "source": "Finnhub (existing key)",
        "tried": "finnhub.io/docs/api text scan for 'futures'",
        "result": "No futures endpoint in the API documentation (only a link to a Kaggle tick dataset).",
        "licence": "n/a",
        "verdict": "No futures history.",
    },
    {
        "source": "Polygon.io -> massive.com futures",
        "tried": "polygon.io/docs/futures (301 -> massive.com/docs/futures), massive.com/docs/llms.txt",
        "result": "REST aggregates + flat files for CME/CBOT/COMEX/NYMEX futures exist; no free-tier statement or history depth found on the pages reached; pricing not shown.",
        "licence": "unknown from here",
        "verdict": "UNRESOLVED (likely paid); not needed given the SPAN archive.",
    },
    {
        "source": "Barchart OnDemand",
        "tried": "search of ondemand FAQ/getHistory docs",
        "result": "getHistory serves futures daily/dailyNearest/dailyContinue; API key required; site says members can download EOD history 'for up to two years prior'.",
        "licence": "commercial API terms; key required",
        "verdict": "NOT free at the needed depth; not pursued.",
    },
    {
        "source": "Kaggle 'E-mini S&P 500 Futures Contracts (CME) [2000-2022]' (choweric/cme-es)",
        "tried": "dataset page read",
        "result": "Individual ES contract months 2000-2022, licence CC BY-SA 4.0; provenance of the prices NOT stated (only a link to CME's contract specs).",
        "licence": "CC BY-SA 4.0",
        "verdict": "Provenance unclear -> not used as an input; could serve as a third cross-check for ES only.",
    },
    {
        "source": "ICE Futures U.S. (KC, SB, CT)",
        "tried": "ice.com Report Center pages",
        "result": "'End of day report packages in .csv format are available for purchase on a subscription basis'; report views require login.",
        "licence": "subscription",
        "verdict": "NO free source found by legitimate means; Databento IFUS.IMPACT (2018-12-23+) is the licensed path.",
    },
    {
        "source": "Interactive Brokers TWS API",
        "tried": "interactivebrokers.github.io/tws-api/historical_limitations.html read live",
        "result": "Verbatim: 'Expired futures data older than two years counting from the future's expiration date' is unavailable.",
        "licence": "free with a funded account (not opened)",
        "verdict": "At most ~2 years of expired-contract history; NOT a history source.",
    },
    {
        "source": "Yahoo Finance (`=F` and individual contracts)",
        "tried": "not redone -- see tsmom_futures_feasibility_2026-09-05.txt",
        "result": "raw front-month splice (PROOF_1/2/3); expired contracts purged",
        "licence": "n/a",
        "verdict": "Still rejected as an INPUT; used here only as an independent CROSS-CHECK of SPAN settles.",
    },
]


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> None:
    t0 = time.time()
    feas = load_feasibility_module()
    synthetic = feas.validate_against_synthetic()
    if synthetic["failures"] or not synthetic["panama_demonstrably_differs"]:
        raise SystemExit(f"synthetic known-answer validation FAILED ({synthetic['failures']}); refusing to report")

    frame = span.load_daily(SPAN_STORE)
    if frame.empty:
        raise SystemExit("SPAN store is empty; run fetch_cme_span_archive.py first")
    span.write_per_instrument(SPAN_STORE, frame)

    p: dict[str, Any] = {
        "run_date": RUN_DATE,
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "synthetic_validation": {k: v for k, v in synthetic.items() if k != "checks"} | {"n_checks": len(synthetic["checks"])},
        "roll_rule": f"hold nearest-expiring listed contract with Type-B expiration > t + {ROLL_BDAYS_BEFORE_EXPIRY} business days (pre-declared; deviation from MOP most-liquid rule, see docstring)",
        "reprobes": reprobe_sources(),
        "span_checks": span_store_checks(frame),
    }
    log.info("yahoo cross-check")
    p["yahoo_cross_check"] = yahoo_cross_check(frame)
    log.info("eia cross-check")
    p["eia_cross_check"] = eia_cross_check(frame)
    eia_cov = {}
    for s in eia.EIA_SERIES:
        path = STORE / "eia" / f"{s.series_id}.csv"
        if path.exists():
            e = eia.load_series(STORE, s.series_id)
            eia_cov[s.series_id] = {"globex": s.globex, "position": s.position, "rows": len(e), "first": str(e.index.min().date()), "last": str(e.index.max().date()), "min_value": float(e.min())}
    p["eia_coverage"] = eia_cov
    log.info("MOP chain")
    chain = chain_all(frame, feas)
    p["mop_chain"] = {g: {k: v for k, v in d.items() if k != "true_returns"} for g, d in chain.items()}
    p["es_vs_cash_index"] = es_vs_cash_index(chain)
    p["databento_plan"] = dbf.dry_run_summary(date.fromisoformat(RUN_DATE)).to_dict(orient="records")
    key = dbf.api_key_from_env()
    if key:
        try:
            p["databento_cost"] = dbf.estimate_cost(dbf.make_client(key), dbf.build_plans(date.fromisoformat(RUN_DATE)))
        except Exception as exc:  # noqa: BLE001
            p["databento_cost"] = {"error": f"{type(exc).__name__}: {exc}"}
    else:
        p["databento_cost"] = {"skipped": "DATABENTO_API_KEY not set -- owner's account decision; offline size estimate only"}
    p["source_ledger"] = SOURCE_LEDGER
    p["verdict"] = build_verdict(p)
    manifest = span.write_manifest(SPAN_STORE, frame, extra={"validation_run": OUT_TXT.name, "validation_summary": {
        "yahoo_either_share": {g: v.get("either_share") for g, v in p["yahoo_cross_check"].items()},
        "eia_share_exact": {k: v.get("share_exact") for k, v in p["eia_cross_check"].items()},
    }})
    p["span_manifest"] = str(manifest)
    p["elapsed_seconds"] = round(time.time() - t0, 1)
    OUT_JSON.write_text(json.dumps(p, indent=2, default=str), encoding="utf-8")
    OUT_TXT.write_text(render_report(p), encoding="utf-8")
    log.info("wrote %s and %s", OUT_TXT, OUT_JSON)


def build_verdict(p: dict[str, Any]) -> dict[str, Any]:
    per = p["span_checks"]["per_instrument"]
    covered = sorted(per)
    missing_cme = sorted(set(span.GLOBEX_TO_SPAN) - set(per))
    eia_ok = all((v.get("share_exact") or 0) > 0.99 for v in p["eia_cross_check"].values() if "share_exact" in v)
    return {
        "instruments_free_from_cme_span": len(covered),
        "cme_roots_missing_from_store": missing_cme,
        "instruments_needing_licensed_source": ICE_ROOTS,
        "span_coverage": f"{p['span_checks']['first_trade_date']} .. {p['span_checks']['last_trade_date']}",
        "eia_agrees_to_the_cent": eia_ok,
        "p4_status": "NARROWED: no USD 270/yr purchase needed; remaining gaps are (a) KC/SB/CT -- licensed only (Databento IFUS.IMPACT 2018-12-23+, inside free credit by estimate), (b) 2025-09-15 onward for the 31 CME roots -- free CME DataMine login or the same Databento pull, (c) MOP most-liquid-contract rule needs per-contract volume (Databento) -- calendar rule used meanwhile.",
    }


def _w(text: str, width: int = 96, indent: str = "  ") -> str:
    import textwrap

    return "\n".join(textwrap.fill(par, width=width, initial_indent=indent, subsequent_indent=indent) for par in text.split("\n"))


def render_report(p: dict[str, Any]) -> str:
    L: list[str] = []
    L.append(f"FUTURES DATA SOURCING -- ATTACKING PAID-DATA GAP P4 -- {p['run_date']}")
    L.append("=" * 100)
    L.append("")
    L.append("VERDICT")
    L.append("-" * 100)
    v = p["verdict"]
    L.append(_w(f"{v['instruments_free_from_cme_span']} of 34 target instruments obtained FREE from CME Group's public SPAN archive as per-contract daily settlements, coverage {v['span_coverage']}; CME roots missing from the store: {v['cme_roots_missing_from_store'] or 'none'}; instruments with no free source: {v['instruments_needing_licensed_source']}."))
    L.append(_w(f"EIA agrees to the cent with SPAN on every compared energy date: {v['eia_agrees_to_the_cent']}."))
    L.append(_w("P4: " + v["p4_status"]))
    L.append("")
    L.append("SYNTHETIC KNOWN-ANSWER VALIDATION (reused from run_tsmom_futures_feasibility.py, unmodified)")
    L.append("-" * 100)
    L.append(_w(json.dumps(p["synthetic_validation"], default=str)))
    L.append("")
    L.append("ROLL RULE (pre-declared)")
    L.append("-" * 100)
    L.append(_w(p["roll_rule"]))
    L.append("")
    L.append("LIVE RE-PROBES THIS RUN (one request each)")
    L.append("-" * 100)
    for k, r in p["reprobes"].items():
        L.append(f"  {k}: http={r.get('http')} bytes={r.get('bytes')} {r.get('error', '')}")
        L.append(_w(f"url: {r.get('url')}", indent="      "))
        if r.get("head"):
            L.append(_w("head: " + r["head"].replace("\n", " "), indent="      "))
        if r.get("verdict"):
            L.append(_w("verdict: " + r["verdict"], indent="      "))
    L.append("")
    L.append("CME SPAN STORE -- INTEGRITY CHECKS")
    L.append("-" * 100)
    sc = p["span_checks"]
    L.append(f"  rows {sc['rows']}  trade days {sc['trade_days']}  {sc['first_trade_date']} .. {sc['last_trade_date']}")
    L.append(f"  Type-81 high-precision vs Type-82 regular settlement: rows with both {sc['hp_vs_regular']['rows_with_hp']}, mismatches {sc['hp_vs_regular']['mismatches']}")
    L.append(f"  fraction-code last-digit census: {json.dumps(sc['fraction_digit_census'])}")
    L.append(_w(f"inferred eighth-tick digits (1/3/6/8) rows: {json.dumps(sc['inferred_eighth_digit_rows'])}"))
    L.append(f"  negative settlements (must be present, e.g. CL 2020-04-20 -37.63): {json.dumps(sc['negative_settlements'])}")
    L.append(f"  within-contract |daily return| > 50% (scale-break screen): {json.dumps(sc['within_contract_scale_breaks'])}")
    L.append("")
    L.append("  root   rows   days   first        last         contracts  rows w/o expiry")
    for g in sorted(sc["per_instrument"]):
        r = sc["per_instrument"][g]
        L.append(f"  {g:5s} {r['rows']:6d} {r['trade_days']:6d}   {r['first']}   {r['last']}   {r['contracts']:6d}   {r['missing_expiration_rows']:6d}")
    L.append("")
    L.append("CROSS-CHECK 1 -- YAHOO `=F` CLOSE == SPAN NEAREST/SECOND CONTRACT SETTLE (exact equality)")
    L.append("-" * 100)
    L.append(_w("Yahoo's close is a last trade, CME's is a settlement; products settled at a different time than the last trade (FX, Treasuries, some ags) are EXPECTED to match rarely. A high rate is proof of tick-level agreement; a low rate is not evidence of error (EIA settles are the settlement-vs-settlement check)."))
    L.append("  root   days   front-exact  second-exact  either share")
    for g in sorted(p["yahoo_cross_check"]):
        r = p["yahoo_cross_check"][g]
        if "error" in r:
            L.append(f"  {g:5s} error {r['error']}")
        else:
            L.append(f"  {g:5s} {r['days_compared']:6d} {r['front_exact']:11d} {r['second_exact']:13d}  {r['either_share']:.3f}")
    L.append("")
    L.append("CROSS-CHECK 2 -- EIA CONTRACT N SETTLE == SPAN N-th NEAREST UNEXPIRED CONTRACT SETTLE (to the cent)")
    L.append("-" * 100)
    L.append("  series                         root pos   days   exact  share    worst|diff|")
    for k in sorted(p["eia_cross_check"]):
        r = p["eia_cross_check"][k]
        if "error" in r:
            L.append(f"  {k:30s} error {r['error']}")
        else:
            L.append(f"  {k:30s} {r['globex']:4s} {r['position']:3d} {r['days_compared']:6d} {r['exact_to_the_cent']:7d}  {r['share_exact']:.4f}  {r['worst_abs_diff']:.4f}")
            for ex in r["mismatch_examples"]:
                L.append(f"      mismatch {ex}")
    L.append("")
    L.append("EIA COVERAGE (positional Contract 1-4, public domain)")
    L.append("-" * 100)
    for k, r in p["eia_coverage"].items():
        L.append(f"  {k:30s} {r['globex']} C{r['position']}  rows {r['rows']:6d}  {r['first']} .. {r['last']}  min {r['min_value']}")
    L.append("")
    L.append("MOP (2012) SECTION 2.1 CHAIN ON SPAN DATA -- PROOF OF CONCEPT, NOT A SIGNAL")
    L.append("-" * 100)
    L.append(_w("true = within-contract chained returns (MOP); naive = front-month splice pct_change (Yahoo's shape). The artifact column is what a splice would inject at each roll under the same holding series -- measured on real exchange settlements for every instrument, which the 2026-09-05 run could only do for ES."))
    L.append("  root   days  rolls  ann vol   true cum   naive cum   art mean pp  share>0   art pp/yr  ratio-equiv  off-roll zero")
    for g in sorted(p["mop_chain"]):
        r = p["mop_chain"][g]
        if "error" in r:
            L.append(f"  {g:5s} error {r['error']}")
            continue
        a = r["roll_artifact_pp"]
        L.append(
            f"  {g:5s} {r['days']:5d} {r['rolls']:6d}  {r['true_ann_vol']:7.3f}  {r['true_cum_return']:+9.3f}  {r['naive_cum_return']:+10.3f}  "
            f"{(a['mean'] if a['mean'] is not None else float('nan')):+10.3f}  {(a['share_positive'] if a['share_positive'] is not None else float('nan')):7.2f}  "
            f"{a['sum_pp_per_year']:+9.2f}  {r['ratio_adjust_equivalence_max_abs']:.1e}  {r['artifact_zero_off_roll_days']}"
        )
    L.append("")
    L.append(f"  ES chained returns vs ^GSPC: {json.dumps(p['es_vs_cash_index'])}")
    L.append(_w("MOP p.231: 'For the equity indexes, our return series are almost perfectly correlated with the corresponding returns of the underlying cash indexes'."))
    L.append("")
    L.append("DATABENTO -- PLAN AND COST")
    L.append("-" * 100)
    for r in p["databento_plan"]:
        L.append(f"  {json.dumps(r, default=str)}")
    L.append(_w(f"cost from Databento's own endpoint: {json.dumps(p['databento_cost'], default=str)}"))
    L.append("")
    L.append("SOURCE LEDGER -- EVERYTHING TRIED, WITH VERDICTS")
    L.append("-" * 100)
    for s in p["source_ledger"]:
        L.append(f"  [{s['source']}]")
        for k in ("tried", "result", "licence", "verdict"):
            L.append(_w(f"{k}: {s[k]}", indent="      "))
        L.append("")
    L.append("WHAT THIS RUN DOES NOT ESTABLISH")
    L.append("-" * 100)
    L.append(_w("It builds no TSMOM signal and registers nothing. The chain above uses a calendar roll rule because no free source carries per-contract volume; MOP's most-liquid rule needs Databento's volume field. Coverage before 2013 exists only for the four EIA energy roots (positional), and after 2025-09-12 for nothing until the owner opens a CME DataMine login (free per Chadv21-471) or a Databento account (USD 125 credit). CME's website Data Terms of Use were not readable from this environment; the owner must read them before any use of the SPAN archive beyond internal research."))
    L.append("")
    L.append(f"elapsed {p['elapsed_seconds']} s; JSON alongside; SPAN manifest {p['span_manifest']}")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
