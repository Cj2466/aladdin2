from fpdf import FPDF

from app.models.portfolio import Portfolio
from app.schemas.risk import PortfolioAnalyzeResponse
from app.services.risk.stress import ScenarioResult


def build_pdf_report(
    portfolio: Portfolio,
    analyze_result: PortfolioAnalyzeResponse,
    stress_results: list[ScenarioResult],
) -> bytes:
    pdf = FPDF()
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, f"Portfolio report: {portfolio.name}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=10)
    pdf.cell(
        0,
        8,
        f"As of {analyze_result.as_of} - base currency {portfolio.base_currency}",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Holdings", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=10)
    for holding in portfolio.holdings:
        weight_pct = f"{holding.weight * 100:.2f}%" if holding.weight is not None else "-"
        pdf.cell(0, 6, f"{holding.ticker}: {weight_pct}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Risk metrics", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=10)
    metrics = [
        ("Annualized volatility", f"{analyze_result.volatility_annualized * 100:.2f}%"),
        ("Historical VaR (95%)", f"{analyze_result.var_historical_95 * 100:.2f}%"),
        ("Parametric VaR (95%)", f"{analyze_result.var_parametric_95 * 100:.2f}%"),
        ("CVaR (95%)", f"{analyze_result.cvar_95 * 100:.2f}%"),
        ("Beta", f"{analyze_result.beta:.2f}"),
        ("HHI", f"{analyze_result.hhi:.4f}"),
        ("Avg pairwise correlation", f"{analyze_result.avg_pairwise_correlation:.2f}"),
    ]
    for label, value in metrics:
        pdf.cell(0, 6, f"{label}: {value}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Stress scenarios", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=10)
    for scenario in stress_results:
        estimated_note = " (includes estimated holdings)" if scenario.has_estimated else ""
        pdf.multi_cell(
            0,
            6,
            f"{scenario.label} ({scenario.start} to {scenario.end}): "
            f"portfolio {scenario.portfolio_return * 100:.2f}%, "
            f"benchmark {scenario.benchmark_return * 100:.2f}%{estimated_note}",
            new_x="LMARGIN",
            new_y="NEXT",
        )

    return bytes(pdf.output())
