# "Did the unsourced cost default make us throw away a good strategy?" — searched, and the answer is NO where it can be measured (2026-09-12)

Owner's instruction after the cost-constant audit: go and find the strategies we may have
discarded wrongly. This is that search, by the orchestrator against the real DB (3,235 trial rows,
55 families), not a re-reading of memos.

## What the database actually carries
`total_cost_drag` in 47 of 55 families, `total_turnover` in 35, an explicit `cost_arm` label in 11,
and — decisively — BOTH a gross and a net Sharpe in **6** families. Only those 6 allow the question
to be answered without re-running anything.

## The six, read directly

| family | best gross | best net | Sharpe eaten by cost | what cost it charged | sourced? |
|---|---|---|---|---|---|
| ofi_crypto | 1.492 (0.745 at the row with net 0.462) | 0.462 | ~0.28 | 10 bp + Binance taker 5 bp | YES — real exchange fees |
| eigenportfolio_statarb | 0.620 | 0.093 | 0.53 | 5 bp one-way | **YES — the paper's own ε = 0.0005** (Avellaneda-Lee §5), not the unsourced default |
| intraday_momentum_spy | 0.610 | 0.101 | 0.51 | **1.0 bp** one-way | YES — deliberately 7.2× SPY's own quoted half-spread, a disclosed safety margin |
| letf_rebalancing_eod | 0.579 | 0.104 | 0.48 | **1.0 bp** one-way | YES — fixed by its pre-registration §4.2 |
| dividend_month_premium | 0.447 | −0.272 | 0.72 | default | gross is already below the 0.50 floor — dead at ANY cost |
| earnings_announcement_premium | 0.202 | −0.337 | 0.54 | default | same — dead at zero cost |

## The finding, stated against my own earlier speculation
I suggested the unsourced 5 bp default might have buried good strategies. **Among every family where
it can actually be checked, it did not.** The two families that lost the most Sharpe to cost
(intraday_momentum_spy, letf_rebalancing_eod) were charged **1 bp, not 5** — a deliberately
conservative margin chosen and disclosed in their own pre-registrations — and eigenportfolio was
charged the source paper's own number. The two families that used the plain default had gross
Sharpes of 0.45 and 0.20, below the 0.50 screening floor before any cost at all.

Separately, and worth keeping: neither of those two ETF families was declined ON COST anyway.
`intraday_momentum_spy` was declined UNDERPOWERED (power 0.014 to detect its own source's claim) and
`letf_rebalancing_eod` failed its mechanism gate with the wrong sign (t = −1.155). A cheaper cost
assumption changes neither verdict.

## What IS real, and is the durable lesson
High-turnover families lose roughly half a Sharpe point to trading costs **at any defensible rate** —
0.48 to 0.53 here, even at 1 bp — because a strategy that turns over daily pays the spread ~500 times
a year. That is economics, not a modelling error, and it is the strongest argument for the
break-even-cost number A2 will compute: for these families the question was never "is 5 bp right"
but "does the edge survive 500 crossings of any spread at all".

## The honest limit of this search
41 of 55 families store no gross Sharpe, so their cost sensitivity cannot be read from the database
at all. Answering for them requires re-running each at zero cost — cheap per family, but it is a
real run, and under this project's rules it needs its arms declared before it starts. Logged as an
open item rather than done here.
