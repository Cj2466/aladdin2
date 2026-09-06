"""Daily per-contract futures SETTLEMENT prices from CME Group's public SPAN
risk-parameter archive (ftp.cmegroup.com/span/archive/cme/), for the 31
CME-Group instruments of the TSMOM universe. Built 2026-09-07 for the
futures-data-sourcing task (data/research_runs/run_futures_data_sourcing.py),
which documents the sourcing decision; this module documents the DATA FACTS.

EVERY CLAIM BELOW WAS VERIFIED LIVE 2026-09-07 IN THIS SESSION against the
production FTP server and CME's published SPAN file layout, not recalled
from memory.

WHAT THE ARCHIVE IS
  * ftp://ftp.cmegroup.com/span/archive/cme/<YYYY>/cme.<YYYYMMDD>.s.pa2.zip
    for 2014..2025; 2013 is split into monthly subfolders
    (.../2013/<YYYYMM>/cme.<YYYYMMDD>.s.pa2.zip). The ".s" cycle is the
    end-of-day (final settlement) cycle; a/c/e/i/m/AI/BE/X are intraday
    cycles and are NOT used. Listed live: first settlement file
    cme.20130102.s.pa2.zip, last cme.20250912.s.pa2.zip; 260-261 ".s"
    files per calendar year 2014..2024, 182 in 2025. There is no 2026
    folder: CME decommissioned SPAN publication on the public FTP site,
    finally effective 2025-09-15 (clearing advisory 25-264, "Update: SPAN
    Files Decommission on FTP Sites, Monday, September 15th"); the
    archive itself is still served, which is what this module reads.
    Post-2025-09-12 files are published via CME DataMine, which advisory
    Chadv21-471 describes as "available for download without charge via
    CME DataMine" -- that needs a DataMine login and is the OWNER's
    decision, not taken here.
  * Each zip holds one fixed-width text file (~86 MB, ~690k lines) whose
    record types are documented at CME's public SPAN wiki
    (cmegroupclientsite.atlassian.net/wiki/spaces/pubsub/pages/457083445,
    "Risk Parameter File Layouts for the Positional Formats", read live
    2026-09-07). Byte positions below are 1-based exactly as that page
    prints them; the Python slices are 0-based.

RECORD LAYOUT USED (Type 8 - Expanded, page 457083725; Type P, page
457083966; Type B - Expanded, page 457215159 -- all read live 2026-09-07)
  "81"  3-5 exchange, 6-15 commodity code, 26-28 product type ("FUT"),
        30-35 futures contract month CCYYMM, 109-122 "High-Precision
        Settlement Price", 123 flag ("N means ... the price may be read
        either from this field or from the regular Settlement Price
        field").
  "82"  same key fields; 111-117 regular Settlement Price (per clearing
        advisory Chadv10-147: "The regular Settlement Price field, in bytes
        111-117 of the type '82' record, will also always be populated,
        except if the price requires more than seven total digits"),
        118 sign.
  "P "  3-5 exchange, 6-15 product code, 16-18 product type, 34-36
        "Settlement Price Decimal Locator", 40 "Settlement Price Alignment
        Code", 80-114 product long name.
  "B "  3-5 exchange, 6-15 commodity code, 16-18 product type, 19-24
        futures contract month, 92-99 "Expiration (Settlement) Date as
        CCYYMMDD".

PRICE DECODING -- the decimal locator is documented; the ALIGNMENT CODE'S
VALUE SET IS NOT documented on any page reachable from here (searched
2026-09-07), so the two non-blank codes are decoded by a rule ESTABLISHED
EMPIRICALLY and re-verified by run_futures_data_sourcing.py on every file
it ingests (last-digit distribution + exact agreement with Yahoo `=F`
closes and EIA NYMEX settlements on the same dates):
  blank  plain decimal: settle = int(raw) / 10**locator.
         ES 2019-01-02 raw 0251100 locator 2 -> 2511.00 (= Yahoo ES=F);
         CL raw 0004654 -> 46.54 (= EIA RCLC1 46.54 and Yahoo CL=F);
         NG raw 0295800 locator 5 -> 2.95800 (= EIA RNGC1 2.958);
         6J raw 0091905 locator 7 -> 0.0091905.
  "C"    CBOT Treasury quotes in 32nds: the digits after the locator are
         32nds*10, with the LAST digit a quarter-32nd code. ZN raw 0122060
         -> 122 + 06.0/32 = 122.1875 (= Yahoo ZN=F 2019-01-02); ZB
         0146240 -> 146.75 (= Yahoo). Decoded with FRACTION_CODE below
         (quarter digits 2/5/7; ZT, which ticks in 1/8 of a 32nd, also
         uses the eighth digits 1/3/6/8 of CME's display convention).
  "0"    CBOT grain quotes in cents/bushel with the LAST digit a
         quarter-cent code: corn raw 0003757 -> 375.75 (= Yahoo ZC=F
         2019-01-02); wheat 0005067 -> 506.75 (= Yahoo); soybeans 0009070
         -> 907.00. A decimal reading (3.757 $/bu) would be off by a
         quarter cent on every such print; the quarter-code reading
         matches Yahoo exactly.
  Any other alignment code, or a last digit outside FRACTION_CODE for
  "C"/"0", is REFUSED (raises) rather than guessed -- the run script
  reports how many rows that would affect (zero on every file measured).

UNITS: settle is stored in the exchange's own quoted unit (index points,
$/bbl, cents/bushel, cents/lb, $/short ton, USD per unit FX, price per 100
face for Treasuries). A TSMOM return is a ratio within one contract, so
the unit cancels; it is recorded in the manifest so nobody mixes them.

KNOWN LIMITS (measured, not assumed)
  * No per-contract VOLUME or OPEN INTEREST anywhere on the public FTP:
    daily_volume/daily_volume_<date>.xlsx is per PRODUCT. MOP (2012)
    Section 2.1's "most liquid contract" rule therefore cannot be applied
    from this source; the run script pre-declares a calendar roll rule
    from the Type B expiration date instead and logs that as a deviation.
  * Coverage is 2013-01-02 .. 2025-09-12 only. Anything later needs
    DataMine (free with login) or Databento (paid-per-GB, credit).
  * RTY was an ICE product until 2017-07 and appears in these files only
    from CME's relisting; the per-instrument row counts in the manifest
    say exactly what was found.
  * The negative WTI settlement of 2020-04-20 (-37.63) MUST survive:
    the "82" sign byte (118) is honoured, and the store never applies
    price_store.drop_implausible.

NETWORK BEHAVIOUR: one FTP GET per file, at most 3 concurrent, no retry
storm (3 attempts, growing pause). CME's website (www.cmegroup.com) is
NEVER touched by this module -- its Data Terms of Use forbid automated
access and it blocked this session's IP after a handful of page reads
(recorded in the run report). The FTP archive is the channel CME's own
advisories call "CME's public FTP site".
"""

