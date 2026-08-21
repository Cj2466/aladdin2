import csv
import io

from app.models.portfolio import Portfolio
from app.schemas.risk import PortfolioAnalyzeResponse
from app.services.risk.stress import ScenarioResult


def build_csv_report(
    portfolio: Portfolio,
    analyze_result: PortfolioAnalyzeResponse,
    stress_results: list[ScenarioResult],
) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)

    writer.writerow(["Portfolio", portfolio.name])
    writer.writerow(["Base currency", portfolio.base_currency])
    writer.writerow(["As of", analyze_result.as_of])
    writer.writerow([])

    writer.writerow(["Holdings"])
    writer.writerow(["ticker", "weight"])
    for holding in portfolio.holdings:
        writer.writerow([holding.ticker, holding.weight])
    writer.writerow([])

    writer.writerow(["Risk metrics"])
    writer.writerow(["metric", "value"])
    writer.writerow(["volatility_annualized", analyze_result.volatility_annualized])
    writer.writerow(["var_historical_95", analyze_result.var_historical_95])
    writer.writerow(["var_parametric_95", analyze_result.var_parametric_95])
    writer.writerow(["cvar_95", analyze_result.cvar_95])
    writer.writerow(["beta", analyze_result.beta])
    writer.writerow(["hhi", analyze_result.hhi])
    writer.writerow(["avg_pairwise_correlation", analyze_result.avg_pairwise_correlation])
    writer.writerow([])

    writer.writerow(["Stress scenarios"])
    writer.writerow(
        ["scenario_id", "label", "start", "end", "portfolio_return", "benchmark_return", "has_estimated"]
    )
    for scenario in stress_results:
        writer.writerow(
            [
                scenario.scenario_id,
                scenario.label,
                scenario.start,
                scenario.end,
                scenario.portfolio_return,
                scenario.benchmark_return,
                scenario.has_estimated,
            ]
        )

    return buffer.getvalue()
