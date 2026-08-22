from dataclasses import dataclass
from datetime import timedelta


@dataclass(frozen=True)
class MacroSeriesDefinition:
    series_id: str
    label: str
    category: str  # "inflation" | "rates" | "debt" | "growth"
    cadence: str  # "daily" | "monthly" | "quarterly"
    fred_units: str  # "lin" (native level/rate) or "pc1" (% change from a year ago)
    unit: str  # "percent" | "usd_trillions" — drives frontend formatting
    decimals: int


# FRED reports CPI/Core PCE as raw index levels (~314), meaningless to a
# retail investor without context — units="pc1" converts to "percent change
# from a year ago," i.e. the YoY inflation rate people actually mean by
# "CPI is 3.1%." Every other series here is already a native rate/level.
MACRO_SERIES: tuple[MacroSeriesDefinition, ...] = (
    MacroSeriesDefinition("CPIAUCSL", "CPI (YoY)", "inflation", "monthly", "pc1", "percent", 1),
    MacroSeriesDefinition("PCEPILFE", "Core PCE (YoY)", "inflation", "monthly", "pc1", "percent", 1),
    MacroSeriesDefinition("DGS3MO", "3-Month Treasury", "rates", "daily", "lin", "percent", 2),
    MacroSeriesDefinition("DGS2", "2-Year Treasury", "rates", "daily", "lin", "percent", 2),
    MacroSeriesDefinition("DGS10", "10-Year Treasury", "rates", "daily", "lin", "percent", 2),
    MacroSeriesDefinition("DGS30", "30-Year Treasury", "rates", "daily", "lin", "percent", 2),
    MacroSeriesDefinition("T10Y2Y", "10Y-2Y Spread", "rates", "daily", "lin", "percent", 2),
    MacroSeriesDefinition("DFF", "Fed Funds Rate", "rates", "daily", "lin", "percent", 2),
    MacroSeriesDefinition("T10YIE", "10Y Breakeven Inflation", "inflation", "daily", "lin", "percent", 2),
    MacroSeriesDefinition("GFDEBTN", "Federal Debt", "debt", "quarterly", "lin", "usd_trillions", 2),
    MacroSeriesDefinition("GFDEGDQ188S", "Debt-to-GDP", "debt", "quarterly", "lin", "percent", 1),
    MacroSeriesDefinition("A191RL1Q225SBEA", "Real GDP Growth", "growth", "quarterly", "lin", "percent", 1),
    MacroSeriesDefinition("UNRATE", "Unemployment Rate", "growth", "monthly", "lin", "percent", 1),
)

MACRO_SERIES_BY_ID: dict[str, MacroSeriesDefinition] = {s.series_id: s for s in MACRO_SERIES}

# Backend cache TTL per cadence tier — how long a cached value is trusted
# before re-checking FRED. Sized so a new release surfaces quickly (the
# "real-time" policy: never show a number staler than necessary) without
# hammering FRED for series that update at most once a day.
CADENCE_TTL: dict[str, timedelta] = {
    "daily": timedelta(minutes=30),
    "monthly": timedelta(hours=6),
    "quarterly": timedelta(hours=12),
}

# Deliberately static, honestly-worded hints rather than a literal
# countdown — a precise "T-minus-N-days" would imply per-series scheduling
# precision this app doesn't actually have without a second FRED
# integration (the release/dates endpoint).
CADENCE_NEXT_RELEASE_HINT: dict[str, str] = {
    "daily": "Next business day",
    "monthly": "Typically early-to-mid next month",
    "quarterly": "Typically ~1 month after quarter-end",
}

# Fixed maturity order for the yield-curve chart — reuses 4 of the series
# already being cached individually, no extra fetch needed.
YIELD_CURVE_SERIES: tuple[tuple[str, str], ...] = (
    ("DGS3MO", "3M"),
    ("DGS2", "2Y"),
    ("DGS10", "10Y"),
    ("DGS30", "30Y"),
)