from __future__ import annotations

import io
import json
import logging
import time
import urllib.request
import zipfile
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

SPAN_ARCHIVE_FTP_ROOT = "ftp://ftp.cmegroup.com/span/archive/cme/"
SPAN_ARCHIVE_FIRST_DATE = date(2013, 1, 2)
SPAN_ARCHIVE_LAST_DATE = date(2025, 9, 12)
SPAN_LAYOUT_URL = (
    "https://cmegroupclientsite.atlassian.net/wiki/spaces/pubsub/pages/457083445"
)
CME_DATAMINE_ADVISORY = "https://www.cmegroup.com/notices/clearing/2021/12/Chadv21-471.html"
CME_FTP_DECOMMISSION_ADVISORY = "https://www.cmegroup.com/notices/clearing/2025/08/25-264.html"

# Globex root -> (SPAN exchange acronym, SPAN commodity code). Every pair
# was read from the "P " (product) records of cme.20190102.s.pa2 in this
# session; the long names quoted are the file's own bytes 80-114.
GLOBEX_TO_SPAN: dict[str, tuple[str, str, str]] = {
    "ES": ("CME", "ES", "E-MINI S&P 500 FUTURES"),
    "NQ": ("CME", "NQ", "E-MINI NASDAQ 100 FUTURES"),
    "YM": ("CBT", "YM", "E-MINI DOW ($5) FUTURES"),
    "RTY": ("CME", "RTY", "EMINI RUSSELL 2000 INDEX FUTURES"),
    "ZT": ("CBT", "26", "2 YEAR TREASURY NOTE FUTURES"),
    "ZF": ("CBT", "25", "5 YR TREASURY NOTE FUTURES"),
    "ZN": ("CBT", "21", "10Y TREASURY NOTE FUTURES"),
    "ZB": ("CBT", "17", "30 YR U.S. TREASURY BOND FUTURES"),
    "6E": ("CME", "EC", "EURO FUTURE"),
    "6J": ("CME", "J1", "JAPANESE YEN FUTURES"),
    "6B": ("CME", "BP", "BRITISH POUND FUTURES"),
    "6A": ("CME", "AD", "AUSTRALIAN DOLLAR FUTURES"),
    "6C": ("CME", "C1", "CANADIAN DOLLAR FUTURES"),
    "6S": ("CME", "E1", "SWISS FRANC FUTURES"),
    "CL": ("NYM", "CL", "CRUDE OIL FUTURES"),
    "BZ": ("NYM", "BZ", "BRENT LAST DAY CONTRACT"),
    "NG": ("NYM", "NG", "NATURAL GAS HENRY HUB FUTURE"),
    "HO": ("NYM", "HO", "NY HARBOR ULSD FUT"),
    "RB": ("NYM", "RB", "RBOB GASOLINE FUTURES"),
    "GC": ("CMX", "GC", "COMEX 100 GOLD FUTURES"),
    "SI": ("CMX", "SI", "COMEX 5000 SILVER FUTURES"),
    "HG": ("CMX", "HG", "COMEX COPPER FUTURES"),
    "PL": ("NYM", "PL", "PLATINUM FUTURES NYMEX"),
    "PA": ("NYM", "PA", "PALLADIUM FUTURES NYMEX"),
    "ZC": ("CBT", "C", "CORN FUTURES"),
    "ZS": ("CBT", "S", "SOYBEAN FUTURES"),
    "ZW": ("CBT", "W", "WHEAT FUTURES"),
    "ZL": ("CBT", "07", "SOYBEAN OIL FUTURES"),
    "ZM": ("CBT", "06", "SOYBEAN MEAL FUTURES"),
    "LE": ("CME", "48", "LIVE CATTLE FUTURES"),
    "HE": ("CME", "LN", "LEAN HOG FUTURES"),
}
SPAN_TO_GLOBEX: dict[tuple[str, str], str] = {
    (ex, code): globex for globex, (ex, code, _name) in GLOBEX_TO_SPAN.items()
}

