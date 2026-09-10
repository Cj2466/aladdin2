# Feasibility memo — leveraged-ETF end-of-day rebalancing flow

FEASIBILITY ONLY. No signal built, no return statistic computed, no DB write,
nothing merged to main. Worktree `letf-feasibility` / branch
`letf-feasibility-2026-09-11`, off main `2a1149e`.

---

## Q1 — Literature, verbatim

### Cheng & Madhavan (2009), "The Dynamics of Leveraged and Inverse
Exchange-Traded Funds", *Journal of Investment Management*, 7(4), 43-62.

**COULD NOT OBTAIN THE PRIMARY SOURCE DIRECTLY.** Every fetch attempt failed:
- SSRN abstract page (`papers.ssrn.com/sol3/papers.cfm?abstract_id=1539120`) —
  HTTP 403 to both `WebFetch` and `curl`.
- SSRN's own delivery/download endpoint — returned an HTML "Content Blocked"
  page, not a PDF.
- Wayback Machine copy of the SSRN page — resolved but the underlying PDF
  delivery link still routes through SSRN and was not independently tested
  further after two failures.
- ResearchGate request-PDF page — HTTP 403.
- `dialnet.unirioja.es/descarga/articulo/4690294.pdf` (found via search,
  looked like it might be an indexed copy) — downloaded but the PDF is
  corrupt (`pdftotext` errors: "Invalid XRef entry", "Missing 'endstream'",
  "Couldn't find trailer dictionary"); unusable.
- Semantic Scholar paper page — no open-access PDF link found.

**What is verified instead, and how**: Shum, Hejazi, Haryanto & Rodier
(2016) — the peer-reviewed *Review of Finance* paper, obtained in full (see
next section) — quotes and re-derives Cheng & Madhavan's formula directly,
with its own citation and an appendix derivation. From the fetched text
(`pdfs/utoronto_scholaris.txt`, line ~404 onward, section 2):

> "The rebalancing process is primarily executed near the market's close
> because leveraged ETFs are designed to replicate daily returns for
> investors, which are calculated from each day's market's close to the
> following day's market's close. Cheng and Madhaven (2009) provide a
> generalized expression that describes the amount by which a leveraged
> ETF's counterparty should rebalance at day's end. We estimate and use
> this amount in our empirical models. (See the derivation of this
> expression in appendix A).
>
>     RA_t = NAV_{t-1} (x^2 - x) r_t                    (1)
>
> where: RA_t = potential rebalancing amount on day t; NAV_{t-1} = leveraged
> ETF's net asset value at day (t-1)'s close; x = exposure of the leveraged
> ETF to the index that it tracks, e.g., x = 2 for a 2x long; r_t = return
> of the index from day (t-1)'s close to day t's close."

This is EXACTLY the `(L^2 - L)*A*r` formula stated in the orchestrator's
brief (with `x` = `L`). It is a **secondary-source verification**, not a
direct read of Cheng & Madhavan's own paper — flagged accordingly.

Also quoted from Shum et al. (2016), attributing to Cheng & Madhavan (2009)
directly, giving that paper's headline empirical estimate (line ~219):

> "Cheng and Madhavan (2009) estimate that if the market moves by one
> percent during the day, leveraged ETF rebalancing could account for up to
> 16.8 percent of the market-on-close (MOC) volume. Further, if the market
> moves by five percent, up to 50 percent of the MOC volume could be
> attributable to leveraged ETF trading."

**Cheng & Madhavan's own timing/decay claims (e.g. whether their sample-period
findings have since decayed) are UNVERIFIED** — I have only what Shum et al.
cite, not the original paper's own text, tables, or sample period.

### Shum, Hejazi, Haryanto & Rodier (2016), "Intraday Share Price Volatility
and Leveraged ETF Rebalancing", *Review of Finance* 20(6), 2379-2409,
DOI `10.1093/rof/rfv061`.

