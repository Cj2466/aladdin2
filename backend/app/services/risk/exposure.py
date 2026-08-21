from dataclasses import dataclass

from app.services.market_data.base import TickerMetadataResult

UNKNOWN_LABEL = "Unknown"
NON_EQUITY_LABEL = "Non-equity"
_SECTORLESS_ASSET_CLASSES = {"Crypto", "Bond"}


@dataclass
class ExposureSlice:
    label: str
    weight: float


def _sector_or_non_equity(metadata: TickerMetadataResult | None) -> str | None:
    # Distinguish "metadata fetch failed" (still Unknown, worth retrying)
    # from "this asset class has no GICS sector by definition" (Crypto/Bond).
    if metadata is None:
        return None
    if metadata.sector:
        return metadata.sector
    if metadata.asset_class in _SECTORLESS_ASSET_CLASSES:
        return NON_EQUITY_LABEL
    return None


def aggregate_sector_exposure(
    weights: dict[str, float], metadata: dict[str, TickerMetadataResult | None]
) -> list[ExposureSlice]:
    return _aggregate(weights, metadata, lambda m: _sector_or_non_equity(m))


def aggregate_asset_class_exposure(
    weights: dict[str, float], metadata: dict[str, TickerMetadataResult | None]
) -> list[ExposureSlice]:
    return _aggregate(weights, metadata, lambda m: m.asset_class if m else None)


def _aggregate(weights, metadata, extract) -> list[ExposureSlice]:
    totals: dict[str, float] = {}
    for ticker, weight in weights.items():
        label = extract(metadata.get(ticker)) or UNKNOWN_LABEL
        totals[label] = totals.get(label, 0.0) + weight
    return sorted(
        (ExposureSlice(label=label, weight=weight) for label, weight in totals.items()),
        key=lambda s: s.weight,
        reverse=True,
    )
