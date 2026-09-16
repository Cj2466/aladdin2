# Effective spread — the regulatory text, fetched and quoted before any number exists

Required by `PROTOCOL_2026-09-16.md` section 4, which states that the effective-spread statistic
is dropped entirely if this cannot be verified. It is verified. Source:
[17 CFR § 242.600(b)](https://www.law.cornell.edu/cfr/text/17/242.600), Cornell LII, fetched
2026-09-16.

## The definition, verbatim

**§ 242.600(b)(8) — Average effective spread:**

> "the share-weighted average of effective spreads for order executions calculated, for buy orders,
> as double the amount of difference between the execution price and the midpoint of the national
> best bid and national best offer **at the time of order receipt** and, for sell orders, as double
> the amount of difference between the midpoint of the national best bid and national best offer
> at the time of order receipt and the execution price."

**§ 242.600(b)(13) — Average realized spread:**

> "the share-weighted average of realized spreads for order executions calculated, for buy orders,
> as double the amount of difference between the execution price and the midpoint of the national
> best bid and national best offer **at a specified interval after the time of order execution**
> and, for sell orders, as double the amount of difference between the midpoint and the national
> best bid and national best offer at a specified interval after the time of order execution and
> the execution price."

And from § 242.605(a)(1)(ii), fetched separately from the
[GPO's own CFR text](https://www.govinfo.gov/content/pkg/CFR-2010-title17-vol3/pdf/CFR-2010-title17-vol3-sec242-605.pdf):
average effective spread is reported **"(ii) For market orders and marketable limit orders"** only.
The regulatory statistic is a property of liquidity-TAKING orders. That is exactly Policy M in the
protocol, and it is not a property of Policy X or P.

## Deviation 1 — we use trade time, not order-receipt time. Logged, not hidden.

The definition anchors the midpoint at **the time of order receipt**. A consolidated tape does not
carry order-receipt times; it carries execution times. We therefore compute the midpoint from the
last NBBO update at or before the **execution** timestamp.

- This is the standard academic construction, not an invention here, but it **is** a departure from
  the regulatory definition and every number produced must be labelled "effective spread (trade-time
  midpoint)", never "Rule 605 effective spread".
- Direction of the error: order receipt precedes execution, so a regulatory midpoint is taken from
  a slightly staler quote. For orders executing in milliseconds the two coincide; for orders worked
  over seconds they do not. **Whether this biases our number up or down is not determined here**,
  and it is not assumed to be negligible.

## Deviation 2 — trade direction is not on the tape. This one costs nothing.

The definition is signed (buy vs sell). The tape does not mark direction. We use the quote rule:
a trade above the prevailing midpoint is a buy, below is a sell. Under that rule the signed
quantity is **identically** `2 × |P − M|`, so taking the absolute value is not an approximation
for any trade off the midpoint. Trades exactly at the midpoint contribute 0 under either treatment.

The residual is that the quote rule itself misclassifies some trades; that misclassification
changes the SIGN, not the magnitude, so it does not affect this statistic. It would affect a
realized-spread or price-impact statistic, and neither is computed here.

## Deviation 3 — SIP timestamps, not exchange-side NBBO reconstruction.

The NBBO used is the consolidated quote stream as timestamped by the vendor. A true Rule 605
calculation is done by the market center against its own view. We are outside the tape, later than
it, and cannot reproduce that. Consequence: our number is what a reader of the public tape would
compute, which is the right object for "what would this trade have cost us", and the wrong object
for "what does this venue report". Only the former is claimed.