**SOURCE ACTUALLY READ**: the accepted manuscript / post-print, hosted openly
by the University of Toronto's TSpace repository (an institutional
open-access mandate copy, explicitly labeled "This article was made openly
accessible by U of T Faculty"), fetched 2026-09-10:
`https://utoronto.scholaris.ca/server/api/core/bitstreams/55d149e5-bf5c-4211-a446-6326d2397019/content`
(HTTP 200, 1.2MB PDF, `pdftotext -layout`'d to 2,470 lines, read in full —
saved locally as `pdfs/utoronto_scholaris.txt` in the session scratchpad, not
committed to the repo). Also cross-cited from `ssrn.com/abstract=2161057`
(the working-paper version, same authors, confirmed as the pre-print of this
article via the paper's own text: "Electronic copy available at:
https://ssrn.com/abstract=2161057" appears as a running footer throughout).

**(a) The formula** — Eq.(1)/(2), quoted above under Cheng & Madhavan.

**(b) Timing** (lines ~183, ~238, ~778):
> "the day, rather than over the entire trading session. Their swap
> counterparties have to rebalance ... toward the market's close."
>
> "It should be pointed out that while bull ETFs seek to generate 2x or 3x
> its underlying index's return ... rebalancing could begin as early as
> 15:30:00, thereby impacting volatility earlier."
>
> "designed to replicate daily returns of the underlying index, the
> rebalancing transactions could ... spread out the price impact, the
> rebalancing activities could begin as early as 3:30PM, based on ...
> rebalancing amounts on volatility only in the last three 15-minute
> windows."

So the paper's own empirical windows are the **last three 15-minute
intervals of the regular session — 15:30-15:45, 15:45-16:00, and (their
window 27) 16:00:00-16:14:59** (their intervals extend slightly past the
4:00pm close to capture MOC-related trading).

**(c) Empirical late-day effect, magnitude and sample period** (lines
~53-54, ~295-297, ~473, ~577, ~904-926):
> "over the period surrounding the financial crisis, 2006-2011, we show that
> end-of-day volatility was positively and statistically significantly
> correlated with the ratio of potential rebalancing trades to total
> [dollar volume]"
>
> "U.S. large-cap leveraged ETFs, over the period surrounding the financial
> crisis, from July 2006 to July 2011... Our sample period is from June 20,
> 2006 to July 14, 2011... we focus on the volatility of a balanced sample
> of 346 stocks" (S&P 500 constituents that remained on the index the whole
> period, 52 leveraged ETFs in total, Table ii).
>
> Magnitude (window 27, 16:00:00-16:14:59, negative-return subsample): "the
> impact of rebalancing on volatility is 0.06, which represents 33.85
> percent of the average volatility in that window. When the sample is
> restricted to days when RelV_t is greater than the 50th percentile, the
> impact represents 36.89 percent; ... 70th percentile, ... 41.26 percent;
> ... 90th percentile, ... 56.45 percent." The paper calls this
> "economically significant" because it exceeds one-third of mean window
> volatility.

