# M3b -- SET's daily files: what is downloadable free without SETSMART

Measured 2026-09-12 by fetching each page (curl for a static check, then a
headless browser -- `browser-automation` skill, patchright/Playwright -- to
render the client-side data and operate the UI). No SETSMART login was
attempted or paid for. Raw pages committed under `m3_sources/` with SHA-256 in
`m3_SOURCES.md`.

| item | URL tried | HTTP status | content type | history available? | extract |
|---|---|---|---|---|---|
| Daily investor-type trading breakdown (local retail / foreign / institution / proprietary) | `https://www.set.or.th/en/market/statistics/investor-type` | 200 (JS-rendered data) | HTML table, client-rendered, no API key | **Aggregate only, 3 fixed windows: latest trading day, month-to-date, year-to-date.** No date picker was found on this page at all -- there is no way, through this page's UI, to request an arbitrary past day or download a daily time series. Values are for the whole SET (or mai) market, NOT broken out by stock. | `m3_sources/investor_type.html` |
| Daily NVDR trading by stock | `https://www.set.or.th/en/market/statistics/nvdr/trading-by-stock` | 200 (JS-rendered data) | HTML table, client-rendered, per-symbol rows (buy/sell/net volume and value), "Export Excel" button present, no API key | **Single-day selector, read-only text input** (`<input readonly placeholder="Select date">`). The calendar popup that opens is a v-calendar instance whose header (`.vc-header`) contains only a month/year title (`"September 2026"`) with **no navigation-arrow elements anywhere in the DOM** (confirmed by dumping the full `.vc-container` HTML and by a screenshot -- see `m3_sources/`); days outside the currently-displayed month are simply absent from the calendar grid, and only ~10 recent trading days within the current month are enabled (`aria-disabled="false"`), all others `disabled`. Because the input is `readonly`, typing a date directly is also not possible. **Could not drive this control to a date before the current month within the time budget** -- keyboard shortcuts described in the widget's own `data-helptext` (PageUp/PageDown for month, Alt+PageUp/PageDown for year) were tried and had no visible effect. Practical conclusion: **this page, as its free UI currently renders, exposes at most the current month's trading days per stock; no confirmed way to pull an arbitrary historical day for free.** This is a measured UI limitation, not a proof that the underlying data does not exist server-side -- only that this agent could not retrieve it through the public page within budget. | `m3_sources/nvdr_trading_by_stock.html` |
| Daily short-selling by stock | `https://www.set.or.th/en/market/statistics/short-sales/total-short-sales` | 200 (JS-rendered data) | HTML table, client-rendered, per-symbol rows (short-sale volume/value and outstanding short position), "Export Excel" button present, no API key | **Date-RANGE selector** (separate "Start date" / "End date" text inputs, both defaulting to today), with a page-level label reading **"Back to 6 months"** next to the range control -- i.e. SET's own UI advertises up to 6 months of lookback for this table. However, the same calendar-widget limitation as above applied: no navigation-arrow elements were found in the DOM, so this agent could not click, keyboard-navigate, or otherwise drive the calendar back to a month before the current one within the time budget. **The "6 months" figure is SET's own stated capability (page text), not independently confirmed by successfully pulling an out-of-month day.** | `m3_sources/short_sales_total.html` |
| Program trading value | `https://www.set.or.th/en/market/statistics/program-trading-value` | 200 (JS-rendered data) | HTML table, client-rendered, market-wide aggregate (not by stock) | Single-day selector, same "Back to 6 months" label as short sales, same unconfirmed-navigation caveat. | `m3_sources/program_trading_value.html` |

## What this means, honestly

- All four pages are free, require no API key or SETSMART login, and return
  real current-day data through a headless browser.
- **Per-stock daily granularity exists for two of the four** (NVDR trading,
  short sales) -- the other two (investor-type, program trading) are
  market-wide aggregates only.
- **Historical depth could not be confirmed for any of the four beyond the
  currently displayed calendar month.** Two pages (short sales, program
  trading) carry SET's own "Back to 6 months" label, which is a real
  disclosed capability of the tool as SET describes it, but this agent was
  unable to operate the date-picker's month navigation (no arrow controls
  exist in the rendered DOM; keyboard shortcuts named in the widget's own
  help text had no effect; the date inputs are `readonly` so direct typing is
  blocked) within the ~1.5h budget. **This is recorded as NOT VERIFIED,
  not as a confirmed 6-month history** -- a future attempt should try either
  a real (non-headless) browser interactively, or find the underlying data
  API by inspecting the page's JS bundle rather than the rendered accessibility
  tree.
- SET's official real-time/historical data PRODUCT (`end-of-day` service,
  `m3_sources/end_of_day_service.html`) is a separate, vendor-distributed
  paid feed (contact "Information Services Department", sample files/data
  models linked per product but no self-serve download or pricing shown on
  the page) -- distinct from the free website pages above. This is the
  **candidate paid-data gap P10**: a proper multi-year, per-stock daily
  investor-type / NVDR-flow / short-selling panel is a SETSMART or
  SET-vendor-feed product, not obtainable free at the depth this project would
  need for a cross-sectional backtest. (Per the brief, this is logged here for
  the orchestrator to add to `PENDING_PAID_DATA_DECISIONS.md` -- this agent
  did not edit that file and did not price or purchase anything.)

## SET's published policy on data use

`m3_sources/market_data_policy.html` ("SET Information Services Guideline")
links a **Non-Display Usage Policy** (`m3_sources/non_display_usage.pdf`,
effective 1 Jan 2017). Read directly (pp. 1-2): it defines "Non-Display Usage"
as machine use of SET's equity market data (explicitly naming "Automated
Trading Application[s]" -- program trading, market making, order routing,
execution algorithms) and requires a **paid "Subscriber" contract with SET**
("Firm" or "Subscriber Group") before such use. On its face this document
addresses **subscribers to SET's own paid FEED product** ("SET FEED (Equity)
members"), not the free public website -- this agent did not find equivalent
non-display-usage language addressed specifically at set.or.th website
scraping.

Separately, `m3_sources/terms.html` (Terms and Conditions of Use, section 1.3,
verbatim from the static SSR HTML) states: *"you may only view, download,
upload the Contents and print any document of the Contents for your own
personal and non-commercial use. You may not copy, store or download ...
for the purpose in transmit, transfer, perform, broadcast, publish,
reproduce, create a derivative work from, display, distribute, sell,
license, rent, lease or otherwise transfer any of Contents to any third
person whether for direct commercial or any gain or otherwise without the
prior written permission from SET Group."* This is a real, general
website-terms restriction to "personal and non-commercial use" that this
agent surfaces here without interpreting further -- whether scraping these
pages for this project's research (non-live, no capital deployed) falls
inside or outside "personal and non-commercial use" is a legal/policy
question for the project owner, not something this agent decided or acted on.
