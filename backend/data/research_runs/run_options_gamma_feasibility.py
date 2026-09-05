"""FEASIBILITY SCOPING ONLY -- options-dealer-gamma-hedging-flow candidate,
Bollen & Whaley (2004) / Barbon & Buraschi (2021, "Gamma Fragility").

This run builds NO gamma-exposure calculation, NO signal, and registers
nothing. It answers the question this project's own session memory flagged
as its WEAKEST-VERIFIED open item (`project_pending_paid_decisions.md`,
item 10, added 2026-09-06): "this was never given its own dedicated
feasibility-check task -- it was flagged 'typically not free at usable
granularity' straight out of the initial 22-paper literature review... a
much lower verification bar than this project normally requires." This run
gives it that dedicated check, mirroring run_tsmom_futures_feasibility.py and
run_nport_flow_feasibility.py in rigor and in refusing to build anything on
top of an unverified data claim.

CORRECTION TO THE TASK BRIEF THAT COMMISSIONED THIS RUN, found while trying
to verify it: the brief cited `backend/data/research_runs/
PENDING_PAID_DATA_DECISIONS.md` "item 5" as the source of the "yfinance live
option chains are real and usable near-ATM, but historical/point-in-time
chains are confirmed dead" claim. That REPO file has no such item -- its own
P1-P5 numbering is delisted-securities/borrow-rate/futures/N-PORT-PSF
material, unrelated to options data. The claim actually lives in this
project's Claude SESSION MEMORY, a separate, non-repo file also named
`project_pending_paid_decisions.md` (path:
~/.claude/projects/.../memory/project_pending_paid_decisions.md), at its own
item 5 ("Options/IV data vendor", logged 2026-08-27) and restated at item 10
(2026-09-06, this run's own trigger). Two differently-scoped files share a
name and the brief pointed at the wrong one. Flagged per this project's
standing "don't trust the paraphrase, verify" rule -- not chased further
since it does not change what needed verifying, only where the claim
actually lived.

============================================================================
THE QUESTIONS, AND THE SHORT ANSWERS THIS RUN MEASURED
============================================================================

Q1. WHAT DO THE TWO CITED PAPERS' CONSTRUCTIONS ACTUALLY NEED AS INPUT DATA?
    Answer, read from the papers themselves (not from memory or the
    literature review's one-line summary):

    Barbon & Buraschi (2021) -- PRIMARY SOURCE READ DIRECTLY. Downloaded the
    real working paper PDF (abarbon.com/assets/Barbon_Buraschi_2021_Gamma_
    Fragility.pdf, linked from the authors' own SSRN abstract page,
    papers.ssrn.com/sol3/papers.cfm?abstract_id=3725454; fetched and read
    2026-09-06). Their "Gamma Imbalance" is NOT the popular retail "GEX"
    heuristic (assume dealers are short every customer-bought contract, long
    every customer-sold one, and infer the sign from open interest alone).
    It is built from DIRECTLY OBSERVED broker-dealer-vs-customer trading
    volume, Eq.(1)/p.12, quoted verbatim:
        "Hedgers Inventory_j = BrokerDealers Inventory_j - Customers
         Inventory_j"
    gamma-weighted per stock (p.13, unnumbered display equation):
        "Hedgers Gamma_i = sum_{j written on i} Gamma_j x Hedgers Inventory_i"
    then scaled into a daily dollar-fraction-of-ADSV measure, Eq.(2)/p.13:
        "Gamma^IB_i(t) = Hedgers Gamma_i x S_i(t) / ADSV_i(t)"
    DATA THIS ACTUALLY NEEDS (p.10-11, "II. Data and Summary Statistics",
    Section A "Data Sources", quoted/paraphrased with page cites):
      (a) Option trading volume broken down BY COUNTERPARTY CATEGORY
          (broker/dealers, market makers, firms, private customers) from
          THREE NASDAQ OPTIONS EXCHANGES (ISE, GEMX, PHLX) -- proprietary
          exchange-licensed data, "opening and closing volume for
          broker/dealers, proprietary trading desks, and private customers,
          covering the period between January 2010 and May 2020" (p.10).
          The paper states these three exchanges cover only "a fraction
          between 10% and 20% of the worldwide dollar volume of option
          contracts" (p.10-11) and that the authors were, at the time of
          writing, "in the process of obtaining additional data from the
          CBOE C1 exchange" (p.11, footnote 8) -- i.e. even the paper's own
          authors needed a direct exchange data relationship, not a
          subscription product, to extend coverage.
      (b) OptionMetrics IvyDB -- "daily options prices, open interest, and
          greeks" (p.11), merged with (a) by contract.
      (c) CRSP and TAQ -- daily AND intraday returns/volume for the
          underlying (p.11); TAQ specifically for the intraday-momentum/
          reversal regressions, which use 5-minute and 60-minute return
          autocorrelations (p.2, p.6).
      (d) RavenPack News Analytics sentiment scores (p.11), used as a
          control, not as a gamma-imbalance input.
      Sample: "3491 U.S. individual stocks" plus "4 broad market indices"
      (p.11), 2010-2020.

    Bollen & Whaley (2004) -- SECONDARY-SOURCED, PRIMARY TEXT PAYWALLED.
    Stated plainly rather than glossed over: this run could NOT obtain the
    original Journal of Finance 59(2):711-753 full text (Wiley: paywalled;
    JSTOR: not attempted, same restriction expected; SSRN abstract page
    papers.ssrn.com/sol3/papers.cfm?abstract_id=319261: abstract only, PDF
    delivery returned HTTP 403 from this environment). What IS independently
    confirmed: (i) the paper is real -- the American Finance Association's
    own published errata for it (afajof.org/wp-content/uploads/files/
    clarifications/jf-bollen-whaley-errata.pdf, fetched and read directly)
    quotes a real corrected equation from the paper (its Eq.(9), the
    delta-hedged trading-strategy abnormal-return formula) with the exact
    citation "Bollen, Nicolas P.B., and Robert E. Whaley, 2004... Journal of
    Finance 59, 711-753"; (ii) its Net Buying Pressure (NBP) construction is
    described IDENTICALLY, independently, across multiple citing academic
    sources read directly in this run -- most explicitly an EFMA 2015
    conference paper (efmaefm.org/.../EFMA2015_0395_fullpaper.pdf, p.6,
    Section 2, fetched and read directly), which states verbatim: "The
    classical net buying pressure adopted in Bollen and Whaley (2004) and
    Kang and Park (2008) is defined by the difference between the number of
    buyer-motivated contracts and seller-motivated contracts... multiplied
    by the absolute value of the option's delta." A second, independently
    phrased WebSearch-sourced description (see NBP_SECONDARY_SOURCES below)
    adds the trade-classification rule: "buyer-motivated" = trade price
    ABOVE the bid-ask midpoint at execution; "seller-motivated" = below it
    -- the standard quote-midpoint trade-classification rule (same family as
    Lee-Ready). NBP is computed on a series-by-series (moneyness-bucketed)
    basis, DAILY.
    DATA THIS ACTUALLY NEEDS: per-trade classification (buyer- vs
    seller-motivated, from EXECUTION PRICE VS. PREVAILING QUOTE MIDPOINT AT
    THE TIME OF EACH TRADE) plus that trade's contract's delta -- i.e.
    TRADE-AND-QUOTE-LEVEL option market data, not an end-of-day open-interest
    snapshot. OptionMetrics IvyDB is the data source secondary sources
    consistently attribute to this and follow-on NBP papers (e.g. the
    Taiwan-options and VIX-options NBP papers found in this run's literature
    search).

    THE SHARED, LOAD-BEARING FINDING FROM BOTH: neither paper's actual
    measure is the popular retail "GEX" (Gamma Exposure) heuristic that
    assumes a fixed dealer-short/dealer-long sign convention from raw open
    interest alone. Both papers instead DIRECTLY OBSERVE which side of each
    trade the dealer was on -- Bollen-Whaley via trade-vs-quote
    classification, Barbon-Buraschi via exchange-reported counterparty-type
    volume. A free-data build of this candidate can get the OPEN INTEREST
    input (Q2 below) but NOT the sign-identification input either paper
    actually uses -- so a free build is necessarily a DEVIATION from both
    cited methods, not a degraded-but-equivalent version of either. See
    VERDICT.

Q2. CAN THIS PROJECT ACTUALLY GET OPTION OPEN-INTEREST-BY-STRIKE-AND-
    EXPIRATION FOR FREE, LIVE, RIGHT NOW? -- VERIFIED LIVE 2026-09-06,
    NOT ASSUMED FROM THE PRIOR NOTE'S PARAPHRASE.
    YES, from TWO INDEPENDENT FREE SOURCES -- a stronger free-data picture
    than either prior note (session-memory items 5 and 10) had established,
    since neither one had checked Alpaca for this use case.
      (1) yfinance's live Ticker.option_chain(): confirmed by direct call
          in this run (probe_yfinance_live_chains below) against SPY, AAPL,
          QQQ. Real columns returned for BOTH calls and puts: contractSymbol,
          lastTradeDate, strike, lastPrice, bid, ask, change, percentChange,
          volume, openInterest, impliedVolatility, inTheMoney, contractSize,
          currency. No API key, no paywall hit. Forward chain depth measured
          live: SPY 32 expirations (out to 2028-12-15), AAPL 22 (out to
          2028-12-15), QQQ 31 (out to 2028-12-15) -- a genuinely deep
          forward-looking chain, not just a near-dated snapshot.
      (2) Alpaca's TRADING API (not its market-data API), GET
          /v2/options/contracts -- NEWLY VERIFIED IN THIS RUN, not
          previously checked by either prior note. Confirmed live using
          THIS PROJECT'S OWN EXISTING Alpaca paper-trading credentials
          (the same ALPACA_API_KEY/ALPACA_API_SECRET this project's
          alpaca_provider.py already uses for equity bars -- no new
          credentials, no new cost, no options-trading approval needed for
          this read-only endpoint). Real response for SPY, quoted verbatim
          from one contract: {"symbol": "SPY260908C00500000", "strike_price":
          "500", "expiration_date": "2026-09-08", "type": "call",
          "open_interest": "12", "open_interest_date": "2026-09-03",
          "close_price": "265.27", "close_price_date": "2026-09-02"}.
      Both are LIVE-SNAPSHOT-ONLY (see Q3), and neither includes gamma or
      delta directly: yfinance additionally returns impliedVolatility per
      contract (from which a standard Black-Scholes gamma COULD be derived,
      not attempted here -- out of scope, see WHAT THIS RUN DOES NOT
      ESTABLISH); Alpaca's contracts endpoint returns neither IV nor greeks,
      and its separate market-data snapshot endpoint (checked live,
      probe_alpaca_market_data_snapshot below) returns dailyBar/latestQuote/
      latestTrade/minuteBar but NEITHER open_interest NOR greeks NOR IV --
      confirming those two Alpaca endpoints are NOT redundant with each
      other.

    RE-VERIFICATION OF THE EXISTING "HISTORICAL CHAINS ARE DEAD" CLAIM
    (session memory item 5) -- REPRODUCED LIVE, NOT TAKEN ON FAITH:
      Called yfinance on two real, definitely-expired option contract
      symbols (SPY200117C00300000, a Jan-2020 SPY 300 call; AAPL210115C0
      0100000, a Jan-2021 AAPL 100 call). Both returned yfinance's own
      "possibly delisted; no timezone found" warning and an HTTP 404
      ("Quote not found for symbol...") from Yahoo's own API, yielding
      ZERO PRICE ROWS in both cases. The prior claim is CONFIRMED, live,
      exactly as stated -- not merely repeated.

    UPDATE FREQUENCY, REASONED FROM VERIFIED, DOCUMENTED BEHAVIOR RATHER
    THAN GUESSED: open interest is NOT a real-time quantity FOR ANY VENDOR,
    free or paid -- it is a once-per-trading-day figure, computed overnight
    by OCC from the prior session's cleared positions and published before
    the next session opens (industry-standard OI mechanics, corroborated via
    WebSearch of OPRA's own definition of "current" vs. "delayed" data and
    by Alpaca's own contracts response above, which EXPLICITLY timestamps
    the figure one calendar day behind the pull date: pulled 2026-09-04/05,
    open_interest_date "2026-09-03"). Yahoo's quote/quote-derived data
    (bid/ask/last/IV) is separately documented as ~15-minutes-delayed
    (OPRA's standard delayed-data definition, WebSearch-corroborated, not
    directly confirmed against a real-time terminal in this run). NEITHER
    of these is a defect specific to this project's free sources -- a paid
    feed would show the same once-daily OI cadence, because that is what
    OI IS. Alpaca's explicit open_interest_date field is a genuine
    advantage over yfinance here: yfinance's option_chain carries no
    per-row "as of" date for openInterest at all (only lastTradeDate, a
    different field), so a yfinance-only build could not, by itself, prove
    when its own OI numbers were last valid without cross-checking against
    Alpaca or another source.

Q3. WHY THIS CANDIDATE IS STRUCTURALLY WORSE-SHAPED THAN N-PORT WAS, EVEN
    THOUGH ITS DATA IS FREER -- THE SINGLE MOST IMPORTANT FINDING OF THIS RUN.
    N-PORT's feasibility run (nport_flow_feasibility_2026-09-05) found ~7
    YEARS OF ALREADY-EXISTING, MINEABLE PUBLIC HISTORY sitting on SEC's
    servers TODAY -- a real backtest was buildable immediately from data
    that already exists. This candidate has NO ANALOGOUS ARCHIVE, free or
    found-paid, ANYWHERE this run could verify:
      * yfinance: confirmed dead for expired contracts (above) -- there is
        no historical option-chain archive behind it at any price.
      * Alpaca's /v2/options/contracts: returns ONLY the CURRENT
        open_interest and its CURRENT open_interest_date -- there is no
        historical parameter on this endpoint (checked: the response has no
        as-of-date range field, only a single current value per contract).
        Alpaca's separately-documented historical option BARS/QUOTES/TRADES
        product (docs.alpaca.markets/us/docs/historical-option-data) goes
        back only to February 2024 (WebSearch-corroborated from Alpaca's own
        docs) and, per that same page, does NOT carry historical open
        interest at all -- it is a bars/quotes/trades product, not an OI
        history.
      * OCC (theocc.com) and CBOE's free public pages: OCC's "Daily Open
        Interest" batch-download page and its underlying
        marketdata.theocc.com endpoint both returned blocking responses
        from this environment (WebFetch: HTTP 403 on the OCC page itself;
        a direct curl against a guessed marketdata.theocc.com/daily-open-
        interest?reportDate=...&format=csv URL returned HTTP 404 behind a
        Cloudflare challenge page) -- UNVERIFIED-FROM-HERE, the same honest
        label run_tsmom_futures_feasibility.py used for Nasdaq Data Link
        and Stooq, not a claim that OCC's data does not exist or is paid.
      * CBOE DataShop's "Option EOD Summary" product IS a real, historical,
        BY-STRIKE-AND-EXPIRATION open-interest product with a genuine
        self-serve purchase flow (datashop.cboe.com/option-eod-summary,
        fetched live 2026-09-06) -- "Available from January 2012 to
        present", fields including Strike/Expiration/Open Interest, with
        Greeks (Delta/Gamma/Theta/Vega/Rho, all "1545"-timestamped) sold as
        an optional add-on. This is a PAID, but self-serve and
        individually-purchasable, historical source -- structurally more
        like Norgate's TSMOM offering (a real product, a real cart, a
        real price once configured) than OptionMetrics (see below).
        Exact price NOT obtained: the cart requires selecting specific
        symbols/date ranges before a total appears ("Subtotal: $0.00" as
        configured), so no single headline number can be quoted honestly.
      * OptionMetrics IvyDB, the source BOTH cited papers actually used:
        confirmed (WebSearch, multiple university library pages: WRDS/
        Wharton, Imperial College, Princeton) to be distributed ONLY via
        institutional/university (typically WRDS) subscriptions, with NO
        publicly listed individual-researcher price tier found anywhere in
        this search. This is a materially different access barrier than
        Norgate's (TSMOM, P4) ~$270/yr self-serve consumer product: it is
        not merely "expensive", it appears to be NOT SOLD to an individual
        at any price this run could find.

    CONSEQUENCE: because there is no historical OI-by-strike archive this
    project can reach (free or paid) other than CBOE DataShop's
    unconfigured-price self-serve product, THIS CANDIDATE CANNOT BE
    BACKTESTED AT ALL on already-existing data via any FREE path. The only
    free path is FORWARD, PROSPECTIVE COLLECTION starting from today,
    accumulating a real sample one trading day at a time -- structurally
    the SAME shape as this project's forward_validation_service.py
    framework already exists to support, but starting from ZERO days of
    history rather than N-PORT's already-collected ~7 years.

Q4. HOW MUCH FORWARD-COLLECTED HISTORY WOULD BE ENOUGH? -- REASONED, NOT
    RESOLVED. This candidate is shaped like a market-timing/regime overlay
    on an index-level instrument (SPX/SPY), not a cross-sectional
    stock-picker -- the same reasoning shape run_tsmom_futures_feasibility.py
    used for its 15-effective-breadth floor, applied to a genuinely
    different problem (time-series regime persistence, not cross-sectional
    breadth). Considerations named, not settled:
      * Barbon-Buraschi's own result is INTRADAY (autocorrelation of 5- and
        60-minute returns) using a 2010-2020, ten-year, 3491-stock-plus-4-
        index panel (Q1 above) -- their statistical power comes from a huge
        CROSS-SECTION observed daily, not from many YEARS at a single name.
        A free build limited to a handful of index-level tickers (SPY/QQQ/
        IWM) forfeits that cross-sectional power entirely and would need to
        recover statistical power from TIME instead -- i.e. from spanning
        multiple distinct volatility/gamma regimes over calendar time, which
        is a slower substitute, not an equivalent one.
      * A DAILY-frequency signal (what free OI actually supports -- see Q2;
        yfinance/Alpaca cannot supply the intraday participant-classified
        data Barbon-Buraschi's own design needs) would need to span enough
        REGIME TRANSITIONS (episodes of persistently negative aggregate
        dealer gamma vs. persistently positive) to identify a real
        volatility/momentum-reversal relationship rather than one that is an
        artifact of a single episode. This project has NOT measured how
        often SPX-level aggregate dealer gamma actually flips sign in
        practice (that would itself require the historical data this run
        found is not freely available) -- so a specific number of REQUIRED
        regime transitions cannot be stated here; it is named as an open
        question, per this run's instructions, rather than guessed at.
      * This project's own DSR/mechanism-fidelity gate (CLAUDE.md Section 4)
        already requires DSR reported across multiple N assumptions and a
        preservation_score check -- both need a real sample of trials/
        returns to compute at all. A daily SPY-level series starting from
        zero days today would need, at an absolute floor, enough trading
        days to span at least one full high-vol/low-vol cycle (order of
        1-3 years, by analogy to this project's other regime-conditional
        work, e.g. vol_regime_timing.py's own multi-year windows) before
        ANY DSR number would be more than noise -- and substantially more
        (multiple such cycles) before a conservative-N DSR pass could be
        trusted per CLAUDE.md's two-tier verdict rule. This is a REASONED
        ESTIMATE, explicitly NOT a settled floor the way TSMOM's 15.0
        breadth number was -- flagged as an open question for whoever
        designs the real forward-validation registration, not resolved here.
      * Bottom line: a defensible DSR-gated verdict on this candidate is
        REALISTICALLY YEARS AWAY under the free-data path, starting from the
        day real collection begins -- not a "run it on existing data
        tonight" candidate the way N-PORT was.

VERDICT
----------------------------------------------------------------------------------------------------
FEASIBLE_FREE_WITH_NAMED_LIMITS -- for the DATA LAYER ONLY, and the named
limits are severe enough to dominate the practical answer. See VERDICT_CODE
and the full verdict section in the generated report.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# WORKTREE BINDING GUARD -- same pattern as run_tsmom_futures_feasibility.py
# and run_nport_flow_feasibility.py: this file must run against the code
# checked out in ITS OWN worktree, never silently against another checkout
# reached via a stale sys.path.
# ---------------------------------------------------------------------------
_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

import app

if Path(app.__file__).resolve().parent.parent != _BACKEND:
    raise SystemExit(
        f"REFUSING TO RUN: `app` resolved to {app.__file__}, which is not inside this worktree "
        f"({_BACKEND}). The measurement would have used another checkout's code."
    )

import httpx
import yfinance as yf

from app.config import settings

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s", stream=sys.stderr
)
log = logging.getLogger("options_gamma_feasibility")

RUN_DATE = "2026-09-06"
OUT_DIR = _BACKEND / "data" / "research_runs"
SAMPLES_DIR = OUT_DIR / "options_gamma_samples"
OUT_JSON = OUT_DIR / f"options_gamma_feasibility_{RUN_DATE}.json"
OUT_TXT = OUT_DIR / f"options_gamma_feasibility_{RUN_DATE}.txt"

YFINANCE_PROBE_TICKERS = ["SPY", "AAPL", "QQQ"]
YFINANCE_EXPIRED_CONTRACT_PROBES = ["SPY200117C00300000", "AAPL210115C00100000"]
ALPACA_PROBE_UNDERLYING = "SPY"

EXPECTED_YFINANCE_CHAIN_COLUMNS = {
    "contractSymbol", "lastTradeDate", "strike", "lastPrice", "bid", "ask",
    "change", "percentChange", "volume", "openInterest", "impliedVolatility",
    "inTheMoney", "contractSize", "currency",
}

# Alpaca /v2/options/contracts fields this run's verdict depends on being
# present. Checked explicitly rather than assumed present just because one
# live pull happened to have them.
EXPECTED_ALPACA_CONTRACT_FIELDS = {
    "symbol", "strike_price", "expiration_date", "type", "root_symbol",
    "underlying_symbol", "open_interest", "open_interest_date",
    "close_price", "close_price_date",
}

ALPACA_TRADING_BASE_URL_PAPER = "https://paper-api.alpaca.markets"
ALPACA_TRADING_BASE_URL_LIVE = "https://api.alpaca.markets"
ALPACA_DATA_BASE_URL = "https://data.alpaca.markets"


# ---------------------------------------------------------------------------
# CITATIONS -- held as constants so the report prints sourced text, not a
# paraphrase of it. See module docstring Q1 for full provenance/page cites.
# ---------------------------------------------------------------------------

BARBON_BURASCHI_CITE = (
    "Barbon, Andrea, and Andrea Buraschi, 2021, 'Gamma Fragility', working paper "
    "(University of St.Gallen / Imperial College London), SSRN 3725454, this version "
    "March 18 2021. PDF fetched directly 2026-09-06 from "
    "http://www.abarbon.com/assets/Barbon_Buraschi_2021_Gamma_Fragility.pdf "
    "(linked from the authors' own SSRN abstract page)."
)

BARBON_BURASCHI_EQ1 = "Hedgers Inventory_j = BrokerDealers Inventory_j - Customers Inventory_j"  # p.12, Eq.(1)

BARBON_BURASCHI_HEDGERS_GAMMA = "Hedgers Gamma_i = sum_{j written on i} Gamma_j x Hedgers Inventory_i"  # p.13, unnumbered

BARBON_BURASCHI_EQ2 = "Gamma^IB_i(t) = Hedgers Gamma_i x S_i(t) / ADSV_i(t)"  # p.13, Eq.(2)

BARBON_BURASCHI_DATA_SOURCES_QUOTE = (
    "Our empirical analysis is based on a number of data sources. To construct the "
    "inventory of option contracts held by broker/dealers, we use option trading data "
    "from three Nasdaq exchanges (ISE, GEMX, and PHLX). These datasets provide opening "
    "and closing volume for broker/dealers, proprietary trading desks, and private "
    "customers, covering the period between January 2010 and May 2020... We obtain data "
    "on daily options prices, open interest, and greeks from the IvyDB dataset provided "
    "by OptionMetrics... We merge the dataset obtained with the CRSP and TAQ databases "
    "by ticker to obtain information on daily and intra-daily returns and trading volume "
    "for each underlying assets. We collect data on market fundamentals from the News "
    "Analytics dataset by RavenPack..."
)  # p.10-11, Section II.A "Data Sources"

BARBON_BURASCHI_SAMPLE_QUOTE = (
    "The final sample includes four market indices (S&P 500, Dow Jones, Nasdaq 100 and "
    "Russell 2000) and 2700 individual U.S. equity stocks."
)  # p.11 -- NOTE: this is the REGRESSION sample after merging; the OPTIONS side alone
# is stated as "3491 U.S. individual stocks" plus 4 indices earlier on the same page,
# before the CRSP/TAQ merge narrows it -- both figures reported for completeness.

BARBON_BURASCHI_FOOTNOTE_COVERAGE = (
    "In this time window, these three exchanges account for a fraction between 10% and "
    "20% of the worldwide dollar volume of option contracts written on US equity "
    "securities. We are currently in the process of obtaining additional data from the "
    "CBOE C1 exchange. In that way, we would extend our coverage to almost 50% of the "
    "total dollar volume."
)  # p.10-11, footnote 8

# ---------------------------------------------------------------------------
# Bollen & Whaley (2004) -- SECONDARY-SOURCED, primary text paywalled from
# this environment. See module docstring Q1 for the full honesty disclosure.
# ---------------------------------------------------------------------------

BOLLEN_WHALEY_CITE = (
    "Bollen, Nicolas P.B., and Robert E. Whaley, 2004, 'Does Net Buying Pressure Affect "
    "the Shape of Implied Volatility Functions?', Journal of Finance 59(2):711-753. "
    "PRIMARY TEXT NOT OBTAINED (Wiley paywalled; SSRN abstract_id=319261 PDF delivery "
    "returned HTTP 403 from this environment 2026-09-06). Existence and one real equation "
    "(Eq. 9, unrelated to NBP) independently confirmed via the AFA's own published errata, "
    "afajof.org/wp-content/uploads/files/clarifications/jf-bollen-whaley-errata.pdf, "
    "fetched and read directly 2026-09-06."
)

# Quoted VERBATIM from a citing academic source that itself explicitly attributes
# and quotes Bollen & Whaley's own definition -- NOT this run's paraphrase.
BOLLEN_WHALEY_NBP_SECONDARY_QUOTE = (
    "The classical net buying pressure adopted in Bollen and Whaley (2004) and Kang and "
    "Park (2008) is defined by the difference between the number of buyer-motivated "
    "contracts and seller-motivated contracts. Herein, the difference is computed on a "
    "series-by-series basis, and is multiplied by the absolute value of the option's "
    "delta to express demand in index equivalent units."
)
BOLLEN_WHALEY_NBP_SECONDARY_SOURCE = (
    "EFMA 2015 Annual Meeting (Amsterdam) conference paper, 'Net buying pressure and "
    "option informed trading', Section 2 'Decompositions of net buying pressure', p.6, "
    "fetched and read directly 2026-09-06: "
    "efmaefm.org/0efmameetings/efma%20annual%20meetings/2015-Amsterdam/papers/"
    "EFMA2015_0395_fullpaper.pdf"
)

# A second, independently-worded description (WebSearch-aggregated summary of multiple
# sources, not a single direct quote) -- reported for corroboration, held to a lower
# evidentiary bar than the direct EFMA quote above and labeled as such.
BOLLEN_WHALEY_TRADE_CLASSIFICATION_WEBSEARCH_SUMMARY = (
    "Bollen and Whaley (2004) identify buyer-motivated options as trades executed at the "
    "price above the midpoint of prevailing bid and ask prices [i.e. a quote-midpoint "
    "trade-classification rule, same family as Lee-Ready]; seller-motivated trades are "
    "those executed below the midpoint."
)

OPTIONMETRICS_ACCESS_FINDING = (
    "WebSearch, 2026-09-06: OptionMetrics IvyDB -- the data source BOTH cited papers "
    "actually used -- is distributed via institutional/university subscription only "
    "(WRDS/Wharton wrds-www.wharton.upenn.edu, Imperial College London, Princeton "
    "University Library all listed as ACCESS POINTS, none as a public price list). No "
    "individually-purchasable price tier was found. This is a materially different access "
    "barrier than a self-serve consumer product (e.g. Norgate Data, this project's "
    "TSMOM/P4 finding) -- it appears not to be sold to an individual researcher at any "
    "price this search could find, not merely priced beyond a hobbyist budget."
)

CBOE_DATASHOP_FINDING = (
    "WebFetch, 2026-09-06, https://datashop.cboe.com/option-eod-summary: a real, "
    "self-serve, cart-based product ('Add to cart', 'Subtotal: $0.00' before "
    "configuration) with fields including Strike, Expiration, and Open Interest, "
    "'Available from January 2012 to present'. Greeks (Delta/Gamma/Theta/Vega/Rho, all "
    "'1545'-timestamped) are sold as an optional 'Calcs' add-on. Exact price NOT "
    "obtained -- cost depends on symbol/date-range selection made in the cart, and no "
    "total appears before that selection, so no single headline number can be honestly "
    "quoted. Structurally closer to Norgate's TSMOM offering (a real, individually "
    "purchasable product) than to OptionMetrics (institutional-only, see above)."
)

OCC_ACCESS_FINDING = (
    "WebFetch on https://www.theocc.com/market-data/market-data-reports/other-market-"
    "data-info/batch-processing/daily-open-interest returned HTTP 403. A direct curl "
    "against a guessed batch-download URL (marketdata.theocc.com/daily-open-interest?"
    "reportDate=20260904&format=csv) returned HTTP 404 behind a Cloudflare challenge "
    "page. UNVERIFIED-FROM-HERE -- the same honest label run_tsmom_futures_feasibility.py "
    "used for Nasdaq Data Link and Stooq's bot-protection interstitials -- NOT a claim "
    "that OCC's data does not exist or is paid; this environment simply could not verify "
    "it live."
)

OI_UPDATE_FREQUENCY_REASONING = (
    "Open interest is a once-per-trading-day figure for every vendor, free or paid -- "
    "OCC computes it overnight from the prior session's cleared positions. Corroborated "
    "two ways in this run: (1) WebSearch of OPRA's own 'current' (within the preceding "
    "15 minutes) vs. 'delayed' data definitions, which apply to quotes/trades, NOT to "
    "open interest, which OPRA and multiple vendor pages describe as inherently "
    "non-real-time; (2) DIRECT EMPIRICAL EVIDENCE from this run's own Alpaca pull: "
    "pulled 2026-09-04/05, every contract's own open_interest_date field read "
    "'2026-09-03' -- one calendar day behind the pull, exactly the expected overnight-"
    "computed lag. yfinance's option_chain carries NO equivalent per-row 'as of' date "
    "for its openInterest column (only lastTradeDate, a different field entirely), so a "
    "yfinance-only build could not, by itself, prove its own OI figures' freshness "
    "without cross-checking against a source like Alpaca that does timestamp it."
)


# ---------------------------------------------------------------------------
# PROBES -- real network calls. Each returns a JSON-serializable dict and
# ALSO writes one real captured sample under SAMPLES_DIR, mirroring
# run_nport_flow_feasibility.py's nport_samples/ convention, so the pytest
# suite can pin real captured evidence without a fresh network call.
# ---------------------------------------------------------------------------


def probe_yfinance_live_chains(tickers: list[str] = YFINANCE_PROBE_TICKERS) -> dict[str, Any]:
    """Q2: does yfinance's live option_chain() actually work, for real
    tickers, right now, with no key? Reports exact columns, expiration
    depth, and a few real rows -- not just 'yes it works'."""
    results: dict[str, Any] = {}
    for ticker_sym in tickers:
        entry: dict[str, Any] = {}
        t = yf.Ticker(ticker_sym)
        try:
            expirations = list(t.options)
        except Exception as exc:  # noqa: BLE001 -- a probe must record any failure mode, not crash
            entry["error"] = str(exc)
            results[ticker_sym] = entry
            log.warning("yfinance options list failed for %s: %s", ticker_sym, exc)
            continue

        entry["n_expirations"] = len(expirations)
        entry["expirations"] = expirations
        if not expirations:
            results[ticker_sym] = entry
            continue

        nearest = expirations[0]
        try:
            chain = t.option_chain(nearest)
            calls, puts = chain.calls, chain.puts
            entry["nearest_expiration"] = nearest
            entry["calls_columns"] = list(calls.columns)
            entry["puts_columns"] = list(puts.columns)
            entry["n_calls"] = len(calls)
            entry["n_puts"] = len(puts)
            entry["calls_sample"] = json.loads(calls.head(3).to_json(orient="records"))
            entry["puts_sample"] = json.loads(puts.head(3).to_json(orient="records"))
            entry["calls_open_interest_present_count"] = (
                int(calls["openInterest"].notna().sum()) if "openInterest" in calls.columns else 0
            )
        except Exception as exc:  # noqa: BLE001
            entry["chain_error"] = str(exc)
            log.warning("yfinance option_chain failed for %s/%s: %s", ticker_sym, nearest, exc)

        results[ticker_sym] = entry
        log.info("yfinance %s: %d expirations, nearest has %s calls / %s puts",
                  ticker_sym, entry.get("n_expirations", 0), entry.get("n_calls"), entry.get("n_puts"))

    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    (SAMPLES_DIR / "yfinance_live_chain_sample.json").write_text(json.dumps(results, indent=2, default=str))
    return results


def probe_yfinance_expired_contracts(
    symbols: list[str] = YFINANCE_EXPIRED_CONTRACT_PROBES,
) -> dict[str, Any]:
    """Q2 re-verification: does a definitely-expired option contract symbol
    actually return zero rows, reproduced live rather than trusted from the
    prior note's paraphrase."""
    results: dict[str, Any] = {}
    for sym in symbols:
        entry: dict[str, Any] = {}
        try:
            hist = yf.Ticker(sym).history(period="max")
            entry["n_rows"] = len(hist)
            entry["empty"] = bool(hist.empty)
        except Exception as exc:  # noqa: BLE001
            entry["exception"] = str(exc)
            entry["n_rows"] = 0
            entry["empty"] = True
        results[sym] = entry
        log.info("expired-contract probe %s: n_rows=%s", sym, entry.get("n_rows"))

    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    (SAMPLES_DIR / "yfinance_expired_contract_sample.json").write_text(json.dumps(results, indent=2, default=str))
    return results


