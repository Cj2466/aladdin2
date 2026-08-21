import pytest

from app.services.market_data.base import TickerMetadataResult
from app.services.risk.exposure import aggregate_asset_class_exposure, aggregate_sector_exposure


def test_aggregate_sector_exposure_groups_by_sector():
    weights = {"AAPL": 0.5, "MSFT": 0.3, "GLD": 0.2}
    metadata = {
        "AAPL": TickerMetadataResult(
            sector="Technology", industry="Consumer Electronics", asset_class="Equity", currency="USD"
        ),
        "MSFT": TickerMetadataResult(
            sector="Technology", industry="Software", asset_class="Equity", currency="USD"
        ),
        "GLD": TickerMetadataResult(sector=None, industry=None, asset_class="ETF", currency="USD"),
    }
    result = aggregate_sector_exposure(weights, metadata)
    by_label = {s.label: s.weight for s in result}
    assert by_label["Technology"] == pytest.approx(0.8)
    assert by_label["Unknown"] == pytest.approx(0.2)


def test_aggregate_asset_class_exposure():
    weights = {"AAPL": 0.5, "MSFT": 0.3, "GLD": 0.2}
    metadata = {
        "AAPL": TickerMetadataResult(sector="Technology", industry=None, asset_class="Equity", currency="USD"),
        "MSFT": TickerMetadataResult(sector="Technology", industry=None, asset_class="Equity", currency="USD"),
        "GLD": TickerMetadataResult(sector=None, industry=None, asset_class="ETF", currency="USD"),
    }
    result = aggregate_asset_class_exposure(weights, metadata)
    by_label = {s.label: s.weight for s in result}
    assert by_label["Equity"] == pytest.approx(0.8)
    assert by_label["ETF"] == pytest.approx(0.2)


def test_missing_metadata_bucketed_as_unknown_not_dropped():
    weights = {"ZZZZ": 1.0}
    metadata = {"ZZZZ": None}
    result = aggregate_sector_exposure(weights, metadata)
    assert len(result) == 1
    assert result[0].label == "Unknown"
    assert result[0].weight == pytest.approx(1.0)


def test_crypto_and_bond_labeled_non_equity_not_unknown():
    weights = {"BTC-USD": 0.5, "AGG": 0.5}
    metadata = {
        "BTC-USD": TickerMetadataResult(sector=None, industry=None, asset_class="Crypto", currency="USD"),
        "AGG": TickerMetadataResult(sector=None, industry=None, asset_class="Bond", currency="USD"),
    }
    result = aggregate_sector_exposure(weights, metadata)
    assert len(result) == 1
    assert result[0].label == "Non-equity"
    assert result[0].weight == pytest.approx(1.0)


def test_sorted_descending_by_weight():
    weights = {"A": 0.1, "B": 0.9}
    metadata = {
        "A": TickerMetadataResult(sector="Small", industry=None, asset_class=None, currency=None),
        "B": TickerMetadataResult(sector="Big", industry=None, asset_class=None, currency=None),
    }
    result = aggregate_sector_exposure(weights, metadata)
    assert [s.label for s in result] == ["Big", "Small"]