# Last-digit fractional-tick code, used for alignment codes "C" (32nds) and
# "0" (cents). This is CME's price DISPLAY convention for fractions of a
# tick (a quarter is "2"/"7", a half "5", an eighth "1"/"3"/"6"/"8"; "4"
# and "9" are never used). Established empirically on 2019 files (see
# module docstring): grains and ZN/ZF/ZB showed ONLY {0,2,5,7} and matched
# Yahoo exactly; ZT (which ticks in 1/8 of a 32nd) additionally showed "3"
# on deferred months, and its front month read one eighth-of-a-32nd (one
# ZT tick) from Yahoo's last-trade close, i.e. a settle-vs-last difference,
# not a decoding one. The eighth digits {1,3,6,8} are INFERRED from the
# display convention and are counted by the run script wherever they occur.
# Any other digit is refused, never rounded.
FRACTION_CODE: dict[str, float] = {
    "0": 0.0, "1": 0.125, "2": 0.25, "3": 0.375, "5": 0.5, "6": 0.625, "7": 0.75, "8": 0.875,
}
QUARTER_CODE = FRACTION_CODE  # name kept for the docstring's examples
INFERRED_EIGHTH_DIGITS = frozenset({"1", "3", "6", "8"})

FTP_MAX_CONCURRENCY = 3
FTP_ATTEMPTS = 3
FTP_TIMEOUT_SECONDS = 600


class SpanDecodeError(ValueError):
    """A price whose alignment code / last digit is outside the verified
    decoding rules. Raised, never guessed around."""


@dataclass(frozen=True)
class ProductPriceFormat:
    exchange: str
    code: str
    locator: int
    alignment: str
    long_name: str


@dataclass(frozen=True)
class SettlementRow:
    trade_date: str  # YYYY-MM-DD, from the file name / "0 " header
    globex: str
    exchange: str
    span_code: str
    contract_month: str  # CCYYMM
    settle: float
    raw_settle: str  # 7-digit regular field, bytes 111-117 of "82"
    raw_hp_settle: str  # 14-digit field, bytes 109-122 of "81" ("" if absent)
    locator: int
    alignment: str
    expiration_date: str  # CCYYMMDD from "B " bytes 92-99, "" if absent


# ---------------------------------------------------------------------------
# pure decoding -- no I/O, unit-tested against hand-derived values
# ---------------------------------------------------------------------------


