# Alpaca covers delisted names — the free answer to P2 for samples from 2016 onward (2026-09-11)

**Question (paid-decisions list, P2):** yfinance drops names that left the market, so every
universe built on it is survivorship-biased; the list named Norgate / CRSP / Sharadar as the
paid fix. Nobody had measured the FREE alternative already in the codebase — Alpaca's SIP daily
bars (`alpaca_provider.py`, history from 2016-01-04) — against a delisted sample. This run does.

**Method (`probe_alpaca_delisted.py`, output `alpaca_delisted_probe.json`):** the SAME 56-company
IPO sample the 2026-09-06 ipo_lockup feasibility probed against yfinance (six known-delisted
anchors, seven still-trading anchors, six recycled-ticker traps, 37 systematically sampled
2012–2019 IPOs), the SAME ±10-calendar-day lockup windows, fetched through `AlpacaProvider.
get_stock_bars(..., "1Day", feed="sip")`. A window ending before 2016-01-04 is UNTESTABLE on
Alpaca and is excluded from the rate, not counted as a miss. Run 2026-09-11 from the main
checkout; no DB or store writes.

**Result, orchestrator-run (not agent-reported):**

| | testable lockup windows (≥ 2016) | Alpaca resolved | yfinance resolved (2026-09-06) |
|---|---|---|---|
| all | 23 | **23 (100%)** | 12 (52.2%) |
| known-delisted anchor (CLDR) | 1 | 1 | 0 |
| still-trading anchors | 5 | 5 | 5 |
| systematic 2012–2019 IPOs | 17 | 17 | 7 |

Full-history probe (2016-01-04 → 2026-09-10), all 56 symbols: 54 resolved; the two misses
(GWAY, LMNS) were acquired in 2013 and 2015, before Alpaca's history begins — expected.
The six known-delisted anchors all return bars that END on their own delisting date and sit
at plausible price levels: LNKD last 2016-12-07 (delisted 12-08), median close 190.16;
FIT last 2021-01-13 (delisted 01-14), 6.33; ZNGA last 2022-05-20 (delisted 05-23), 5.28;
CLDR last 2021-10-07 (delisted 10-08), 13.18; TCS last 2024-12-09 (NYSE-delisted that day),
77.85 (adjusted for its 2024 reverse split — `adjustment=all`); P runs to 2026-09-10 because
the symbol was re-issued after Pandora's 2019 acquisition (see caveat 1).

**Caveats, stated before anyone builds on this:**
1. **Symbol re-use is not handled by the vendor.** A string like P, FB, SNOW returns whichever
   company holds it on each date. A delisted name's history must be cut at its own delisting
   date from an independent source (the SEC submissions store's last filing, or a corporate-
   action list). This probe did not do that automatically; the anchors were checked by hand.
2. **Coverage is measured on IPO-era names 2016–2026 only.** Nothing here speaks to pre-2016
   history, to OTC names, or to whether *every* delisting is retained (54/54 alive-at-2016 is
   the measured number, on a 56-name sample).
3. `adjustment=all` returns split- and dividend-adjusted closes; a point-in-time store wants
   raw closes plus the adjustment factors — the price store's own convention. Not tested here.
4. Alpaca's free SIP tier refuses any request whose window touches the current UTC day (403);
   end at the last complete UTC day.

**Paid-vendor prices, checked live 2026-09-11:** Norgate's package page (`norgatedata.com/
prices.php`) lists "Delisted securities" and "Historical index constituents" in the US Stocks
**Platinum** and **Diamond** packages (Silver/Gold exclude them); the dollar amounts are rendered
by JavaScript and were NOT extractable here — the owner must open the page. Nasdaq Data Link's
Sharadar SEP page is a JavaScript app; no price extractable; the public API returned "incorrect
dataset code" for `databases/SEP.json`. No price is claimed for either.

**Recommendation to the owner:** for any family whose sample starts 2016 or later, build the
universe on Alpaca daily bars with delisting dates taken from the SEC submissions store, and do
NOT buy P2 yet. Buy only if a family needs pre-2016 delisted history or index-constituent
history, which Norgate Platinum/Diamond supplies and Alpaca does not.