**Robustness finding directly relevant to feasibility (Q5)** — section 5.2.2,
quoted above under flow_scale.json's methodology note: when the authors
substitute SPY itself as the hypothetical rebalancing vehicle instead of the
346-stock basket, the relative-volume ratios "range from 1,781 percent for
the 50th percentile up to 8,646 percent for the 90th percentile... These
percentages suggest that using SPY alone in rebalancing trades is not
feasible... the rebalancing trades must involve individual securities." This
is the paper's own statement that an ETF-only liquidity comparison
understates true capacity constraints (constituent-level trading is where it
actually happens) — but also that SPY-relative ratios below ~100% (unlike
this paper's 1,781%+) would NOT by themselves rule out ETF-level absorption.

### Ivanov & Lenkey — Federal Reserve FEDS Working Paper 2014-106, "Are
Concerns About Leveraged ETFs Overblown?" (November 19, 2014), later
published as Ivanov & Lenkey, "Do Leveraged ETFs Really Amplify Late-Day
Returns and Volatility?", *Journal of Financial Markets* 41 (2018), 36-56.

**NOTE ON TITLE**: the orchestrator's brief named the paper by its 2018
*published* title; the underlying FEDS working paper (2014, the version
fetched) is titled differently ("Are Concerns About Leveraged ETFs
Overblown?"). Flagging this so the title mismatch isn't mistaken for a wrong
paper — confirmed same authors, same FEDS number (2014-106), and the 2018
citation is the well-documented published version of this same working
paper (confirmed via search results citing both under FEDS 2014-106).

**SOURCE ACTUALLY READ**: fetched directly from the Federal Reserve Board,
2026-09-10: `https://www.federalreserve.gov/econresdata/feds/2014/files/2014106pap.pdf`
(HTTP 200, 1,554,476 bytes, 37 pages, `pdftotext -layout`'d to 1,338 lines,
read in full — `pdfs/ivanov_lenkey_feds2014106.txt`, not committed).

**Central claim, verbatim (abstract)**:
> "Leveraged and inverse exchange-traded funds (ETFs) have been heavily
> criticized for exacerbating volatility in financial markets because it is
> thought that they mechanically rebalance their portfolios in the same
> direction as contemporaneous returns. We argue that these criticisms are
> likely exaggerated because they ignore the effects of capital flows on ETF
> rebalancing demand. Empirically, we find that capital flows substantially
> reduce the need for ETFs to rebalance when returns are large in magnitude
> and, therefore, mitigate the potential for these products to amplify
> volatility. We also show theoretically that flows can completely eliminate
> ETF rebalancing in the limit."

Further, on the mechanism of offset (body, lines ~78-143):
> "capital flows reduce rebalancing when the flows offset the change in the
> ETF's assets under management" ... "capital flows diminish the potential
> for leveraged and inverse ETFs to exacerbate volatility" ... "The effects
> of capital flows appear to be stronger for ETFs with higher leverage
> ratios." Also, a caveat the abstract omits: "evidence suggests that
> capital flows may aggravate rather than mitigate the potential to
> [amplify volatility for some funds]... capital flows seem to have only a
> small effect on their rebalancing demand" for certain fund types (the
> exact conditions were not fully re-derived in this feasibility pass —
> UNVERIFIED beyond this general statement).

**This directly bears on the "same-sign, both bull and bear" mechanical
claim in the orchestrator's brief**: Ivanov-Lenkey's finding is that the
MECHANICAL formula (`(L^2-L)*A*r`, same as Cheng-Madhavan/Shum et al.) is
correct as a description of what maintaining constant leverage requires, but
that real-world `A_t` itself is not static — investor capital flows change
`A_t` in ways correlated with `r_t`, and empirically those flows often
subtract from, not add to, the mechanical rebalancing need. This is a
**partial-offset finding, not a "no effect" finding** — the authors still
report the underlying mechanical driver exists; they show it is dampened.

### EFMA 2024 paper — FOUND AND VERIFIED (previously unverified by the
orchestrator)

Jain, Pankaj K.; Mishra, Suchismita; Pagano, Michael S.; Rodriguez, Ivan M.
Jr., "Of Seesaws and Swings: The Market-wide Impact of Levered ETF
Rebalancing during Stressful Times", presented at EFMA (European Financial
Management Association) annual meetings 2024 (conference paper history shows
prior presentations at FMA 2020, Southwest Finance Association 2021, Eastern
Finance Association 2021, Southern Finance Association 2022 per its own
acknowledgments footnote — this is a long-running working paper, **not**
confirmed as peer-reviewed-published as of this fetch).

**SOURCE ACTUALLY READ**: fetched directly, 2026-09-10:
`http://www.efmaefm.org/0EFMAMEETINGS/EFMA%20ANNUAL%20MEETINGS/2024-Lisbon/papers/LETF20231228EFMA.pdf`
(HTTP 200 via `curl`, 2,267,565 bytes, 77 pages, `pdftotext -layout`'d to
2,841 lines, read in relevant part — `pdfs/efma_letf_2024.txt`, not
committed).

