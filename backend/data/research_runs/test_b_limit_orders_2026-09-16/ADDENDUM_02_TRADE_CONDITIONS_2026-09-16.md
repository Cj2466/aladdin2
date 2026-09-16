# Addendum 02 — trade conditions must be filtered, and the filter is sourced. Before any result.

## How this was found

`PROTOCOL_2026-09-16.md` section 5 requires the pipeline to reproduce published large-cap spreads
before any other number is believed. Run on four names whose answer is known, on 2026-09-11,
midday window:

| symbol | quoted half | effective half | verdict |
|---|---|---|---|
| AAPL | 0.50 bp | 0.34 bp | sane |
| MSFT | 0.89 bp | 0.43 bp | sane |
| **SPY** | **0.10 bp** | **88.0 bp** | **impossible** |

A 0.10 bp quoted market cannot produce an 88 bp effective spread. The gate caught it before a
single production number existed, which is the entire reason the gate is in the protocol.

**Cause**, found by inspection rather than guessed: three off-exchange prints on exchange `D`
(FINRA TRF) at **757.8492** against a market of 765.63 / 765.64 — **102.5 bp away** — for 916,250,
125,583 and 125,583 shares. Their condition codes:

```
2026-09-11T17:03:41.853  757.8492  916,250  x=D  c=[' ','4','B']
2026-09-11T17:02:02.641  757.8492  125,583  x=D  c=[' ','7','V']
2026-09-11T17:02:19.663  757.8492  125,583  x=D  c=[' ','7','V']
```

`4` derivatively priced, `B` average price, `7` qualified contingent, `V` contingent. **None of
these is an execution against the displayed quote.** Share-weighted, three prints carried the
statistic.

Note what this is: it is exactly the "trade-condition-flagged prints" that Test A's result listed
as a paid-data gap. We have them, and we do not merely have them — we **need** them, because
without the flags the effective spread is meaningless.

## The filter, from the primary specification

Source: **Consolidated Tape System (CTS) Output Multicast Interface Specification, November 6,
2015, page 118**, section `SALE CONDITION — 'OPEN', 'LAST', 'HIGH', 'LOW' CALCULATIONS`, published
by the CTA Plan
([nyse.com](https://www.nyse.com/publicdocs/ctaplan/notifications/trader-update/cts_output_spec_v78_11062015.pdf)).
The table states, verbatim, for the CONSOLIDATED LAST column:

```
CODE  SALE CONDITION                          LAST
@     REGULAR TRADE                           YES
B     AVERAGE PRICE TRADE                     NO
C     CASH TRADE (Same Day Clearing)          NO
E     AUTOMATIC EXECUTION                     YES
F     INTERMARKET SWEEP ORDER                 YES
H     PRICE VARIATION TRADE                   NO
I     ODD LOT TRADE                           NO
K     RULE 127 / RULE 155                     YES
L     SOLD LAST (Late Reporting)              #3
M     MARKET CENTER OFFICIAL CLOSE            NO
N     NEXT DAY TRADE                          NO
O     MARKET CENTER OPENING TRADE             #1
P     PRIOR REFERENCE PRICE                   #2
Q     MARKET CENTER OFFICIAL OPEN             NO
R     SELLER                                  NO
T     EXTENDED HOURS TRADE                    NO
U     EXTENDED HOURS SOLD (Out of Sequence)   NO
V     CONTINGENT TRADE                        NO
X     CROSS TRADE                             YES
Z     SOLD (Out of Sequence)                  #2
4     DERIVATIVELY PRICED                     #2
5     MARKET CENTER REOPENING TRADE           YES
6     MARKET CENTER CLOSING TRADE             YES
7     QUALIFIED CONTINGENT TRADE              NO
9     CORRECTED CONSOLIDATED CLOSE PRICE      YES
```

**Exclusion set used here** — every code above whose LAST is `NO` or footnoted, plus the auction
and reopening prints (`5`, `6`, `9`, and `O`/`Q`/`M`), which are eligible for LAST but are not
executions against a continuous two-sided quote:

`B C H L M N O P Q R T U V Z 4 5 6 7 8 9`

A trade is dropped if ANY of its condition codes is in that set. Blank bytes are category fillers,
not conditions, and are ignored. Kept: blank, `@`, `E`, `F`, `K`, `X`, and `I` under F2 below.

## Two filters, both reported, neither chosen after seeing a result

- **F1 strict** — last-sale-eligible continuous trades only. Excludes odd lots (`I`). This is the
  construction closest to the literature our anchor figures come from.
- **F2 retail** — F1 **plus odd lots**. Odd lots are excluded from the tape's LAST for a tape
  reason (a 3-share print should not set the consolidated last price), **not** because they are
  unrepresentative executions. We are a small trader; an odd lot is an execution we would actually
  receive. On the SPY sample, odd lots were 2,064 of 3,862 prints — more than half.

**F2 is the primary** for every number that answers "what would this cost us". F1 is reported
beside it, and against the anchor. **If F1 and F2 disagree materially, that is a finding about who
the measurement is for, and it is reported, not resolved by preference.**

## Honest note on scope

This filter is applied to the EFFECTIVE spread, which is computed from trades. The time-weighted
QUOTED spread is computed from quotes and is unaffected — the SPY quoted figure of 0.10 bp was
correct all along. Only the trade-based statistic was broken.
