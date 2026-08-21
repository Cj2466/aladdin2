from app.services.market_data.yfinance_provider import YFinanceProvider

# Module-level singleton, shared by every router that needs market data —
# moved out of risk.py so portfolios.py doesn't have to cross-import from it.
provider = YFinanceProvider()


def get_provider() -> YFinanceProvider:
    return provider
