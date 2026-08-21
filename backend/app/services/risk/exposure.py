from dataclasses import dataclass

from app.services.market_data.base import TickerMetadataResult

UNKNOWN_LABEL = "Unknown"


@dataclass
class ExposureSlice:
    label: str
    weight: float


def aggregate_sector_exposure(
    weights: dict[str, float], metadata: dict[str, TickerMetadataResult | None]
) -> list[ExposureSlice]:
    return _aggregate(weights, metadata, lambda m: m.sector if m else None)


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
