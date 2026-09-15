"""A2 addendum: re-price the book at a SOURCED spread curve, not an estimator.

Source (primary, fetched and read 2026-09-15):
  Collver, Charles, "A characterization of market quality for small
  capitalization US equities", US SEC, Division of Trading and Markets,
  September 2014.  https://www.sec.gov/marketstructure/research/small_cap_liquidity.pdf
  Sample: all of 2013, computed from the SEC's own MIDAS intraday trade-and-quote
  data (not an estimator). Effective spread = 2 x |trade price - prevailing
  midpoint|, dollar-value weighted; relative effective spread scales it by the
  midpoint. Paper's own text, discussion of Table 4:

    "Median relative effective spreads range from 0.922% to 1.235% for the
     smallest stocks and from 0.045% to 0.210% for stocks in the $2 to $5
     Billion capitalization range."

  "Smallest" = market cap below $100 Million. Ranges span the paper's price bins.

Converting: relative effective spread is a FULL spread, so the one-way
half-spread is half of it.
"""
import math, os, sys, json

AUDIT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "number_audit_2026-09-15")
sys.path.insert(0, os.path.abspath(AUDIT))
from a2_book_cost_exact import build            # noqa: E402
from audit_lockbox_numbers import load_doc, load_returns  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

# one-way HALF-spread, bp, from the SEC paper's medians
SEC = {
    "cap < $100M (SEC 2013, median)":      (0.922e4 / 2 / 100, 1.235e4 / 2 / 100),
    "cap $2-5B (SEC 2013, median)":        (0.045e4 / 2 / 100, 0.210e4 / 2 / 100),
}
# the project's existing sourced large-cap constant, for continuity
SP500 = (1.3, 2.3)   # Hagstromer JFE 2021 Table 1 / Mackintosh Nasdaq 2024


def main():
    meta = load_doc(); cols, months, data = load_returns()
    exact = json.load(open(os.path.join(HERE, "a2_book_cost_exact.json")))
    be = exact["breakeven_bp_per_reformation_for_sharpe_050"]

    print("one-way HALF-spread -> cost of one full long-short reformation = 4 x half\n")
    print(f"{'universe / source':>42s} {'half bp':>16s} {'reformation bp':>15s} "
          f"{'Sharpe':>16s} {'verdict':>16s}")
    rows = []
    scen = list(SEC.items()) + [("S&P 500 (Hagstromer/Mackintosh)", SP500)]
    for label, (lo_h, hi_h) in scen:
        lo_c, hi_c = 4 * lo_h, 4 * hi_h
        _, _, _, sr_lo = build(meta, cols, months, data, lo_c)
        _, _, _, sr_hi = build(meta, cols, months, data, hi_c)
        v_lo = "PASS" if sr_lo >= 0.50 else "FAIL"
        v_hi = "PASS" if sr_hi >= 0.50 else "FAIL"
        print(f"{label:>42s} {lo_h:7.1f}-{hi_h:<7.1f} {lo_c:7.1f}-{hi_c:<7.1f} "
              f"{sr_hi:7.3f}-{sr_lo:<7.3f} {v_hi:>7s}/{v_lo:<7s}")
        rows.append({"universe": label, "half_bp": [lo_h, hi_h],
                     "reformation_bp": [lo_c, hi_c],
                     "sharpe_at_cheap_end": round(sr_lo, 4),
                     "sharpe_at_dear_end": round(sr_hi, 4),
                     "verdict_cheap": v_lo, "verdict_dear": v_hi})

    print(f"\nthe book clears Sharpe 0.50 up to {be:.1f} bp per reformation.")
    print("\nOSAP builds 210 of 242 predictors EQUAL-WEIGHTED on CRSP, so the typical")
    print("member BY COUNT is a micro-cap -- the first row, not the last.")

    json.dump({"source": ("Collver, SEC Division of Trading and Markets, Sept 2014, "
                          "'A characterization of market quality for small capitalization "
                          "US equities', text accompanying Table 4; MIDAS intraday data, 2013"),
               "breakeven_bp_per_reformation_for_sharpe_050": be,
               "scenarios": rows},
              open(os.path.join(HERE, "a2_sourced_anchor.json"), "w"), indent=1)
    print("\nwrote a2_sourced_anchor.json")


if __name__ == "__main__":
    main()