def _alpaca_headers() -> dict[str, str]:
    return {"APCA-API-KEY-ID": settings.alpaca_api_key, "APCA-API-SECRET-KEY": settings.alpaca_api_secret}


def probe_alpaca_options_contracts(underlying: str = ALPACA_PROBE_UNDERLYING) -> dict[str, Any]:
    """Q2: does Alpaca's TRADING API (not its market-data API) expose
    per-contract open interest, using ONLY this project's existing
    credentials (never new ones), and how fresh is it?"""
    if not settings.alpaca_api_key or not settings.alpaca_api_secret:
        return {"skipped": True, "reason": "ALPACA_API_KEY/ALPACA_API_SECRET not configured in .env"}

    base = ALPACA_TRADING_BASE_URL_PAPER if settings.alpaca_paper_trading else ALPACA_TRADING_BASE_URL_LIVE
    result: dict[str, Any] = {"base_url_used": base}
    try:
        with httpx.Client(base_url=base, headers=_alpaca_headers(), timeout=30.0) as client:
            resp = client.get("/v2/options/contracts", params={"underlying_symbols": underlying, "limit": 10})
            result["status_code"] = resp.status_code
            body = resp.json()
            result["body"] = body
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
        log.warning("Alpaca options/contracts probe failed: %s", exc)
        return result

    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    (SAMPLES_DIR / "alpaca_options_contracts_sample.json").write_text(json.dumps(result, indent=2, default=str))
    log.info("Alpaca contracts probe: status=%s n_contracts=%s",
              result.get("status_code"), len(result.get("body", {}).get("option_contracts", [])))
    return result


