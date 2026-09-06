"""FEASIBILITY SCOPING ONLY -- IPO lockup-expiration price-pressure candidate,
Field & Hanka (2001, Journal of Finance 56(2):471-500), "The Expiration of
IPO Share Lockups". Candidate #8 in this session's flow/positioning
literature search, after TSMOM (paused, paid-data gap), SEC N-PORT flow
(built, DEFINITE_NEGATIVE), options-dealer-gamma-hedging (paused, paid-data
gap), tax-loss-selling / rebalancing-pressure / dividend-payment-pressure /
margin-credit (all built, DEFINITE_NEGATIVE).

Builds NO lockup-expiration signal, registers nothing, purchases nothing.
Mirrors run_tsmom_futures_feasibility.py and run_options_gamma_feasibility.py
in rigor: live-probe everything, refuse to build on an unverified data claim,
and answer with a verdict from the same taxonomy (FEASIBLE_FREE /
FEASIBLE_FREE_WITH_NAMED_LIMITS / BLOCKED_ON_PAID_DATA).

============================================================================
THE QUESTIONS, AND THE SHORT ANSWERS THIS RUN MEASURED
============================================================================

Q1. CAN THIS PROJECT GET A FREE, PER-COMPANY U.S. IPO DATE + TICKER LIST?
    YES -- Jay Ritter's (Univ. of Florida, Warrington College of Business)
    "IPO-age.xlsx", live-downloaded from
    https://site.warrington.ufl.edu/ritter/files/IPO-age.xlsx 2026-09-06.
    Sheet "1975-2025", 16,030 individual IPO rows, columns: offer date, IPO
    name, Ticker, CUSIP, ADR flag, VC flag (0/1), Dual-class flag, Post-issue
    shares, Internet flag, CRSP PermNo, Founding year, Rollup flag. Ticker
    populated on 97.5% of rows (15,625/16,030). VC-backing flagged per company
    on 3,779 rows -- directly supports testing the paper's own "3x larger in
    VC-backed firms" claim cross-sectionally. Spot-checked against 5 famous,
    independently-known IPOs (Facebook 2012-05-17 FB VC=1, Uber 2019-05-10
    UBER VC=1, Snowflake 2020-09-16 SNOW VC=1, DoorDash 2020-12-09 DASH VC=1,
    Airbnb 2020-12-10 ABNB VC=1) and all five matched exactly on date, ticker
    and VC flag. IPOALL.xlsx (also downloaded) is confirmed to be ONLY the
    aggregate monthly-count file the task brief expected it might be -- no
    per-company rows -- so IPO-age.xlsx, not IPOALL.xlsx, is the file this
    family would actually be built from.

Q2. IS "IPO DATE + 180 CALENDAR DAYS" A DEFENSIBLE LOCKUP-EXPIRATION PROXY?
    YES, provisionally, on the paper's own evidence, with the SEC full-text
    path confirmed real but not pursued as primary (see SECTION B). Field &
    Hanka's own Table I reports 80% of their 1996 cohort and 91% of their
    1997 cohort at exactly 180 days (rising from 43% in 1988); their Table
    III splits the sample into <180/180/>180-day lockups and the -1/+1 CAR is
    directionally similar in all three buckets (-1.3%, not separately broken
    out for exactly-180, and -0.8% for >180), so a 180-day approximation does
    not manufacture the effect out of nothing. This project has NOT verified
    the 180-day share is still ~90%+ in years after Field & Hanka's 1997
    sample end -- that is an open question a build task would need to check
    (SEC full-text search, below, is the free way to do it) rather than an
    assumption carried over uninspected from a 25-years-stale citation.

Q3. UNIVERSE/COVERAGE RISK -- THE HEADLINE FINDING OF THIS RUN.
    TWO DISTINCT, BOTH REAL, RISKS -- not one:
    (a) Ordinary survivorship bias (delisted names return zero price rows) --
        CONFIRMED, see SECTION C, and it is the SAME already-logged P2 gap
        (PENDING_PAID_DATA_DECISIONS.md) other families hit, not a new one.
    (b) TICKER RECYLING / SILENT MISATTRIBUTION -- a risk NOT previously
        logged for any other family in this project, found while building
        this run's sample, before any price data was even fetched: Ritter's
        own free list shows the same ticker reused by unrelated companies
        decades apart at a measured, material rate (see SECTION C.1). A
        naive ticker-string join between an old IPO row and a live data
        provider risks silently returning a LATER, unrelated company's price
        series for an OLD lockup-expiration date -- which is corruption, not
        mere missingness, and would not raise any error. This is the more
        dangerous of the two risks precisely because it is silent.

Q4. ORDER-OF-MAGNITUDE SAMPLE SIZE.
    See SECTION D. Non-SPAC IPO counts run roughly 150-215/year across
    2012-2019 (SPAC contamination measured directly per year-bucket, not
    assumed), comparable in shape to Field & Hanka's own ~195/year average
    over 1988-1997.
"""

