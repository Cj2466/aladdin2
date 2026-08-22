from app.services.macro_data.cleveland_fed_provider import ClevelandFedNowcastProvider
from app.services.macro_data.fred_provider import FredProvider
from app.services.market_data.yfinance_provider import YFinanceProvider

# Module-level singleton, shared by every router that needs market data —
# moved out of risk.py so portfolios.py doesn't have to cross-import from it.
provider = YFinanceProvider()
macro_provider = FredProvider()
cleveland_fed_provider = ClevelandFedNowcastProvider()


def get_provider() -> YFinanceProvider:
    return provider


def get_macro_provider() -> FredProvider:
    return macro_provider


def get_cleveland_fed_provider() -> ClevelandFedNowcastProvider:
    return cleveland_fed_provider
