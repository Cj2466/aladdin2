# aladdin2 — project rules for Claude

## What this project is

A quantitative trading-signal research platform. It searches for candidate trading factors/signals, tests them for genuine statistical and economic validity, and forward-validates them (paper/observational tracking, not real capital) before any live-capital discussion. **No real capital is currently deployed anywhere in this system.** The goal is a small number of *real*, independently-verified edges — not a high pass rate. An honest negative is a valid, useful outcome; a false positive is the worst possible outcome.

Backend: Python, research code under `backend/app/services/research_lab/`, persisted trial results in `backend/aladdin2.db` and `backend/data/research_runs/`. Frontend is a separate app, not typically touched during research work.

## Non-negotiable rules — apply to every task, no exceptions

1. **Never fabricate.** Every factual claim is either verified and cited, or explicitly labeled a guess. This is the single highest-priority rule on this project. Never implement a published formula from memory alone — put the source paper/section in context and cite the equation number in code; validate against synthetic data with a known true answer before trusting it on real data. (This project has been burned once already by a formula-from-memory mistake.)
2. **Git worktree isolation, always — even a small or "safe-looking" edit.** Every change happens in an isolated worktree (`.claude/worktrees/<name>`), never a direct commit on `main`. Merge into `main` only after independent verification. This has been violated once before under time pressure with the excuse "it's just a small edit" — that excuse doesn't hold; don't accept it from yourself either.
3. **Never `git add -A`.** Stage explicit files by name so nothing unintended (secrets, unrelated work) gets swept into a commit.
4. **Persist every computed result to a real DB row or committed file.** Never leave a result only in a scratch note, a chat reply, or an agent's transcript — this project has lost work to a wiped local DB before.
5. **Independent verification is required before declaring any deliverable done.** Re-derive key numbers by hand from primitives (don't just trust a pipeline's own output end-to-end), diff any formula file that should be unchanged and confirm it actually is, run the relevant test suite and confirm nothing new broke, and check that no test was quietly weakened just to make it pass.
6. **Dispatch agents sequentially — never run more than one in parallel for a single task.** (A 4-way parallel dispatch once caused a real account-wide rate-limit incident.) This is about dispatch shape, not scope: never drop part of a task to finish a round-trip faster, and brief each sequential dispatch with full context so it doesn't waste its turn rediscovering what's already known.
7. **Model choice is an active decision, not a default.** Start from Sonnet; escalate to Opus specifically when a task needs genuine judgment — adversarial/skeptical verification, methodological calls, synthesis across conflicting findings, safety-critical review. `claude-fable-5-1` is banned outright until the project owner explicitly lifts the ban.
8. **Never let an unrelated message silently pause background work** — but an explicit "stop" instruction must be honored immediately and completely.
9. **Never change a live/forward-validation registration's operational status** (promote, retire, withdraw) without the project owner's explicit sign-off. Recommend; never unilaterally execute.
10. **Every candidate signal ("family") needs, before its result is treated as real:**
    - **DSR reported across multiple N assumptions, not one point value**, with a two-tier verdict: fails even at the most lenient (family-local) N → definite negative; passes at lenient N but fails at a more conservative, more-pooled N → *unresolved*, needs more forward-validation evidence, not a pass; passes even at the most conservative N measured → a real pass. (A single "correct" N is not currently computable — correlation-clustering was tried and failed to find real structure in this project's actual trial data. Report the honest range rather than a falsely precise single number.)
    - **`preservation_score` computed as a standard secondary check, with no exceptions.** This has already been silently skipped once for a real decision before being caught — treat that as a warning, not a one-off.
    - **Mechanism-fidelity review**: every non-trivial construction choice cites its source paper/section/equation; deviations from the source are logged with reasoning; an independent reviewer signs off before results are treated as final.
    - See `backend/app/services/research_lab/templates/` for the standard registration scorecard and verification checklist (build status: check recent commits/project memory — this was still in progress as of 2026-09-05).

## Conditional rules — apply only when the situation calls for them

- **Regime-conditional testing** (separate DSR in-regime vs. out-of-regime, with the regime definition pre-declared *before* looking at in-regime returns) is required only when the source literature's claim is explicitly conditional — e.g. a trend-following strategy claiming it specifically earns "crisis alpha" during equity bear markets. Skip entirely for mechanisms with a plain, unconditional claim.
- **Cost realism** must feed into the DSR calculation itself for every family (not sit as a side disclosure). Capacity estimates and backtest-window regime-coverage disclosure (which real historical regimes — dot-com, GFC 2008, COVID, 2022 rate hikes — are actually present in the tested window) are informational and don't block registration while no live capital is deployed, but must be stated honestly, not omitted.
- **Retroactively re-applying a newly-stricter rule to already-declined candidates is not required.** A stricter gate can only keep a failing candidate failing or fail it harder — it's not worth the effort. Do apply new rules to every new candidate going forward, and to any currently-live registration when specifically asked to re-check it.
- **Paid-data gaps found mid-task get logged, not acted on immediately** — keep building, resurface the full list of pending paid decisions before any real go-live discussion.

## Where the reasoning behind these rules lives

The history and reasoning behind each rule above — why it exists, what incident it came from — lives in this project's Claude session memory, not in this file. If a rule here seems to need more context than is written, ask rather than guessing at the reason.