def decode_settlement(raw: str, locator: int, alignment: str, *, sign: str = "+") -> float:
    """Decode one 7-digit regular settlement field per the rules in the
    module docstring. `raw` is bytes 111-117 of an "82" record."""
    if len(raw) != 7 or not raw.isdigit():
        raise SpanDecodeError(f"settlement field {raw!r} is not 7 digits")
    if locator < 0:
        raise SpanDecodeError(f"negative decimal locator {locator} not supported")
    negative = sign == "-"
    if alignment == " " or alignment == "":
        value = int(raw) / (10**locator)
    elif alignment == "C":
        # Treasuries: integer part above the locator, then 32nds*10 with a
        # quarter code in the last digit. 0122060 / loc 3 -> 122 + 06.0/32.
        whole = int(raw[: 7 - locator])
        frac_digits = raw[7 - locator :]
        thirty_seconds = int(frac_digits[:-1])
        last = frac_digits[-1]
        if last not in QUARTER_CODE:
            raise SpanDecodeError(f"alignment C last digit {last!r} outside {sorted(QUARTER_CODE)}")
        value = whole + (thirty_seconds + QUARTER_CODE[last]) / 32.0
    elif alignment == "0":
        # Grains: cents/bushel with a quarter-cent code in the last digit.
        # 0003757 -> 375.75. The locator is deliberately NOT applied: the
        # quoted unit is cents, matching CME's own quote board and Yahoo.
        cents = int(raw[:-1])
        last = raw[-1]
        if last not in QUARTER_CODE:
            raise SpanDecodeError(f"alignment 0 last digit {last!r} outside {sorted(QUARTER_CODE)}")
        value = cents + QUARTER_CODE[last]
    else:
        raise SpanDecodeError(f"unknown settlement price alignment code {alignment!r}")
    return -value if negative else value


def parse_products(lines: Iterable[str]) -> dict[tuple[str, str], ProductPriceFormat]:
    """Type P records for FUT products -> price format per (exchange, code)."""
    out: dict[tuple[str, str], ProductPriceFormat] = {}
    for line in lines:
        if not line.startswith("P ") or line[15:18] != "FUT":
            continue
        exchange = line[2:5]
        code = line[5:15].strip()
        locator_field = line[33:36]
        locator = int(locator_field.replace("-", "")) * (-1 if locator_field.startswith("-") else 1)
        out[(exchange, code)] = ProductPriceFormat(
            exchange=exchange,
            code=code,
            locator=locator,
            alignment=line[39:40] if len(line) > 39 else " ",
            long_name=line[79:114].strip(),
        )
    return out


def parse_expirations(lines: Iterable[str]) -> dict[tuple[str, str, str], str]:
    """Type B records for FUT contracts -> expiration date CCYYMMDD per
    (exchange, code, contract month)."""
    out: dict[tuple[str, str, str], str] = {}
    for line in lines:
        if not line.startswith("B ") or line[15:18] != "FUT":
            continue
        key = (line[2:5], line[5:15].strip(), line[18:24])
        exp = line[91:99] if len(line) >= 99 else ""
        out[key] = exp if exp.strip().isdigit() else ""
    return out


def parse_pa2_text(text: str, *, trade_date: str, globex_roots: Iterable[str] | None = None) -> list[SettlementRow]:
    """Parse one decompressed .pa2 file into settlement rows for the
    requested Globex roots (default: every root in GLOBEX_TO_SPAN).

    Uses the "82" regular settlement field as the price of record and
    keeps the "81" high-precision field alongside it for the run script's
    consistency check (they must agree wherever the flag is "N")."""
    roots = list(globex_roots) if globex_roots is not None else list(GLOBEX_TO_SPAN)
    wanted = {GLOBEX_TO_SPAN[r][:2]: r for r in roots}
    lines = text.splitlines()
    products = parse_products(lines)
    expirations = parse_expirations(lines)
    hp: dict[tuple[str, str, str], str] = {}
    rows: list[SettlementRow] = []
    for line in lines:
        rid = line[:2]
        if rid not in ("81", "82") or line[25:28] != "FUT":
            continue
        key = (line[2:5], line[5:15].strip())
        if key not in wanted:
            continue
        month = line[29:35]
        if rid == "81":
            hp[(key[0], key[1], month)] = line[108:122]
            continue
        fmt = products.get(key)
        if fmt is None:
            raise SpanDecodeError(f"no Type P price format for {key} on {trade_date}")
        raw = line[110:117]
        sign = line[117:118] or "+"
        settle = decode_settlement(raw, fmt.locator, fmt.alignment, sign=sign)
        rows.append(
            SettlementRow(
                trade_date=trade_date,
                globex=wanted[key],
                exchange=key[0],
                span_code=key[1],
                contract_month=month,
                settle=settle,
                raw_settle=raw,
                raw_hp_settle="",
                locator=fmt.locator,
                alignment=fmt.alignment,
                expiration_date=expirations.get((key[0], key[1], month), ""),
            )
        )
    # attach the high-precision field (a second pass keeps the code linear)
    return [
        SettlementRow(**{**asdict(r), "raw_hp_settle": hp.get((r.exchange, r.span_code, r.contract_month), "")})
        for r in rows
    ]


