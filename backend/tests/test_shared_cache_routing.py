"""The gitignored vendor caches that families read at import time resolve to the
MAIN checkout from every linked worktree (2026-09-12), like aladdin2.db and the
price/EDGAR stores. Before this, a worktree started with an empty cache while the
main checkout held the real one: the Step 0 dividend-pressure capture silently
replayed 0 specs and the CUSIP->ticker map was absent."""

from app.config import MAIN_CHECKOUT_BACKEND_DIR
from app.services.market_data import form13f_provider, nport_provider
from app.services.research_lab import dividend_payment_pressure_timing


def test_form13f_and_ftd_cache_is_routed_to_the_main_checkout():
    assert form13f_provider.DEFAULT_CACHE_DIR == MAIN_CHECKOUT_BACKEND_DIR / "data" / "form13f_raw"


def test_nport_cache_is_routed_to_the_main_checkout():
    assert nport_provider.DEFAULT_CACHE_DIR == MAIN_CHECKOUT_BACKEND_DIR / "data" / "nport_bulk"


def test_dividend_payment_calendar_is_routed_to_the_main_checkout():
    assert (
        dividend_payment_pressure_timing.PAYMENT_CACHE_PATH
        == MAIN_CHECKOUT_BACKEND_DIR / "data" / "dividend_payment_calendar.json"
    )
