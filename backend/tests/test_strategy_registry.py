import pytest

from app.services.research_lab.strategy_registry import get_adapter


def test_get_adapter_returns_pairs_and_momentum():
    pairs = get_adapter("ou_pairs_v1")
    assert pairs.strategy_name == "ou_pairs_v1"
    assert pairs.direction_labels == ("long_spread", "short_spread")

    momentum = get_adapter("momentum_v1")
    assert momentum.strategy_name == "momentum_v1"
    assert momentum.direction_labels == ("long", "short")


def test_get_adapter_raises_on_unknown_strategy_name():
    with pytest.raises(ValueError):
        get_adapter("not_a_real_strategy")