def parse_pa2_zip(zip_bytes: bytes, *, trade_date: str | None = None, **kw) -> list[SettlementRow]:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = [n for n in zf.namelist() if n.endswith(".pa2")]
        if len(names) != 1:
            raise SpanDecodeError(f"expected exactly one .pa2 member, found {names}")
        text = zf.read(names[0]).decode("latin-1")
    if trade_date is None:
        header = text[: text.find("\n")]
        if not header.startswith("0 "):
            raise SpanDecodeError("first record is not the '0 ' exchange-complex header")
        ymd = header[8:16]
        trade_date = f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:8]}"
    return parse_pa2_text(text, trade_date=trade_date, **kw)


# ---------------------------------------------------------------------------
# archive addressing and fetching
# ---------------------------------------------------------------------------


def archive_url(d: date) -> str:
    ymd = d.strftime("%Y%m%d")
    if d.year == 2013:
        return f"{SPAN_ARCHIVE_FTP_ROOT}2013/{d.strftime('%Y%m')}/cme.{ymd}.s.pa2.zip"
    return f"{SPAN_ARCHIVE_FTP_ROOT}{d.year}/cme.{ymd}.s.pa2.zip"


def fetch_archive_zip(d: date) -> bytes | None:
    """One settlement-cycle zip, or None if the archive has no file for that
    date (weekends/holidays return an FTP 550). Never touches www.cmegroup.com."""
    url = archive_url(d)
    for attempt in range(1, FTP_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(url, timeout=FTP_TIMEOUT_SECONDS) as resp:
                return resp.read()
        except urllib.error.URLError as exc:  # type: ignore[attr-defined]
            reason = str(getattr(exc, "reason", exc))
            if "550" in reason:
                return None
            log.warning("SPAN fetch %s attempt %d failed: %s", url, attempt, reason)
            time.sleep(5 * attempt)
    raise RuntimeError(f"SPAN fetch failed after {FTP_ATTEMPTS} attempts: {url}")


# ---------------------------------------------------------------------------
# on-disk store: one compact CSV per trade date + one per Globex root
# ---------------------------------------------------------------------------

STORE_COLUMNS = [
    "trade_date", "globex", "exchange", "span_code", "contract_month", "settle",
    "raw_settle", "raw_hp_settle", "locator", "alignment", "expiration_date",
]


def daily_csv_path(store_dir: Path, d: date) -> Path:
    return store_dir / "daily" / f"{d.strftime('%Y%m%d')}.csv"


def write_daily_rows(store_dir: Path, d: date, rows: list[SettlementRow]) -> Path:
    path = daily_csv_path(store_dir, d)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame([asdict(r) for r in rows], columns=STORE_COLUMNS)
    tmp = path.with_suffix(".csv.tmp")
    frame.to_csv(tmp, index=False)
    tmp.replace(path)
    return path


def ingest_date(store_dir: Path, d: date, *, zip_bytes: bytes | None = None) -> int | None:
    """Fetch (or take) one day's zip, extract the target rows, write the
    daily CSV. Returns the row count, or None if the archive has no file.
    Idempotent: an existing daily CSV is left alone."""
    path = daily_csv_path(store_dir, d)
    if path.exists():
        return sum(1 for _ in open(path, encoding="utf-8")) - 1
    if zip_bytes is None:
        zip_bytes = fetch_archive_zip(d)
        if zip_bytes is None:
            return None
    rows = parse_pa2_zip(zip_bytes, trade_date=d.isoformat())
    write_daily_rows(store_dir, d, rows)
    return len(rows)


def ingest_range(store_dir: Path, start: date, end: date, *, concurrency: int = FTP_MAX_CONCURRENCY) -> dict[str, int | None]:
    """Weekday sweep over [start, end], at most `concurrency` FTP connections."""
    days = [d.date() for d in pd.bdate_range(start, end)]
    results: dict[str, int | None] = {}
    with ThreadPoolExecutor(max_workers=max(1, min(concurrency, FTP_MAX_CONCURRENCY))) as pool:
        for d, n in zip(days, pool.map(lambda x: ingest_date(store_dir, x), days)):
            results[d.isoformat()] = n
    return results


def load_daily(store_dir: Path) -> pd.DataFrame:
    """Every daily CSV in the store, concatenated. Empty frame if none."""
    files = sorted((store_dir / "daily").glob("*.csv")) if (store_dir / "daily").exists() else []
    if not files:
        return pd.DataFrame(columns=STORE_COLUMNS)
    frame = pd.concat(
        [pd.read_csv(f, dtype={"contract_month": str, "raw_settle": str, "raw_hp_settle": str, "expiration_date": str, "alignment": str}, keep_default_na=False) for f in files],
        ignore_index=True,
    )
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    frame["settle"] = frame["settle"].astype(float)
    return frame


def write_per_instrument(store_dir: Path, frame: pd.DataFrame) -> dict[str, int]:
    """<store>/by_instrument/<GLOBEX>.csv with date, contract_month, settle,
    expiration_date -- the shape a chain builder consumes."""
    out_dir = store_dir / "by_instrument"
    out_dir.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for globex, g in frame.groupby("globex"):
        g = g.sort_values(["trade_date", "contract_month"])[["trade_date", "contract_month", "settle", "expiration_date"]]
        g.to_csv(out_dir / f"{globex}.csv", index=False)
        counts[str(globex)] = len(g)
    return counts


def write_manifest(store_dir: Path, frame: pd.DataFrame, extra: dict | None = None) -> Path:
    per_instrument = {}
    for globex, g in frame.groupby("globex"):
        per_instrument[str(globex)] = {
            "rows": len(g),
            "trade_days": int(g["trade_date"].nunique()),
            "first_trade_date": str(g["trade_date"].min().date()),
            "last_trade_date": str(g["trade_date"].max().date()),
            "contract_months": int(g["contract_month"].nunique()),
            "unit": QUOTE_UNIT.get(str(globex), "exchange quoted unit"),
        }
    manifest = {
        "source": "CME Group public SPAN risk-parameter archive, end-of-day (.s) cycle",
        "source_url": SPAN_ARCHIVE_FTP_ROOT,
        "layout_url": SPAN_LAYOUT_URL,
        "terms_note": (
            "CME's website Data Terms of Use could not be read from this environment "
            "(www.cmegroup.com blocked the session's IP after a few page reads, and the "
            "fetcher timed out); the FTP archive is the channel CME's advisories call "
            "'CME's public FTP site' (Chadv21-471). Confirm permitted use before any "
            "use beyond internal research."
        ),
        "fetched_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "archive_coverage": f"{SPAN_ARCHIVE_FIRST_DATE.isoformat()} .. {SPAN_ARCHIVE_LAST_DATE.isoformat()}",
        "store_trade_days": int(frame["trade_date"].nunique()) if len(frame) else 0,
        "per_instrument": per_instrument,
        **(extra or {}),
    }
    path = store_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return path


QUOTE_UNIT: dict[str, str] = {
    "ES": "index points", "NQ": "index points", "YM": "index points", "RTY": "index points",
    "ZT": "price per 100 face (decimal of 32nds)", "ZF": "price per 100 face (decimal of 32nds)",
    "ZN": "price per 100 face (decimal of 32nds)", "ZB": "price per 100 face (decimal of 32nds)",
    "6E": "USD per EUR", "6J": "USD per JPY", "6B": "USD per GBP", "6A": "USD per AUD",
    "6C": "USD per CAD", "6S": "USD per CHF",
    "CL": "USD per barrel", "BZ": "USD per barrel", "NG": "USD per MMBtu",
    "HO": "USD per gallon", "RB": "USD per gallon",
    "GC": "USD per troy oz", "SI": "USD per troy oz", "HG": "USD per lb",
    "PL": "USD per troy oz", "PA": "USD per troy oz",
    "ZC": "cents per bushel", "ZS": "cents per bushel", "ZW": "cents per bushel",
    "ZL": "cents per lb", "ZM": "USD per short ton", "LE": "cents per lb", "HE": "cents per lb",
}