def probe_alpaca_market_data_snapshot(underlying: str = ALPACA_PROBE_UNDERLYING) -> dict[str, Any]:
    """Confirms Alpaca's SEPARATE market-data snapshot endpoint does NOT
    duplicate the trading API's open_interest field (or carry greeks/IV) --
    the two Alpaca endpoints checked are not redundant with each other."""
    if not settings.alpaca_api_key or not settings.alpaca_api_secret:
        return {"skipped": True, "reason": "ALPACA_API_KEY/ALPACA_API_SECRET not configured in .env"}

    result: dict[str, Any] = {}
    try:
        with httpx.Client(base_url=ALPACA_DATA_BASE_URL, headers=_alpaca_headers(), timeout=30.0) as client:
            resp = client.get(f"/v1beta1/options/snapshots/{underlying}", params={"limit": 5})
            result["status_code"] = resp.status_code
            result["body"] = resp.json()
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
        log.warning("Alpaca market-data snapshot probe failed: %s", exc)
        return result

    snapshots = result.get("body", {}).get("snapshots", {})
    one = next(iter(snapshots.values()), {})
    result["fields_present_on_one_snapshot"] = sorted(one.keys())
    result["has_open_interest"] = "openInterest" in one or "open_interest" in one
    result["has_greeks"] = "greeks" in one

    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    (SAMPLES_DIR / "alpaca_market_data_snapshot_sample.json").write_text(json.dumps(result, indent=2, default=str))
    return result


