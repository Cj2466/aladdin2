"""Regenerates the committed correlation-matrix fixtures that pin the
published 7.10 / 8.11 effective-breadth baselines.

WHY THIS EXISTS
====================================================================
tests/test_futures_effective_breadth.py asserts that the reused
effective-breadth methodology still reproduces the two ETF/cash universe
figures the 15-instrument floor was applied to on 2026-09-05:

    Step 1  (43 nominal tickers) -> 7.098862632956790
    Step 1b (68 nominal tickers) -> 8.107830637943762

Those tests must run offline and deterministically, so they read committed
correlation matrices rather than re-fetching 68 tickers. This script is how
those matrices were produced, so they are reproducible artifacts rather than
unexplained fixture files.

It deliberately does NOT reimplement either run. It imports each run script
and calls that run's own panel builders and its own redundancy screen, so a
fixture can only ever be as faithful as the original pipeline itself.

Both original runs pin END = 2026-09-05, so the fetched window is fixed
rather than drifting with the calendar.

VERIFIED on 2026-09-07:
    Step 1  reproduced 7.098862632956793 (delta 3e-15 vs published),
            window 2011-11-16..2026-09-03, 3560 rows  -- matches the
            persisted JSON's window and row count exactly.
    Step 1b reproduced 8.107830637943760 (delta 2e-15 vs published),
            window 2012-02-06..2026-09-03, 3496 rows  -- likewise.

Run:  python data/research_runs/regenerate_tsmom_breadth_fixtures.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from app.config import MAIN_CHECKOUT_BACKEND_DIR  # noqa: E402
from app.services.market_data import price_store as _price_store  # noqa: E402

# The run scripts must be loaded from THIS checkout: run_combined_universe_
# effective_breadth.py carries its own guard refusing to run if `app`
# resolves to a different checkout than the script, precisely so a
# measurement can never silently mix two versions of the code.
RUNS = BACKEND / "data" / "research_runs"

# ...but the PRICE STORE is a different matter. price_store.DEFAULT_STORE_DIR
# is anchored to price_store.py's own location, so in a worktree it points at
# an EMPTY data/price_store and every fetch silently falls through to the
# network instead of the project's point-in-time store. That would make a
# "reproduction" of a 2026-09-05 figure depend on today's live yfinance
# response rather than on the stored data the original run actually used.
# The 2026-09-06 worktree fix shared the DATABASE across worktrees but not
# the price store, so this has to be pointed across by hand here.
# (Logged as an observation, not fixed here -- changing a shared data path
# for every caller is well outside this task's scope.)
_MAIN_STORE = (
    MAIN_CHECKOUT_BACKEND_DIR
    / "data"
    / "price_store"
    / _price_store.STORE_SCHEMA_VERSION
)
if _MAIN_STORE.is_dir():
    _price_store.DEFAULT_STORE_DIR = _MAIN_STORE
FIXTURES = BACKEND / "tests" / "fixtures"

PUBLISHED_STEP1 = 7.098862632956790
PUBLISHED_STEP1B = 8.107830637943762
TOLERANCE = 1e-9


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def regenerate_step1() -> float:
    step1 = _load("step1", RUNS / "run_combined_universe_effective_breadth.py")
    provider = step1.YFinanceProvider()
    end = step1.END

    commodities, _, _ = step1.build_commodities_price_panel(provider, end)
    fx, _, _ = step1.build_fx_price_panel(provider, end)
    country, _ = step1.fetch_country_price_panel(provider, end)
    country = country.dropna(how="any")
    bonds, _ = step1.build_bonds_price_panel(provider, end)

    combined = pd.concat(
        [bonds, commodities, fx, country], axis=1, join="outer", sort=False
    ).sort_index()
    returns = combined.pct_change(fill_method=None)
    breadth = step1.effective_breadth(returns)
    usable = returns.dropna(how="any")

    print(
        f"STEP 1  n={combined.shape[1]}  breadth={breadth!r}  "
        f"window={usable.index[0].date()}..{usable.index[-1].date()}  rows={len(usable)}"
    )
    usable.corr().to_csv(FIXTURES / "tsmom_step1_pooled_correlation_43.csv")
    return breadth


def regenerate_step1b() -> float:
    step1b = _load("step1b", RUNS / "run_expand_tsmom_universe.py")
    provider = step1b.YFinanceProvider()
    end = step1b.END

    bonds_before, _ = step1b.build_bonds_price_panel(provider, end)
    commodities_before, _, _ = step1b.build_commodities_price_panel(provider, end)
    fx_before, _, _ = step1b.build_fx_price_panel(provider, end)
    country_before, _ = step1b.fetch_country_price_panel(provider, end)
    country_before = country_before.dropna(how="any")

    start = step1b.CANDIDATE_FETCH_START
    new_fx, _, _ = step1b.fetch_new_fx_panel(provider, step1b.NEW_FX_CANDIDATES, start, end)
    new_country, _ = step1b.fetch_close_panel(provider, step1b.NEW_COUNTRY_CANDIDATES, start, end)
    new_bonds, _ = step1b.fetch_close_panel(provider, step1b.NEW_BONDS_CANDIDATES, start, end)
    new_commodities_raw, _ = step1b.fetch_close_panel(
        provider, step1b.NEW_COMMODITIES_CANDIDATES, start, end
    )
    new_commodities, _ = step1b.scrub_commodity_bad_prints(new_commodities_raw)

    def returns_dict(panel):
        return {c: panel[c].pct_change(fill_method=None).dropna() for c in panel.columns}

    fx_accepted, _ = step1b.screen_redundant_candidates(
        returns_dict(new_fx),
        returns_dict(fx_before),
        [c for c in step1b.NEW_FX_CANDIDATES if c in returns_dict(new_fx)],
    )
    country_accepted, _ = step1b.screen_redundant_candidates(
        returns_dict(new_country),
        returns_dict(country_before),
        [c for c in step1b.NEW_COUNTRY_CANDIDATES if c in returns_dict(new_country)],
    )
    bonds_accepted, _ = step1b.screen_redundant_candidates(
        returns_dict(new_bonds),
        returns_dict(bonds_before),
        [c for c in step1b.NEW_BONDS_CANDIDATES if c in returns_dict(new_bonds)],
    )
    commodities_accepted, _ = step1b.screen_redundant_candidates(
        returns_dict(new_commodities),
        returns_dict(commodities_before),
        [c for c in step1b.NEW_COMMODITIES_CANDIDATES if c in returns_dict(new_commodities)],
    )

    after = pd.concat(
        [
            bonds_before, new_bonds[list(bonds_accepted)],
            commodities_before, new_commodities[list(commodities_accepted)],
            fx_before, new_fx[list(fx_accepted)],
            country_before, new_country[list(country_accepted)],
        ],
        axis=1, join="outer", sort=False,
    ).sort_index()
    returns = after.pct_change(fill_method=None)
    breadth = step1b.effective_breadth(returns)
    usable = returns.dropna(how="any")

    print(
        f"STEP 1B n={after.shape[1]}  breadth={breadth!r}  "
        f"window={usable.index[0].date()}..{usable.index[-1].date()}  rows={len(usable)}"
    )
    usable.corr().to_csv(FIXTURES / "tsmom_step1b_pooled_correlation_68.csv")
    return breadth


def main() -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    failures = []
    for label, fn, published in (
        ("step1", regenerate_step1, PUBLISHED_STEP1),
        ("step1b", regenerate_step1b, PUBLISHED_STEP1B),
    ):
        measured = fn()
        delta = abs(measured - published)
        status = "OK" if delta <= TOLERANCE else "MISMATCH"
        print(f"  {label}: published {published!r}  delta {delta:.3e}  -> {status}")
        if delta > TOLERANCE:
            failures.append(f"{label} delta {delta:.3e}")
    if failures:
        raise SystemExit(
            "REFUSING TO TRUST THESE FIXTURES: " + "; ".join(failures)
        )
    print("both baselines reproduced within tolerance; fixtures written")


if __name__ == "__main__":
    main()