**Abstract, verbatim**:
> "We show theoretically that the interplay between investor behavior (LETF
> fund flows) and index return autocorrelation ('see-saw effect') plays a
> central role in either moderating or amplifying the portfolio rebalancing
> demand of levered and inverse-levered ETFs (LETFs). Rebalancing, in turn,
> affects the underlying ETF and market-wide volatility. Disagreement
> between LETF investors and other market participants surprisingly leads to
> moderation of volatility at the onset of COVID-19 pandemic. However, after
> the announcement, there was agreement and an amplification of volatility."

Sample and headline finding (line ~238): "We perform empirical tests and
[analyze] LETFs during the 2006-2020 period. Our estimates provide
statistically and economically significant" [results — the sentence
continues past what I quoted verbatim; the specific magnitude was not
re-extracted in this pass]. This paper explicitly builds on and extends
Ivanov & Lenkey (2018) (its own words: "extending Ivanov and Lenkey (2018) to
include a potentially important additional variable"), and treats the
COVID-19 period as its key out-of-sample stress test — so **it does NOT
report a decay of the mechanism post-2012**; if anything it reports a live,
COVID-era-confirmed effect, conditional on the "see-saw" (index-return
autocorrelation) regime. This is the most recent (2020s) evidence found in
this pass that the underlying mechanical effect Cheng-Madhavan/Shum et al.
described has NOT been arbitraged away, though its magnitude is now
state-dependent on a variable (return autocorrelation / investor
disagreement) not modeled in the earlier two papers.

**Not independently searched further** for any 2023-2025 paper beyond this
one; a more recent (post-2024) academic treatment may exist and was not
found in the searches run this session.

### Summary across the four sources
No paper found in this pass claims the mechanical rebalancing formula itself
has decayed or vanished. What varies across papers is how much of the
mechanical, formula-implied flow actually reaches the market as net
directional demand, once investor capital flows (Ivanov-Lenkey) and the
"see-saw" autocorrelation/disagreement regime (Jain-Mishra-Pagano-Rodriguez)
are accounted for. Shum et al. (2016) find the raw, unadjusted effect
statistically and economically significant in 2006-2011 data; the EFMA paper
extends the empirical record to 2020 and still finds significant effects,
conditional on regime.

---

## Q2 — LETF universe

See `letf_universe.csv` (committed). 20 funds across 6 underlyings (S&P 500,
Nasdaq-100, Russell 2000, Semiconductors, Biotech, Gold Miners), each row's
AUM independently fetched 2026-09-09/10 with a cited URL (ProShares: issuer's
own fund page via `WebFetch`; Direxion: `stockanalysis.com`, third-party,
because Direxion's own site returned HTTP 403 to every automated fetch
attempt — see "Things I could not verify"). One additional out-of-scope row
(TSLL, Direxion 2x single-stock Tesla ETF, $3.40B AUM as of 2026-09-10) is
included only to show single-stock LETF AUM scale is already comparable to
several of the index-level funds above — excluded from all per-underlying
aggregates per the task's scope instruction.

**Note on the semiconductor underlying**: the orchestrator's brief names
SOXX/SMH as the reference underlyings, but Direxion's SOXL/SOXS actually
track Direxion's/ICE's own **"ICE Semiconductor Index"** (labeled "NYSE
Semiconductor Index" historically), which is closely related to but is NOT
literally the same index SOXX (ICE Semiconductor Index — actually SOXX does
track a very similar-sounding index; **this distinction was not fully
resolved and is flagged as unverified** — whether SOXX and SOXL/SOXS track
literally the identical index or two similar-but-distinct semiconductor
indices needs a direct index-methodology check before any construction
work, not assumed identical here). Biotech (LABU/LABD) and Gold Miners
(NUGT/DUST) were more clearly confirmed: both explicitly track the same
named index XBI and GDX respectively track (S&P Biotechnology Select
Industry Index; MarketVector Global Gold Miners Index) — Q4/Q5 therefore use
SOXX/XBI/GDX as reasonable but not fully verified same-index proxies for
volume comparison purposes only (not for return construction).

**Per-underlying aggregate `Σ AUM_i * (L_i^2 - L_i)`** (the dollar
coefficient that gets multiplied by `r_t` to get implied rebalancing demand
— computed in `flow_scale.py`, see Q5):

| Underlying | Σ AUM*(L²−L) (USD) |
|---|---|
| S&P 500 | $103.2B |
| Nasdaq-100 | $268.8B |
| Russell 2000 | $3.47B |
| Semiconductors | $142.3B |
| Biotech | $4.22B |
| Gold Miners | $3.35B |

Nasdaq-100 and Semiconductors dominate — both driven by one enormous single
fund each (TQQQ $35.8B and SOXL $21.1B respectively) combined with 3x
leverage (coefficient 6).

---

## Q3 — Historical daily AUM / shares outstanding

Full detail in `aum_sources.md` (committed). Short version:

- **ProShares: YES**, a genuine free daily historical NAV/shares-outstanding
  /AUM CSV exists (`https://accounts.profunds.com/etfdata/historical_nav.csv`,
  linked from `proshares.com/resources/data-downloads`), independently
  fetched and verified in this session (52.5MB, HTTP 200). Covers all 12
  target ProShares tickers daily from 2008-01-02 or 2013-01-02 depending on
  fund (NOT always back to true inception — a real, disclosed gap). Evidence
  sample committed at `proshares_nav_history_sample.csv`.
- **Direxion: NOT VERIFIED / likely no free historical series.** Direxion's
  own site blocked every automated fetch attempt (HTTP 403, both `WebFetch`
  and `curl` with multiple user agents) on both the fund-listing page and
  four individual product pages. No historical-NAV download analogous to
  ProShares' was found via search. Current-day AUM only, via a third-party
  aggregator. **This means the semiconductor, biotech, and gold-miner legs of
  this candidate — and one of the two S&P 500 issuer families — currently
  have no confirmed free point-in-time AUM history.** A forward (starting
  today) collection is possible the same way this project's existing
  price/EDGAR point-in-time stores work, but that is NOT the same as having
  history to backtest against.
- **SEC N-PORT**: an issuer-agnostic backstop exists in principle (monthly,
  quarter-end-only public, real lag), and this project already has N-PORT
  ingestion code (`cross_sectional_nport_flow.py`,
  `cross_sectional_firesale_pressure.py`) that could in principle be reused
  — but this was not tested for AUM-field quality or timeliness in this
  pass, and monthly/lagged data is a poor match for a daily-`A_t` formula.

---

## Q4 — Alpaca minute-bar sample (data availability only)

Script: `fetch_alpaca_sample.py` (committed, reruns cleanly — verified by
actually running it in this session with the main checkout's `.env` Alpaca
credentials sourced, never printed/copied/committed). Output:
`alpaca_minute_sample.json` (committed). Full bar pickles were written to
the session scratchpad only, per instruction, not the repo.

Tickers: SPY, QQQ, IWM, SOXX, XBI, GDX. Windows: 2016-01-04..2016-01-29 and
2025-06-02..2025-06-27.

| Ticker | Window | Days | Mean min/day | Last-30-min $vol share | Last-min $vol share |
|---|---|---|---|---|---|
| SPY | 2016 | 19 | 390.0 | 15.0% | 1.9% |
| QQQ | 2016 | 19 | 390.0 | 14.2% | 1.6% |
| IWM | 2016 | 19 | 390.0 | 14.6% | 2.0% |
| SOXX | 2016 | 19 | 277.9 (191-352 range) | 15.8% | 2.3% |
| XBI | 2016 | 19 | 389.4 | 13.9% | 1.6% |
| GDX | 2016 | 19 | 390.0 | 20.2% | 5.4% |
| SPY | 2025 | 19 | 390.0 | 18.0% | 3.1% |
| QQQ | 2025 | 19 | 390.0 | 13.3% | 2.3% |
| IWM | 2025 | 19 | 390.0 | 17.1% | 3.2% |
| SOXX | 2025 | 19 | 390.0 | 17.2% | 2.1% |
| XBI | 2025 | 19 | 390.0 | 16.1% | 2.0% |
| GDX | 2025 | 19 | 390.0 | 17.0% | 2.9% |

**Data-availability finding**: SPY/QQQ/IWM/XBI/GDX all show full 390
regular-session minutes per day in both windows. SOXX in January 2016
sometimes shows FEWER than 390 minutes/day (191-352 range) — i.e. real gaps
in the minute-bar series for this ticker that early, resolved by 2025 (full
390/day). This is consistent with SOXX's lower liquidity in 2016 and is a
genuine data-availability fact, not a fabricated one — every ticker/window
combination returned data (no `missing_tickers` from `AlpacaProvider`), so
the gap is intra-series thinness, not an outright missing ticker.

Last-30-minute dollar-volume share sits in the 13-20% range across tickers
and both windows — broadly consistent with (not proof of, just consistent
with) the Shum et al. framing of a meaningfully volume-concentrated closing
window, though this project's own number is a plain volume fact, not their
rebalancing-attributed estimate.

---

## Q5 — Flow scale (no return statistics)

Script: `flow_scale.py` (committed, reruns cleanly against the committed
`letf_universe.csv` and the scratchpad bar pickles from Q4 — re-fetch the
bars first if the scratchpad has been cleared). Output: `flow_scale.json`
(committed).

Methodology: `Σ AUM_i*(L_i^2-L_i)` per underlying (from Q2) × {1%, 2%} =
implied dollar rebalancing demand on a day with that return magnitude,
compared to the underlying ETF's own mean last-30-minute dollar volume in
the 2025-06-02..2025-06-27 window (from Q4's real bar data).

| Underlying | Implied demand @1% | Implied demand @2% | ETF last-30min $vol (mean) | Ratio @1% | Ratio @2% |
|---|---|---|---|---|---|
| S&P 500 (SPY) | $1.03B | $2.06B | $6.86B | 0.150x | 0.301x |
| Nasdaq-100 (QQQ) | $2.69B | $5.38B | $2.96B | 0.908x | 1.816x |
| Russell 2000 (IWM) | $34.7M | $69.4M | $1.11B | 0.031x | 0.062x |
| Semiconductors (SOXX) | $1.42B | $2.85B | $263M | **5.402x** | **10.805x** |
| Biotech (XBI) | $42.2M | $84.5M | $131M | 0.321x | 0.643x |
| Gold Miners (GDX) | $33.5M | $66.9M | $162M | 0.206x | 0.413x |

**This is a lower-bound comparison only** (ETF-only volume, per Shum et
al.'s own caution that real rebalancing trades constituents/swaps, not the
ETF itself — see Q1). No index-constituent closing-auction volume was
sourced in this pass (see "Things I could not verify").

**Headline finding**: for the S&P 500, Russell 2000, Biotech, and Gold
Miners underlyings, implied rebalancing demand even at a 2% day stays well
under the underlying ETF's own last-30-minute volume (ratios 0.06x-0.64x) —
a comfortable liquidity cushion by this lower-bound measure. For
**Nasdaq-100, the ratio crosses 1.0x at a 2% day** (implied demand exceeds
the ETF's own last-30-min volume), and for **Semiconductors the implied
demand is already 5.4x the ETF's own last-30-min volume at just a 1% day,
and nearly 11x at 2%** — meaning SOXX's own trading could not possibly
absorb the implied rebalancing flow; it would have to be absorbed elsewhere
(index constituents, swap-counterparty inventory, other liquidity). This
matches the qualitative pattern in Shum et al.'s SPY-only robustness check
(their ratios of 1,781%-8,646%, an even more extreme mismatch, for the S&P
500/SPY pairing using their older, smaller LETF-AUM sample) — i.e., **this
project's own numbers replicate the direction of Shum et al.'s finding using
current 2026 AUM data**, though the magnitudes differ (their sample is
2006-2011 AUM, much smaller than today's).

---

## Q6 — Novelty vs this repo

Grepped `app/services/research_lab/` for `letf|leveraged etf|closing
auction|last.*30.*min|aum` (case-insensitive). Findings:

- `rebalancing_pressure_timing.py` — an existing, DIFFERENT family (read in
  full): the Harvey-Mazzoleni-Melone (NBER WP 33554) 60/40 pension/sovereign-
  wealth/target-date-fund rebalancing signal. Its state variable is a
  simulated institutional portfolio's deviation from a 60% equity target; it
  trades a fixed SPY-vs-IEF spread. This is a genuinely different mechanism
  (institutional asset-allocation rebalancing, not LETF daily re-leveraging)
  and does not touch LETF AUM at all.
- `cross_sectional_index_removal.py` — mentions "closing auction" once, in
  the context of S&P 500 INDEX rebalance-driven forced selling at index
  additions/removals (a different, well-known mechanism, not LETF
  rebalancing).
- `cross_sectional_quarter_end_marking.py` — mentions "last hour" once, in
  the context of "marking the close" (Carhart/Kaniel/Musto/Reed), a fund-
  manager window-dressing mechanism, not LETF rebalancing.
- `cross_sectional_small_mid_cap.py` — mentions "leveraged ETF" once, but
  only as an incidental data-quality bug description (a defunct ticker `INT`
  whose price series turned out to belong to "Corgi Intc 2x Daily ETF" after
  a ticker-remapping error) — unrelated to the LETF-rebalancing mechanism.
- `cross_sectional_firesale_pressure.py` (Coval-Stafford) and
  `cross_sectional_nport_flow.py` (Lou 2012 FIT) — both use "AUM"/flow
  language, but both are MUTUAL FUND holdings-based flow-pressure measures
  built from SEC Form N-PORT bulk data, not LETF daily re-leveraging.

**Honest conclusion: this candidate is genuinely new to this repo.** No
existing family constructs an LETF-implied rebalancing-demand signal, uses
LETF AUM/shares-outstanding data, or targets the specific
last-30-minute/closing-auction LETF mechanism. The closest existing family
by surface theme (`rebalancing_pressure_timing.py`) is a different
mechanism, different state variable, different traded instrument, and
already explicitly documents (in its own module docstring) why it is not a
cross-sectional-universe family — the same reasoning would apply here.

---

## Things I could not verify

1. Cheng & Madhavan (2009)'s own paper text — never obtained directly (SSRN
   403, ResearchGate 403, one corrupt third-party PDF). Its formula and
   16.8%/50% MOC estimate are verified only via Shum et al.'s (2016)
   quotation/citation of it, not read first-hand.
2. Whether SOXX and Direxion's SOXL/SOXS reference index are literally the
   same index or two similar-but-distinct semiconductor indices — not
   resolved; flagged in Q2.
3. Whether ProShares' free historical NAV CSV is point-in-time-correct
   (i.e., not later-restated) vs. simply "today's historical record" — not
   checked; this project's own price/EDGAR stores distinguish "filed" vs.
   "first observed" dates and this ProShares file offers no such split.
4. Any free historical daily AUM/shares-outstanding source for Direxion
   funds — none found; direxion.com itself is unreachable to this session's
   automated fetch tooling (HTTP 403 throughout), which may itself be worth
   retrying with a headless browser (the `browser-automation` skill) before
   concluding no free source exists at all.
5. SEC N-PORT's AUM-field quality/timeliness as a Direxion backstop — not
   tested in this pass, only confirmed to exist and that this repo already
   has N-PORT ingestion code for a different purpose.
6. Whether a 2023-2025 academic paper on this mechanism exists BEYOND the
   EFMA "Of Seesaws and Swings" working paper found here — searches run in
   this pass did not find one, but the search was not exhaustive (no
   dedicated arXiv/SSRN new-papers sweep was run).
7. Index-constituent-level closing-auction dollar volume (a less
   conservative liquidity comparison than the ETF-only one used in Q5) —
   not sourced; would need either a paid data feed or a free-but-effortful
   constituent-by-constituent assembly, not attempted here.
8. Whether the EFMA paper's headline 2006-2020 magnitude (the sentence was
   truncated in my extraction) states a number comparable to Shum et al.'s
   33.85%-56.45%-of-mean-volatility figure — not re-extracted precisely;
   only the qualitative "still significant, COVID-confirmed" conclusion is
   verified.
9. Whether the "Of Seesaws and Swings" EFMA paper has since been published
   in a peer-reviewed journal (as of the 2024-Lisbon conference PDF fetched
   here, it reads as a still-unpublished working paper) — not checked
   further (e.g. no Google Scholar citation-chain check for a later
   published version).

---

## Feasibility verdict: **FEASIBLE-WITH-GAPS**

The mechanism itself is real, well-documented across a peer-reviewed paper
(Shum et al. 2016, full text read), a Federal Reserve working paper
(Ivanov-Lenkey 2014/2018, full text read), and a 2020-sample-extending 2024
conference working paper (Jain-Mishra-Pagano-Rodriguez, full text read),
plus a secondary-source-verified Cheng-Madhavan (2009) formula. This
project's own Alpaca minute-bar infrastructure already covers the needed
underlying ETFs at 1-minute granularity back to 2016 with no missing
tickers. This project's own Q5 computation, using real 2026 AUM and real
2025 volume data, independently reproduces the qualitative pattern Shum et
al. found (implied rebalancing demand can exceed the underlying ETF's own
trading capacity, most dramatically for the semiconductor/SOXX leg).

Gaps that keep this from a clean FEASIBLE:

- **AUM history**: only half the target universe (ProShares) has a
  confirmed free daily point-in-time AUM source reaching back to
  2008-2013; the other half (Direxion — all of semiconductors/biotech/gold-
  miners, plus one S&P 500 issuer family) has none confirmed. A historical
  backtest as currently scoped (6 underlyings) cannot be built without
  either (a) finding a Direxion source, (b) restricting to ProShares-only
  underlyings (S&P 500, Nasdaq-100, Russell 2000 — Nasdaq-100 keeps the
  largest Σ AUM*(L²−L) coefficient of the six, but restricting away
  Semiconductors drops the single most liquidity-stressed underlying found
  in Q5), or (c) building a forward-only point-in-time AUM store (like this
  project's existing price/EDGAR stores) and waiting for history to
  accumulate.
- **Cheng & Madhavan's own paper** was never read directly — a real citation
  gap that should be closed (retry via a different channel, e.g. a
  university library proxy or a headless-browser SSRN attempt) before any
  construction choice cites it as primary.
- **The 2023-2025 literature question is not conclusively answered** — the
  EFMA paper found is real and directly on-point, but is a still-unpublished
  working paper, and a broader sweep for other recent papers was not run.
- **Only a lower-bound (ETF-only) liquidity comparison was done for Q5** —
  Shum et al.'s own robustness check says this understates the true capacity
  constraint (real rebalancing hits constituents), which if anything makes
  the semiconductor-leg liquidity concern MORE serious, not less, but this
  was not independently confirmed with constituent-level data.

## What the orchestrator must decide

1. Whether to invest further effort re-obtaining Cheng & Madhavan (2009)
   directly (a university proxy, ResearchGate request-a-copy, or a
   headless-browser SSRN attempt) before treating its formula as verified-
   primary rather than verified-via-citation.
2. Whether to retry Direxion's site with a headless browser
   (`browser-automation` skill) to check whether the 403s are simple bot-
   detection (likely, given ProShares' JS-shell page also blocked plain
   `curl`) rather than a genuine absence of a historical-NAV download.
3. Whether to scope any eventual construction to ProShares-only underlyings
   (S&P 500, Nasdaq-100, Russell 2000) given the confirmed AUM history gap
   for Direxion — which would drop the most liquidity-stressed underlying
   (Semiconductors) found in this pass.
4. Whether the SEC N-PORT backstop is worth testing as a Direxion AUM
   source, given this project already has N-PORT ingestion code for a
   different purpose (mutual-fund flow families) — likely only useful for a
   monthly/lagged construction, not a daily one.
5. Per CLAUDE.md's paid-data-gap-deferral rule, this is logged as a finding,
   not a request to buy anything now — no paid-data decision is being asked
   for in this memo.
