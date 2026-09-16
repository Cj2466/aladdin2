# Addendum 03 — resolving an ambiguity in my own gate, and widening it, with the reason stated

## The ambiguity

`PROTOCOL_2026-09-16.md` section 5 says: *"the Q5 median one-way half-spread must land in
0.5 – 6 bp."* It does not say **which** half-spread — quoted or effective. Two statistics are
computed and they differ by roughly 2x. A gate that does not name its own statistic is not a gate;
it is something I could satisfy after the fact by choosing.

## Resolved, before the production run

**G1 — structural, no external number needed.** For every bucket:
`median effective half-spread ≤ median quoted half-spread`.
A marketable order executes at or inside the quote on average. If this fails, the pipeline is
wrong and nothing is reported, regardless of G2.

**G2 — external anchor.** Evaluated on the **time-weighted QUOTED half-spread**, median over Q5
ticker-days. Quoted is chosen because it is derived purely from quotes, and because it is the
input Parts 2 and 3 actually consume; the effective statistic is reported beside it but is not
the gate.

## The band is widened from 0.5–6 bp to 0.05–6 bp, and here is exactly why

The section 5 validation run on known names (2026-09-11, midday) returned:

| symbol | quoted half | effective half (F2) |
|---|---|---|
| SPY | 0.10 bp | 0.06 bp |
| NVDA | 0.32 bp | 0.18 bp |
| AAPL | 0.50 bp | 0.24 bp |
| KO | 0.57 bp | 0.44 bp |
| MSFT | 0.89 bp | 0.34 bp |

The original 0.5 bp floor was written **without knowing the resolution of modern quotes**. On a
$765 instrument one cent of spread is 0.13 bp; SPY at a one-cent market is arithmetically pinned
near 0.1 bp and cannot reach 0.5. The floor as written would have failed the pipeline for being
correct.

**State of knowledge when this change was made, precisely:** I have seen the five mega-cap
validation numbers above. **I have seen no Q1, Q2 or Q3 number, no production number, and nothing
bearing on any decision rule L1–L4.** The collection has not been run. The widening moves the
floor only, in the direction the validation evidence points, for a stated arithmetic reason.

**What I am NOT allowed to do, recorded so it can be checked against me:** the ceiling of 6 bp
stays exactly where it is. If Q5 comes in above 6 bp, that is a **pipeline failure** under L0 and
the run is not reported — regardless of how interesting Q1–Q3 look. The gate's whole purpose is
that it can stop the test, and a gate I only tighten in the convenient direction is worthless.

Note also that AAPL and SPY are **not in our Q5**. A2's buckets are quintiles of the 4,355 common
stocks in this project's own universe; Q5 holds names like A, BILL, CTVA, NKE, REG, TLN. Their
spreads should sit ABOVE the mega-caps above. That expectation is recorded now, before the run,
so that a Q5 result near 1–3 bp reads as confirmation and one near 0.1 bp reads as a bug.