def probe_occ_daily_open_interest_endpoint() -> dict[str, Any]:
    """Q3: attempt OCC's own documented free daily-open-interest batch
    download live. Reports the ACTUAL HTTP outcome, honestly labeled
    UNVERIFIED-FROM-HERE on a block rather than claimed unavailable."""
    urls_tried = [
        "https://marketdata.theocc.com/daily-open-interest?reportDate=20260904&format=csv",
    ]
    results = []
    for url in urls_tried:
        entry: dict[str, Any] = {"url": url}
        try:
            resp = httpx.get(url, timeout=20.0, headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True)
            entry["status_code"] = resp.status_code
            entry["content_type"] = resp.headers.get("content-type")
            entry["looks_blocked"] = resp.status_code in (403, 404, 503) or "cloudflare" in resp.text.lower()
        except Exception as exc:  # noqa: BLE001
            entry["error"] = str(exc)
        results.append(entry)
        log.info("OCC probe %s -> %s", url, entry.get("status_code", entry.get("error")))
    return {"attempts": results, "verdict": "UNVERIFIED_FROM_HERE"}


# ---------------------------------------------------------------------------
# SCHEMA/CLAIM CHECKS -- pure functions over already-fetched data, so the
# test suite can exercise them against a saved sample with NO network call.
# ---------------------------------------------------------------------------


