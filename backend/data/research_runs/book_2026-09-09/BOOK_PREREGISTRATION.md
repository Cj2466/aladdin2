# The pre-registered book — pre-registration (written before any gate was run)

Date: 2026-09-09. Author: Claude (Fable 5.1) for the project owner, who
approved "do everything in order": (1) Dormant re-scorer coverage → (2) this
→ (3) a $0 high-claimed-Sharpe candidate → (4) leftovers.

## 1. Why a book, and why it is not the rejected "option D"

Measured today (`intraday_data_scoping_2026-09-09`, re-derived): at a fixed
annualized Sharpe, years-to-detect is invariant to sampling frequency; a true
0.5 needs ~222 years, a true 1.0 ~14, a true 2.0 ~2. No single micro-edge of
the size this project hunts is certifiable in a working lifetime. The only
honest lever that raises an ANNUALIZED Sharpe is combining independent
edges: M members with per-member Sharpe s and pairwise correlation ρ have a
combined Sharpe of roughly s·√(M / (1 + (M−1)ρ)) — 30 members at 0.3 with
ρ = 0.05 give ≈ 1.1, which is certifiable in ~12 years. This is the
"many small micro-edges, law of large numbers" thesis in CLAUDE.md §7,
stated as arithmetic.

Option D (portfolio-level *admission*) was rejected this morning because
choosing the members IN SAMPLE lets uncorrelated noise raise the in-sample
portfolio Sharpe with no edge behind it, and no portfolio-level
multiple-testing correction exists. The book avoids that in one move:
**membership is fixed by rule before any book return exists, and the book
is scored only on data after that date.** There is no member selection on
the scored segment, hence nothing to deflate, hence N = 1 — the same logic
that makes the Dormant extension test honest.

## 2. Membership rule (mechanical, no judgement at scoring time)

* Members = every frozen spec that is in **Active** (a forward registration)
  or **Dormant** (a manifest entry with `rescorable = true` and
  `pit_ok = true`) on a **membership date**.
* Membership dates: the book's inception date, then each anniversary. A spec
  entering Dormant/Active between membership dates joins at the next one;
  its returns before joining are not part of the book.
* A member leaves only when it is **Closed by mechanism evidence**; it does
  not leave for a bad return, a failed look, or any statistic. (A member that
  leaves keeps its history in the book up to its exit date.)
* Weight: equal, 1/M_t over the members that have a realized net return on
  date t; members with no return that day (a monthly family between
  formations, a 252-day family on a crypto calendar day) are simply absent
  that day and the weights renormalize. No volatility scaling, no
  optimisation — anything estimated from returns would be a selection.
* Calendar: the union of members' calendars; `periods_per_year` for the
  book's PSR is 252 (a crypto member contributes on its own days; the
  book's realized-day count is what PSR uses, so this is a labelling
  choice for the annualized Sharpe display, not a statistical input).

## 3. Statistic, look schedule, boundary — identical to the Dormant pool

    PSR_book = probabilistic_sharpe_ratio(SR_book, 0, n_book, skew, kurt)

on the book's realized net daily returns strictly after inception, N = 1,
looks at k × 252 realized book days (k ≤ 10), promotion iff
PSR_book ≥ C_K[bucket] with the Dormant boundaries (LOW 0.99397 /
HIGH 0.99894, `dormant_pool.C_K`), bucket from the book's lag-1
autocorrelation measured on the members' PRE-inception composite (data that
exists before any scored day). Promotion = the book gets its own Active
forward-tracking slot. **Not** capital: the capital bar is unchanged.

The daily-Sharpe-of-the-composite is also the statistic option C was
rejected in favour of, so nothing new is introduced.

## 4. Gates (pass criteria fixed here, before running)

The book's daily return is an average of member returns, so its null
distribution is at least as well-behaved as a single member's; the LOW
boundary was calibrated for i.i.d. normal / t(4) / AR(1) 0.1 members. The
gates therefore ask two different questions from the Dormant ones:

* **GB1 (size with correlated null members):** M ∈ {10, 30, 50} members with
  true Sharpe 0 and pairwise correlation ρ ∈ {0, 0.05, 0.2, 0.5} (one
  common factor), K_MAX looks, LOW boundary → per-book false promotion
  ≤ 0.05 + 2·se. If any (M, ρ) cell fails, the boundary is recalibrated on
  the worst cell and everything re-run, and that is recorded.
* **GB2 (size under the membership rule's one degree of freedom):** members
  join at membership dates *after* being observed as promising elsewhere
  (they were, after all, selected by an in-sample screen once). Simulate
  the selection: from a pool of 200 null specs, admit the 30 with the best
  in-sample Sharpe on a pre-inception window; score the book only after
  inception. Per-book false promotion must still be ≤ 0.05 + 2·se. (This is
  the exact trap option D fell into; the book must be shown NOT to.)
* **GB3 (power, informational):** members with true Sharpe s ∈ {0.2, 0.3,
  0.5}, M ∈ {10, 30, 50}, ρ ∈ {0, 0.05, 0.2}: P(promoted within 10 y) and
  the median year. The honest number the owner needs: how many independent
  0.3-Sharpe members does it take before a decade certifies the book.
* **GB4 (dilution, informational):** the same with a stated fraction of
  null members (50%, 80%) — what the book looks like if most of the research
  pipeline's survivors are noise.

Seeds: calibration/gates use seeds different from the Dormant run's
(20260910 family). Nothing is tuned after seeing results.

## 5. What this does not do

It does not pick winners; it tests the research process as a whole. If most
members are null, the book fails its looks and that is the finding. It does
not allocate capital. It does not replace per-family scorecards. It needs
the Dormant manifest to be populated (owner's triage) before the first
membership date can mean anything; until then the only members are the
four Active registrations.
