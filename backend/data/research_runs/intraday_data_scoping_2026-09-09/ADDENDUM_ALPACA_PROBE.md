# Addendum — the recommended purchase is unnecessary (probe, 2026-09-09)

The memo's single recommended purchase was Massive "Stocks Developer" at
$79/month (verified price) for 10 years of minute bars, the entire data
requirement of M3 (Gao-Han-Li-Zhou intraday momentum, single instrument).
The memo's Alpaca paragraph quoted the pricing page ("Free: 7+ years, IEX
only") and did not test the project's own account.

**Probe, run from the main backend with the project's existing free Alpaca
credentials, read-only, 2026-09-09** (`AlpacaProvider.get_stock_bars`,
`timeframe="1Min"`, `regular_session_only=True`, symbol SPY):

| date | 1-minute rows returned |
|---|---|
| 2016-01-05 | 390 (a full 09:30–16:00 session) |
| 2017-01-05 | 390 |
| 2019-01-07 | 390 |
| 2021-01-05 | 390 |

So free minute bars exist on this account back to at least January 2016 —
10.7 years, covering the full out-of-sample window M3 needs. **Data cost for
M3 is $0.** The $79/month tier would add 2014–2015 only.

Two caveats, stated rather than assumed away:

1. **Feed.** The pricing page says the free tier is IEX-only; this project's
   own provider module records that on 2026-08-26 the same account returned
   full SIP consolidated data by default (a volume comparison, documented in
   `alpaca_provider.py`'s header). Which entitlement applies to *historical*
   2016 minute bars was not re-tested here. For a SPY price-return test at
   the half-hour horizon the distinction is immaterial (IEX SPY quotes are
   inside the consolidated spread essentially always); for any volume-based
   or auction-based construction it is not, and must be re-verified first.
2. **Survivorship.** Irrelevant for a single-instrument SPY test; the
   memo's delisted-coverage UNVERIFIED item stands for anything
   cross-sectional.

Nothing in the memo's ranking or its headline finding changes — this only
removes the one line item that had a price on it.
