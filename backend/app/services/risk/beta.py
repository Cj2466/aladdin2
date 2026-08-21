import pandas as pd


def compute_beta(portfolio_returns: pd.Series, benchmark_returns: pd.Series) -> float:
    aligned = pd.concat(
        [portfolio_returns.rename("portfolio"), benchmark_returns.rename("benchmark")],
        axis=1,
    ).dropna()

    if len(aligned) < 2:
        return float("nan")

    covariance = aligned["portfolio"].cov(aligned["benchmark"])
    variance = aligned["benchmark"].var(ddof=1)
    if variance == 0:
        return float("nan")
    return float(covariance / variance)
