# Addendum 01 to the protocol — measurement windows. Written before any number exists.

`PROTOCOL_2026-09-16.md` fixes the sample but not how much of each session is paginated. That
turns out to matter, and the decision is made here, in advance, on **data-volume grounds only**.
No measurement has been run. Nothing below was chosen with knowledge of any result.

## The problem

The vendor returns quote UPDATES. A Q1 name produces tens to a few thousand per session; a Q5 name
produces enough to need hundreds of pages. Full-session pagination is cheap where the question is
contested and infeasible where it is not.

The tempting fix — paginate Q5 until a page cap and stop — is **biased**, and in the direction that
matters: pagination is chronological, so a cap keeps the opening minutes and discards the rest, and
spreads are widest at the open. That would inflate the anchor and make the section 5 validation
gate easier to fail for a reason having nothing to do with the pipeline being wrong.

## The decision

Two statistics, both computed, both reported.

| | window | buckets | role |
|---|---|---|---|
| **A** | full session 14:30:00–21:00:00Z, full pagination | **Q1–Q3** | primary. Parts 1, 2 and 3 all use it. |
| **B** | 17:00:00–17:05:00Z, full pagination | **all five** | like-for-like comparison, and the section 5 gate |

Statistic B is a fixed five-minute midday window, chosen because it is away from both the opening
and closing auctions and costs the same number of requests regardless of liquidity. **The section 5
gate is evaluated on B**, so the gate compares Q5 against published figures using the same
construction applied to every other bucket.

B is also reported for Q1–Q3, next to A. If A and B disagree materially for the same names, that
is itself a finding about time-of-day and is reported as one rather than resolved by picking the
convenient window.

## What this costs

Parts 2 and 3 — resting-order fills and fill selection — need the session's running minimum ask and
maximum bid, so they need window A. **They are therefore computed for Q1–Q3 only.** Q4 and Q5
contribute the calibration anchor and nothing else, which is all the protocol assigned them.

## Carry-forward, restated because it is easy to get wrong

Window B is five minutes. An illiquid name may have **zero** quote updates inside it — KOSS had
none in the 15:00–15:01 window on 2026-09-11 while being continuously quoted. The NBBO at 17:00:00Z
is the last update at or before it, which may be hours earlier. The collector therefore requests a
lookback (from 14:30:00Z) to seed the state before the window opens, and a ticker-day whose state
cannot be seeded at all is recorded as `no_quote_state` and excluded from B with the count
reported, never silently dropped.
