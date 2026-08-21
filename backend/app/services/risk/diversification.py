import numpy as np
import pandas as pd


def herfindahl_index(weights: dict[str, float]) -> float:
    """Weight-concentration measure: sum(w_i^2). 1.0 = fully concentrated in
    one holding, 1/n = perfectly equal-weighted across n holdings. Does not
    account for correlation between holdings — see average_pairwise_correlation."""
    return float(sum(w**2 for w in weights.values()))


def average_pairwise_correlation(corr_matrix: pd.DataFrame) -> float:
    """Mean of the off-diagonal correlation entries. A concentration measure
    (HHI) alone would call an equal-weighted portfolio of highly correlated
    holdings 'diversified' when it isn't — this catches that."""
    n = corr_matrix.shape[0]
    if n < 2:
        return float("nan")
    values = corr_matrix.to_numpy()
    off_diag_sum = values.sum() - np.trace(values)
    count = n * (n - 1)
    return float(off_diag_sum / count)