from __future__ import annotations

import json
import logging
import sys
import urllib.request
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# WORKTREE BINDING GUARD -- same pattern as run_tsmom_futures_feasibility.py
# and run_options_gamma_feasibility.py: this file must run against the code
# checked out in ITS OWN worktree, never silently against another checkout
# reached via a stale sys.path.
# ---------------------------------------------------------------------------
_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

import app

if Path(app.__file__).resolve().parent.parent != _BACKEND:
    raise SystemExit(
        f"REFUSING TO RUN: `app` resolved to {app.__file__}, which is not inside this worktree "
        f"({_BACKEND}). The measurement would have used another checkout's code."
    )

import openpyxl

from app.services.market_data.price_store import PriceStore
from app.services.market_data.yfinance_provider import YFinanceProvider

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s", stream=sys.stderr
)
logger = logging.getLogger("ipo_lockup_feasibility")

OUT_DIR = Path(__file__).resolve().parent / "ipo_lockup_samples"
OUT_DIR.mkdir(exist_ok=True)

RITTER_IPO_AGE_URL = "https://site.warrington.ufl.edu/ritter/files/IPO-age.xlsx"
RITTER_IPOALL_URL = "https://site.warrington.ufl.edu/ritter/files/IPOALL.xlsx"

UA_HEADERS = {"User-Agent": "Mozilla/5.0 (research-scoping; aladdin2 project)"}


