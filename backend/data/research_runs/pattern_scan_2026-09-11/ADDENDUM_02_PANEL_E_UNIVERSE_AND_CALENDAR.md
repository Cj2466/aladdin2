# ADDENDUM 02 — Panel E's universe and bar calendar, and a disclosed timing probe

Dated 2026-09-11, written by the builder (Fable 5.1). Amends PREREGISTRATION.md §2 per its §8.
No threshold, k, window, draw count, top-20 count or gate is changed.

---

## 1. The problem: §2's operational rule contradicts itself on this store

§2 defines Panel E as "**(US equities, daily)** every ticker in the shared point-in-time price
store (`data/price_store/v1`, 1,593 files on 2026-09-11) with ≥ 1,000 daily rows". Measured on the
actual store today, that rule cannot be executed as written:

* 73 of the store's tickers are spot crypto pairs (`<COIN>-USD`), which quote **every calendar
  day**. Taking the union of all tickers' dates as the panel's bar index therefore produces a
  ~3,901-bar CALENDAR-day index over 2016-01-04 … 2026-09-08, not the ~2,685-bar equity trading
  calendar.
* Under §2's own "bars with a missing predecessor are dropped" rule, that is fatal rather than
  merely untidy: on a calendar-day index every Monday's predecessor bar is a Sunday, on which no
  equity has a close, so **every equity return in the panel would be dropped**. The rule as written
  would leave Panel E containing only the crypto names that §2 puts in Panel C.

## 2. Resolution (two parts, both declared before the scan)

**(a) Universe.** Panel E is every ticker file in the store with ≥ 1,000 stored daily rows and at
least one row inside the sample window, EXCLUDING the continuous-calendar instruments identified by
the store's own `price_store.trades_every_calendar_day` (the `-USD` suffix; the store module
documents that all 73 such tickers are crypto and that no five-day symbol carries that suffix).
That is **1,437 names**. Nothing else is filtered: under §2's literal "every ticker in the store"
rule, 17 FX quotes (`...=X`) and 7 index symbols (`^GVZ`, `^MOVE`, `^OVX`, …) REMAIN in Panel E.
They are not US equities and two of them are not tradable at all; they are kept because the
pre-registration's rule is "every ticker", they are 24 of 1,437 names (1.7%), and dropping them
would be a post-hoc universe choice. This is disclosed, not hidden, and is listed again in the run
report's limits.

**(b) Bar calendar.** A date is a Panel E bar iff the number of names with a close on it is at
least 10% of the median daily live-name count. The data separates completely at this rule, so it is
a boundary between two clearly distinct populations rather than a tuned threshold: of the 2,783
dates the 1,437 names span, **2,685 carry 1,300–1,431 names and 98 carry 17 or fewer** — the 98 are
US market holidays on which only the FX quotes print. Median live count is 1,390; the rule cuts at
139, an order of magnitude away from either population. Panel E is therefore 2,685 bars ×
1,437 names, which is the US equity trading calendar for the declared window.

Panel C needs no such rule: the 25 Binance spot files share one continuous hourly index, 61,405
bars in the declared window, every bar carrying 14–25 of the 25 symbols.

## 3. Disclosed: a timing probe produced real-arm numbers before this file was committed

Honesty requires recording this rather than tidying it away. While sizing the run (to check §8's
"if the equity panel is too slow" clause), the builder ran one `run_discovery` call on the REAL
Panel E under the rules in §2 above, purely to time it. It returned in 0.7 s and printed:

| horizon | measurable | N3 | N4 | Tmax | formation bars |
|---|---|---|---|---|---|
| h = 1 | 117 | 0 | 0 | 2.884 | 1,761 |
| h = 5 | 117 | 3 | 0 | 3.273 | 1,757 |

So a real-arm number existed before this addendum was committed, which is the opposite of the order
§8 asks for. Two things make the record clean anyway, and both are checkable:

1. **Nothing in §2 above was decided after seeing those numbers.** The universe rule and the
   calendar rule were fixed by the preceding measurement, which counted tickers, dates and live
   names and computed no return, no t-statistic and no pattern. The probe then simply applied them.
2. **Nothing in §2 above is tunable toward a result.** (a) is a binary "does this instrument quote
   on weekends" test delegated to an existing module, and (b) cuts a 17-vs-1,300 gap.

The probe's numbers are reproduced above so they can be compared against the committed run: if the
run report's Panel E discovery figures differ from these, something changed between the probe and
the run and must be explained. They are not the experiment's result — the gates need the placebo
draws, which the probe did not compute.

---

Builder: Claude Fable 5.1, 2026-09-11.
