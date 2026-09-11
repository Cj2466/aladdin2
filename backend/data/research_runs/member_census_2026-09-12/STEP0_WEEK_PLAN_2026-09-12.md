# Step 0 — "member production trial" — week plan (written 2026-09-12, before any result)

**Owner's decision so far (2026-09-12):** run Step 0 ONLY. No CLAUDE.md change, no BOOK
inception, no purchase, no kill date yet. Owner asked for plain-language reporting.
The strategic context (six first principles, five SpaceX-style principles, the phased
roadmap, the 3-year kill date, Path A vs Path B) is in session memory
`project_first_principles_and_book_roadmap_2026-09-12.md`; this file is the operational
plan so that any future session can resume without the conversation.

**The one question this week answers:** how many candidate BOOK members satisfy the new
sourcing criterion — (i) someone is FORCED to trade against the position (a mechanical
loser), and (ii) large capital cannot profitably collect it (F5) — and are mutually
low-correlated enough to add pooled power. Output is ONE number: admissible members.

## Day 1 (2026-09-12) — census of what already exists   [IN PROGRESS]
- Members = 16 Dormant (`dormant_pool_2026-09-09/dormant_pool_manifest.json`) + 4 Active
  registrations (quality_cbop/cbop_ls_h63, lazy_prices/lazy_jaccard_full_h126_ivol,
  short_interest/si_ratio_hedged_h21, crypto/xc_btcbeta_l180_h180).
- `member_census.py`: pairwise correlation of the frozen specs' net daily returns from the
  committed 2026-09-05 return matrix (18 of 20 present) + `capture_missing_two.py` for
  rebalancing_pressure and dividend_payment_pressure via the Dormant re-scorer's own path.
- `MEMBER_CENSUS_2026-09-12.md` (orchestrator, Fable): for each of the 20, who is forced to
  lose / can big money collect it / verdict ADMISSIBLE, DOUBTFUL, or NOT (with the source
  section that establishes the mechanism), plus the correlation findings.
- Decision at end of Day 1: which existing members count, and which pairs are near-duplicates.

## Day 2–3 — the micro-cap corner
- Build ONE shared point-in-time micro-cap panel including delisted names (free Alpaca SIP
  daily, `feed="sip"`, `adjustment=all`, delisting cut by SEC submissions; probe and memo in
  `alpaca_delisted_coverage_2026-09-11/`). Reproducibility: route it through the shared
  price store like every other panel (CLAUDE.md §2).
- List the forced-loser mechanisms already tested on large caps that the literature says
  survive in the costly-to-arbitrage corner (McLean-Pontiff; HXZ against — see
  `hunting_ground_review_2026-09-11/`): candidates in `candidate_sourcing_2026-09-11/candidates_ranked.csv`.
- For each: PORTFOLIO-LEVEL pre-check first — "does adding this raise the BOOK's pooled
  power enough?" — using `sourcing_power_check` on the marginal pooled Sharpe (Sharpe_pool
  ≈ s·√(M/(1+(M−1)ρ))) with ρ measured against Day-1 members. Declined ones go to
  `DECLINED_AT_SOURCING.md`, not built.

## Day 4–5 — build only what passed the pre-check
- Usual pipeline, unchanged: pre-registration (with control non-degeneracy proof) committed
  before any number → Opus build in a worktree → orchestrator re-derives from raw files with
  its own code → full backend suite on the exact tree → end-to-end re-check → merge.
- Model: Opus for builds; main session may switch to Opus for Day 2–5 (tell the owner).

## Day 6 — report one number
- "Admissible members: X." Decision point 1: X ≥ 3 → owner decides on the 3-year wait
  (Path A continues to Step 1: FIRST_PRINCIPLES.md, CLAUDE.md amendments, kill date,
  inception); X ≤ 1 → discuss Path B (harvest diversified risk premia) — no further build.

## Standing rules that apply all week
worktree isolation; never `git add -A`; never fabricate (cite or label a guess); persist
every result; sequential agents; rule 6 (live registrations untouched); secrets only via
`set -a; . ./.env; set +a` in the MAIN checkout; pure-append dated corrections; full suite
on the exact tree merged; main-checkout venv only; Alpaca 403 on windows touching the
current UTC day; "make as few mistakes as possible" (slow and verified over fast).