def _download(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def _is_spac_like(name: str | None, ticker: str | None) -> bool:
    name_u = str(name or "").upper()
    ticker_s = str(ticker or "")
    return ("ACQUISITION" in name_u) or ticker_s.endswith("U") or (" ACQ" in name_u)


def _parse_offer_date(raw: Any) -> date | None:
    """Ritter's own file stores `offer date` inconsistently: an int
    YYYYMMDD for older rows, a numeric-string YYYYMMDD for the most recent
    (2025) rows added after this run started checking. Handle both rather
    than assume one, since silently mis-parsing a date here would corrupt
    every downstream lockup-date computation."""
    if raw is None:
        return None
    s = str(raw).strip()
    if len(s) != 8 or not s.isdigit():
        return None
    try:
        return date(int(s[0:4]), int(s[4:6]), int(s[6:8]))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# SECTION A -- Ritter free IPO list: download, parse, and measure it for real
# ---------------------------------------------------------------------------


def section_a_ritter_data() -> dict[str, Any]:
    logger.info("SECTION A: downloading Ritter IPO-age.xlsx and IPOALL.xlsx live")
    ipo_age_bytes = _download(RITTER_IPO_AGE_URL)
    ipoall_bytes = _download(RITTER_IPOALL_URL)

    wb_age = openpyxl.load_workbook(BytesIO(ipo_age_bytes), read_only=True, data_only=True)
    age_sheet_names = wb_age.sheetnames
    ws = wb_age[age_sheet_names[0]]
    rows = list(ws.iter_rows(values_only=True))
    header = [str(h) for h in rows[0] if h is not None]
    data_rows = rows[1:]

    wb_all = openpyxl.load_workbook(BytesIO(ipoall_bytes), read_only=True, data_only=True)
    ipoall_sheet_names = wb_all.sheetnames
    ws_all = wb_all[ipoall_sheet_names[0]]
    ipoall_first_rows = [list(r) for r in list(ws_all.iter_rows(values_only=True))[:8]]
    ipoall_max_cols_with_data = 0
    for r in list(ws_all.iter_rows(values_only=True))[:200]:
        nonnull = sum(1 for v in r if v is not None)
        ipoall_max_cols_with_data = max(ipoall_max_cols_with_data, nonnull)

    parsed = []
    for r in data_rows:
        d = _parse_offer_date(r[0])
        parsed.append(
            {
                "offer_date": d.isoformat() if d else None,
                "name": r[1],
                "ticker": r[2],
                "cusip": r[3],
                "adr": r[4],
                "vc": r[5],
                "dual": r[6],
            }
        )

    n_total = len(parsed)
    n_with_date = sum(1 for p in parsed if p["offer_date"])
    n_with_ticker = sum(1 for p in parsed if p["ticker"] not in (None, ".", ""))
    n_vc = sum(1 for p in parsed if p["vc"] == 1)
    dated = [p for p in parsed if p["offer_date"]]
    min_date = min(p["offer_date"] for p in dated)
    max_date = max(p["offer_date"] for p in dated)

    # ---- SPAC contamination by 4-year window -----------------------------
    windows = [
        ("2004-2007", 2004, 2007),
        ("2008-2011", 2008, 2011),
        ("2012-2015", 2012, 2015),
        ("2016-2019", 2016, 2019),
        ("2020-2021", 2020, 2021),
        ("2022-2025", 2022, 2025),
    ]
    spac_by_window = {}
    for label, y0, y1 in windows:
        total = spac = 0
        for p in dated:
            y = int(p["offer_date"][:4])
            if y0 <= y <= y1:
                total += 1
                if _is_spac_like(p["name"], p["ticker"]):
                    spac += 1
        spac_by_window[label] = {
            "total": total,
            "spac_like": spac,
            "non_spac": total - spac,
            "spac_pct": round(spac / total * 100, 1) if total else None,
            "non_spac_per_year": round((total - spac) / (y1 - y0 + 1), 1) if total else None,
        }

    # ---- ticker-recycling measurement --------------------------------
    from collections import defaultdict

    ticker_to_names: dict[str, set[str]] = defaultdict(set)
    for p in dated:
        t = p["ticker"]
        if t not in (None, ".", ""):
            ticker_to_names[str(t)].add(str(p["name"]))
    recycled = {t: sorted(names) for t, names in ticker_to_names.items() if len(names) > 1}
    n_distinct_tickers = len(ticker_to_names)
    n_recycled_tickers = len(recycled)

    # spot-check against independently-known real IPOs
    spot_check_targets = {
        "FB": ("2012-05-17", 1),
        "UBER": ("2019-05-10", 1),
        "SNOW": ("2020-09-16", 1),
        "DASH": ("2020-12-09", 1),
        "ABNB": ("2020-12-10", 1),
    }
    spot_check_results = {}
    for p in dated:
        t = p["ticker"]
        if t in spot_check_targets:
            exp_date, exp_vc = spot_check_targets[t]
            if p["offer_date"] == exp_date:
                spot_check_results[t] = {
                    "expected_date": exp_date,
                    "found_date": p["offer_date"],
                    "name": p["name"],
                    "vc_flag": p["vc"],
                    "match": p["vc"] == exp_vc,
                }

    result = {
        "ritter_ipo_age_url": RITTER_IPO_AGE_URL,
        "ritter_ipoall_url": RITTER_IPOALL_URL,
        "ipo_age_sheet_names": age_sheet_names,
        "ipo_age_header": header,
        "ipo_age_n_total_rows": n_total,
        "ipo_age_n_with_date": n_with_date,
        "ipo_age_n_with_ticker": n_with_ticker,
        "ipo_age_pct_with_ticker": round(n_with_ticker / n_total * 100, 1),
        "ipo_age_n_vc_flagged": n_vc,
        "ipo_age_date_range": [min_date, max_date],
        "ipoall_sheet_names": ipoall_sheet_names,
        "ipoall_max_nonnull_cols_first_200_rows": ipoall_max_cols_with_data,
        "ipoall_is_aggregate_only": ipoall_max_cols_with_data <= 8,
        "spac_contamination_by_window": spac_by_window,
        "ticker_recycling": {
            "n_distinct_tickers": n_distinct_tickers,
            "n_tickers_used_by_more_than_one_company": n_recycled_tickers,
            "pct_tickers_recycled": round(n_recycled_tickers / n_distinct_tickers * 100, 2),
            "example_recycled_tickers": {
                t: recycled[t] for t in ["SNOW", "GPRO", "FB", "PTON"] if t in recycled
            },
        },
        "spot_check_against_known_ipos": spot_check_results,
        "spot_check_all_matched": all(v["match"] for v in spot_check_results.values())
        and len(spot_check_results) == len(spot_check_targets),
    }
    (OUT_DIR / "section_a_ritter_data.json").write_text(json.dumps(result, indent=2, default=str))
    return result, parsed


# ---------------------------------------------------------------------------
# SECTION B -- SEC EDGAR 424B4 cross-check (supplementary only, per brief)
# ---------------------------------------------------------------------------


def section_b_edgar_check() -> dict[str, Any]:
    logger.info("SECTION B: probing SEC EDGAR full-text search for lock-up language in 424B4s")
    import httpx

    result: dict[str, Any] = {}
    client = httpx.Client(headers={"User-Agent": "aladdin2-research contact@example.com"}, timeout=20.0)

    # (1) EDGAR full text search: how many 424B4 filings mention a 180-day lockup?
    try:
        r = client.get(
            "https://efts.sec.gov/LATEST/search-index",
            params={"q": '"lock-up period of 180 days"', "forms": "424B4"},
        )
        result["fulltext_search_180day_status"] = r.status_code
        if r.status_code == 200:
            payload = r.json()
            result["fulltext_search_180day_hits"] = payload.get("hits", {}).get("total", {}).get("value")
            result["fulltext_search_180day_sample"] = [
                {
                    "display_names": h.get("_source", {}).get("display_names"),
                    "file_date": h.get("_source", {}).get("file_date"),
                    "form": h.get("_source", {}).get("root_form"),
                }
                for h in payload.get("hits", {}).get("hits", [])[:5]
            ]
    except Exception as exc:  # noqa: BLE001 -- report the failure, don't hide it
        result["fulltext_search_180day_error"] = repr(exc)

    # (2) EDGAR full text search coverage window -- the API itself documents
    # its earliest coverage; confirm it live rather than assume 2001+.
    try:
        r2 = client.get(
            "https://efts.sec.gov/LATEST/search-index",
            params={"q": '"lock-up"', "forms": "424B4", "dateRange": "custom",
                    "startdt": "2001-01-01", "enddt": "2001-12-31"},
        )
        result["fulltext_search_2001_status"] = r2.status_code
        if r2.status_code == 200:
            payload2 = r2.json()
            result["fulltext_search_2001_hits"] = payload2.get("hits", {}).get("total", {}).get("value")
    except Exception as exc:  # noqa: BLE001
        result["fulltext_search_2001_error"] = repr(exc)

    # (3) SEC company_tickers.json -- ticker <-> CIK master mapping, the free
    # resource a real build would use to resolve a company name/ticker to a
    # CIK for pulling its actual 424B4 rather than trusting Ritter's ticker
    # string alone.
    try:
        r3 = client.get("https://www.sec.gov/files/company_tickers.json")
        result["company_tickers_status"] = r3.status_code
        if r3.status_code == 200:
            mapping = r3.json()
            result["company_tickers_count"] = len(mapping)
    except Exception as exc:  # noqa: BLE001
        result["company_tickers_error"] = repr(exc)

    client.close()
    (OUT_DIR / "section_b_edgar_check.json").write_text(json.dumps(result, indent=2, default=str))
    return result


# ---------------------------------------------------------------------------
# SECTION C -- price-history availability stress test (the core question)
# ---------------------------------------------------------------------------

ANCHOR_DELISTED = [
    # (ticker, ipo_date, company, delisting fact, source-verified date)
    ("LNKD", "2011-05-19", "LinkedIn Corp", "acquired by Microsoft, delisted 2016-12-08"),
    ("FIT", "2015-06-18", "Fitbit Inc", "acquired by Google, delisted 2021-01-14"),
    ("ZNGA", "2011-12-15", "Zynga Inc", "acquired by Take-Two, delisted 2022-05-23"),
    ("P", "2011-06-14", "Pandora Media Inc", "acquired by SiriusXM, completed 2019-02-01"),
    ("TCS", "2013-11-01", "Container Store Group", "NYSE-delisted 2024-12-09, Ch.11 2024-12-22"),
    ("CLDR", "2017-04-28", "Cloudera Inc", "taken private by KKR/CD&R, delisted 2021-10-08"),
]

ANCHOR_STILL_TRADING = [
    ("FB", "2012-05-17", "Facebook Inc (now META)"),
    ("UBER", "2019-05-10", "Uber Technologies Inc"),
    ("SNOW", "2020-09-16", "Snowflake Inc"),
    ("ABNB", "2020-12-10", "Airbnb Inc"),
    ("ETSY", "2015-04-16", "Etsy Inc"),
    ("BYND", "2019-05-02", "Beyond Meat Inc"),
    ("PTON", "2019-09-26", "Peloton Interactive Inc"),
]

# Ticker-recycling stress test: OLD companies whose ticker was later reused
# by an unrelated, currently-trading company. If yfinance silently returns
# the LATER company's price data for the OLD lockup window, that is a
# misattribution failure, not mere missingness.
ANCHOR_RECYCLED_TICKER = [
    ("SNOW", "1994-03-02", "SnowRunner (pre-Snowflake use of SNOW)"),
    ("SNOW", "2000-03-20", "Snowball.com Inc (pre-Snowflake use of SNOW)"),
    ("SNOW", "2014-01-31", "Intrawest Resorts Holdings (pre-Snowflake use of SNOW)"),
    ("GPRO", "1987-09-30", "Gen-Probe (pre-GoPro use of GPRO)"),
    ("FB", "1994-11-02", "Falcon Building Products (pre-Facebook use of FB)"),
    ("PTON", "1991-06-04", "Proteon (pre-Peloton use of PTON)"),
]


def _systematic_sample(parsed: list[dict[str, Any]], y0: int, y1: int, step: int, seed_offset: int = 0) -> list[tuple[str, str, str]]:
    """Every `step`-th non-SPAC row with a real ticker in [y0, y1], in offer-date
    order -- a systematic sample, not a hand-picked one, specifically to avoid
    cherry-picking only names whose fate is already known."""
    candidates = [
        p
        for p in parsed
        if p["offer_date"]
        and y0 <= int(p["offer_date"][:4]) <= y1
        and p["ticker"] not in (None, ".", "")
        and not _is_spac_like(p["name"], p["ticker"])
    ]
    candidates.sort(key=lambda p: p["offer_date"])
    out = []
    for i in range(seed_offset, len(candidates), step):
        p = candidates[i]
        out.append((str(p["ticker"]), p["offer_date"], str(p["name"])))
    return out


def _fetch_window(provider: YFinanceProvider, ticker: str, center: date, pad_days: int) -> dict[str, Any]:
    start = center - timedelta(days=pad_days)
    end = center + timedelta(days=pad_days)
    try:
        frame, missing = provider.get_price_history([ticker], start, end)
    except Exception as exc:  # noqa: BLE001 -- report, don't hide
        return {"error": repr(exc), "resolved": False, "n_rows": 0}
    if ticker in missing or frame.empty or ticker not in frame.columns:
        return {"resolved": False, "n_rows": 0}
    col = frame[ticker].dropna()
    if col.empty:
        return {"resolved": False, "n_rows": 0}
    return {
        "resolved": True,
        "n_rows": int(len(col)),
        "window_start_actual": col.index.min().date().isoformat(),
        "window_end_actual": col.index.max().date().isoformat(),
        "first_price": float(col.iloc[0]),
        "last_price": float(col.iloc[-1]),
    }


def section_c_price_availability(parsed: list[dict[str, Any]]) -> dict[str, Any]:
    logger.info("SECTION C: building sample and testing real price-fetch via YFinanceProvider")
    # store_dir=None -- pass-through mode, exactly what unit tests use, so
    # this run neither writes into nor depends on the project's real price
    # store (see price_store.py's own docstring on this constructor arg).
    provider = YFinanceProvider(price_store=PriceStore(store_dir=None))

    today = date.today()
    sample_rows: list[dict[str, Any]] = []

    def add_row(ticker: str, ipo_date_s: str, name: str, bucket: str, a_priori_label: str):
        ipo_dt = datetime.strptime(ipo_date_s, "%Y-%m-%d").date()
        lockup_dt = ipo_dt + timedelta(days=180)
        sample_rows.append(
            {
                "ticker": ticker,
                "ipo_date": ipo_date_s,
                "lockup_date_approx": lockup_dt.isoformat(),
                "name": name,
                "bucket": bucket,
                "a_priori_label": a_priori_label,
            }
        )

    for t, d, n, fact in ANCHOR_DELISTED:
        add_row(t, d, n, "anchor_delisted", fact)
    for t, d, n in ANCHOR_STILL_TRADING:
        add_row(t, d, n, "anchor_still_trading", "well-known, expected still trading")
    for t, d, n in ANCHOR_RECYCLED_TICKER:
        add_row(t, d, n, "anchor_recycled_ticker", "ticker later reused by an unrelated company")

    systematic = _systematic_sample(parsed, 2012, 2019, step=40, seed_offset=7)
    for t, d, n in systematic:
        add_row(t, d, n, "systematic_sample_2012_2019", "unlabeled a priori -- ordinary IPO")

    logger.info("Sample built: %d rows (%d anchors, %d systematic)", len(sample_rows), 19, len(systematic))

    for row in sample_rows:
        lockup_dt = datetime.strptime(row["lockup_date_approx"], "%Y-%m-%d").date()
        lockup_probe = _fetch_window(provider, row["ticker"], lockup_dt, pad_days=20)
        row["lockup_window_probe"] = lockup_probe
        # Recent-window probe: is this ticker resolvable to ANY data in the
        # last 30 days, as an empirical (not assumed) "still trading today"
        # signal, cross-checked against the a-priori anchor labels.
        recent_probe = _fetch_window(provider, row["ticker"], today - timedelta(days=15), pad_days=15)
        row["recent_window_probe"] = recent_probe
        logger.info(
            "%-6s ipo=%s lockup~%s : lockup_resolved=%s rows=%s | recent_resolved=%s",
            row["ticker"], row["ipo_date"], row["lockup_date_approx"],
            lockup_probe.get("resolved"), lockup_probe.get("n_rows"),
            recent_probe.get("resolved"),
        )

    # ---- aggregate stats --------------------------------------------------
    def agg(rows):
        n = len(rows)
        resolved = sum(1 for r in rows if r["lockup_window_probe"].get("resolved"))
        return {"n": n, "resolved_lockup_window": resolved, "hit_rate_pct": round(resolved / n * 100, 1) if n else None}

    still_trading_rows = [r for r in sample_rows if r["recent_window_probe"].get("resolved")]
    not_still_trading_rows = [r for r in sample_rows if not r["recent_window_probe"].get("resolved")]

    summary = {
        "n_total_sample": len(sample_rows),
        "overall": agg(sample_rows),
        "by_bucket": {
            b: agg([r for r in sample_rows if r["bucket"] == b])
            for b in ["anchor_delisted", "anchor_still_trading", "anchor_recycled_ticker", "systematic_sample_2012_2019"]
        },
        "by_empirical_still_trading_today": {
            "still_trading_today": agg(still_trading_rows),
            "not_still_trading_today": agg(not_still_trading_rows),
        },
        "recycled_ticker_misattribution_check": [
            {
                "ticker": r["ticker"],
                "name": r["name"],
                "ipo_date": r["ipo_date"],
                "lockup_resolved": r["lockup_window_probe"].get("resolved"),
                "lockup_price_if_resolved": r["lockup_window_probe"].get("first_price"),
                "note": (
                    "if resolved=True here, MUST manually verify the price level is "
                    "plausible for this OLD company/era, not a later company's price "
                    "silently returned under the same ticker string"
                ),
            }
            for r in sample_rows
            if r["bucket"] == "anchor_recycled_ticker"
        ],
    }

    (OUT_DIR / "section_c_price_availability_detail.json").write_text(
        json.dumps(sample_rows, indent=2, default=str)
    )
    (OUT_DIR / "section_c_price_availability_summary.json").write_text(
        json.dumps(summary, indent=2, default=str)
    )
    return summary, sample_rows


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------


def main() -> None:
    section_a_result, parsed = section_a_ritter_data()
    section_b_result = section_b_edgar_check()
    section_c_summary, section_c_rows = section_c_price_availability(parsed)

    full = {
        "run_date": date.today().isoformat(),
        "section_a": section_a_result,
        "section_b": section_b_result,
        "section_c_summary": section_c_summary,
    }
    out_path = Path(__file__).resolve().parent / "ipo_lockup_feasibility_2026-09-06.json"
    out_path.write_text(json.dumps(full, indent=2, default=str))
    logger.info("Wrote %s", out_path)

    print(json.dumps(full, indent=2, default=str))


if __name__ == "__main__":
    main()