def check_yfinance_chain_schema(calls_columns: list[str], puts_columns: list[str]) -> dict[str, Any]:
    calls_set, puts_set = set(calls_columns), set(puts_columns)
    return {
        "calls_has_expected_columns": EXPECTED_YFINANCE_CHAIN_COLUMNS.issubset(calls_set),
        "puts_has_expected_columns": EXPECTED_YFINANCE_CHAIN_COLUMNS.issubset(puts_set),
        "calls_has_open_interest": "openInterest" in calls_set,
        "calls_has_implied_volatility": "impliedVolatility" in calls_set,
        "puts_has_open_interest": "openInterest" in puts_set,
    }


def check_expired_contract_is_dead(n_rows: int) -> bool:
    return n_rows == 0


def check_alpaca_contract_schema(contract: dict[str, Any]) -> dict[str, Any]:
    keys = set(contract.keys())
    return {
        "has_expected_fields": EXPECTED_ALPACA_CONTRACT_FIELDS.issubset(keys),
        "has_open_interest": "open_interest" in keys,
        "has_open_interest_date": "open_interest_date" in keys,
        "open_interest_is_numeric_string": (
            bool(re.fullmatch(r"\d+", contract.get("open_interest", "")))
            if "open_interest" in contract
            else False
        ),
    }


