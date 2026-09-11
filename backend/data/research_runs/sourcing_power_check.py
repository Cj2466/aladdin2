"""CLI for app.services.research_lab.sourcing_power_check -- the sourcing-stage
power pre-check that should run BEFORE a candidate family is built, not after.

Usage:
    python data/research_runs/sourcing_power_check.py \\
        --claimed-sharpe 1.08 --periods-per-year 252 --years-of-data 10.56 \\
        --n-local 8 [--bar 0.95] [--offset-fractions 1.0 0.5] [--json]

Prints the human-readable report (SourcingPowerCheckReport.summary()) by
default; --json prints the machine-readable dict instead (or in addition,
with --both). Exit code is 0 for PROCEED and 1 for DECLINE_AT_SOURCING, so
this can gate a build script.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.research_lab.sourcing_power_check import (
    PROCEED,
    sourcing_power_check,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Sourcing-stage power pre-check: before a family is built, check whether the "
            "DSR gate could even detect the source literature's claimed effect."
        )
    )
    parser.add_argument(
        "--claimed-sharpe",
        type=float,
        required=True,
        dest="claimed_sharpe_annualized",
        help="The source literature's claimed annualized Sharpe, net of this project's cost model.",
    )
    parser.add_argument(
        "--periods-per-year",
        type=float,
        required=True,
        help="Sampling frequency the family would screen at (e.g. 252 for daily equities).",
    )
    parser.add_argument(
        "--years-of-data",
        type=float,
        required=True,
        help="Calendar years of data actually available.",
    )
    parser.add_argument(
        "--n-local",
        type=int,
        required=True,
        help="Intended pre-declared grid size (number of specs).",
    )
    parser.add_argument(
        "--bar",
        type=float,
        default=0.95,
        help="DSR threshold to check power against (default 0.95).",
    )
    parser.add_argument(
        "--offset-fractions",
        type=float,
        nargs="+",
        default=[1.0, 0.5],
        help="Fractions of the claimed Sharpe to check (default: 1.0 0.5).",
    )
    parser.add_argument(
        "--skewness",
        type=float,
        default=0.0,
        help="Assumed skewness for the PSR variance term (default 0.0, the normal case).",
    )
    parser.add_argument(
        "--kurtosis",
        type=float,
        default=3.0,
        help="Assumed kurtosis for the PSR variance term (default 3.0, the normal case).",
    )
    parser.add_argument("--json", action="store_true", help="Print the JSON report instead of text.")
    parser.add_argument("--both", action="store_true", help="Print both the text summary and the JSON report.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    report = sourcing_power_check(
        claimed_sharpe_annualized=args.claimed_sharpe_annualized,
        periods_per_year=args.periods_per_year,
        years_of_data=args.years_of_data,
        n_local=args.n_local,
        bar=args.bar,
        offset_fractions=tuple(args.offset_fractions),
        skewness=args.skewness,
        kurtosis=args.kurtosis,
    )

    if args.json or args.both:
        print(json.dumps(report.to_dict(), indent=2))
    if not args.json or args.both:
        print(report.summary())

    return 0 if report.verdict == PROCEED else 1


if __name__ == "__main__":
    raise SystemExit(main())