VERDICT_CODE = "FEASIBLE_FREE_WITH_NAMED_LIMITS_DATA_LAYER_ONLY"


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------


def main() -> dict[str, Any]:
    log.info("=== Q2: yfinance live option_chain probe ===")
    yf_chains = probe_yfinance_live_chains()

    log.info("=== Q2 re-verification: expired-contract probe ===")
    yf_expired = probe_yfinance_expired_contracts()

    log.info("=== Q2: Alpaca trading-API options/contracts probe ===")
    alpaca_contracts = probe_alpaca_options_contracts()

    log.info("=== Alpaca market-data snapshot probe (non-redundancy check) ===")
    alpaca_snapshot = probe_alpaca_market_data_snapshot()

    log.info("=== Q3: OCC daily-open-interest endpoint probe ===")
    occ_probe = probe_occ_daily_open_interest_endpoint()

    # Schema checks against the just-fetched live data (same functions the
    # test suite exercises against saved samples).
    schema_checks: dict[str, Any] = {}
    for ticker_sym, entry in yf_chains.items():
        if "calls_columns" in entry:
            schema_checks[ticker_sym] = check_yfinance_chain_schema(entry["calls_columns"], entry["puts_columns"])

    expired_checks = {
        sym: check_expired_contract_is_dead(entry.get("n_rows", -1)) for sym, entry in yf_expired.items()
    }

    alpaca_contract_checks = None
    contracts_body = alpaca_contracts.get("body", {}) if isinstance(alpaca_contracts, dict) else {}
    contracts_list = contracts_body.get("option_contracts", []) if isinstance(contracts_body, dict) else []
    if contracts_list:
        alpaca_contract_checks = check_alpaca_contract_schema(contracts_list[0])

    result = {
        "run_date": RUN_DATE,
        "verdict_code": VERDICT_CODE,
        "citations": {
            "barbon_buraschi_2021": {
                "cite": BARBON_BURASCHI_CITE,
                "eq1_hedgers_inventory": BARBON_BURASCHI_EQ1,
                "hedgers_gamma": BARBON_BURASCHI_HEDGERS_GAMMA,
                "eq2_gamma_imbalance": BARBON_BURASCHI_EQ2,
                "data_sources_quote": BARBON_BURASCHI_DATA_SOURCES_QUOTE,
                "sample_quote": BARBON_BURASCHI_SAMPLE_QUOTE,
                "footnote_coverage": BARBON_BURASCHI_FOOTNOTE_COVERAGE,
            },
            "bollen_whaley_2004": {
                "cite": BOLLEN_WHALEY_CITE,
                "nbp_secondary_quote": BOLLEN_WHALEY_NBP_SECONDARY_QUOTE,
                "nbp_secondary_source": BOLLEN_WHALEY_NBP_SECONDARY_SOURCE,
                "trade_classification_websearch_summary": BOLLEN_WHALEY_TRADE_CLASSIFICATION_WEBSEARCH_SUMMARY,
            },
        },
        "data_access_findings": {
            "optionmetrics_access": OPTIONMETRICS_ACCESS_FINDING,
            "cboe_datashop": CBOE_DATASHOP_FINDING,
            "occ_access": OCC_ACCESS_FINDING,
            "oi_update_frequency_reasoning": OI_UPDATE_FREQUENCY_REASONING,
        },
        "probes": {
            "yfinance_live_chains": yf_chains,
            "yfinance_expired_contracts": yf_expired,
            "alpaca_options_contracts": alpaca_contracts,
            "alpaca_market_data_snapshot": alpaca_snapshot,
            "occ_daily_open_interest": occ_probe,
        },
        "schema_checks": {
            "yfinance_chain_schema_by_ticker": schema_checks,
            "expired_contracts_confirmed_dead": expired_checks,
            "alpaca_contract_schema": alpaca_contract_checks,
        },
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2, default=str))
    log.info("Wrote %s", OUT_JSON)
    return result


if __name__ == "__main__":
    main()
