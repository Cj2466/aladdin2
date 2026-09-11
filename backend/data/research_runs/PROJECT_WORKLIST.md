# PROJECT WORKLIST — every open item, every topic (living document)

รายการงานทั้งโปรเจกต์ ทุกหัวข้อ อัปเดตทุกครั้งที่งานเปลี่ยนสถานะ ถ้ากลับมาหลังหยุดไปนาน ให้อ่านไฟล์นี้ก่อน
(Started 2026-09-12 at the owner's request. Rule: append a dated line when an item changes; never
delete a closed item — move it to §10 with the commit that closed it.)

Legend: **OWNER** = only the owner can do/decide it. **CLAUDE** = the assistant can do it in a
worktree. **BLOCKED** = waiting on something named. Dates are absolute.

---

## 1. The strategic decision in front of the owner (2026-09-12)

| # | item | who | status |
|---|---|---|---|
| 1.1 | Choose Path A (continue the edge search as a BOOK, accept ~3 years to the first kill/continue decision, ~10 years to full 0.95 certification) or Path B (stop trying to beat the market; harvest diversified risk premia; no proof needed; not Renaissance) | OWNER | open; Step 0 (§2) is the evidence for this choice |
| 1.2 | Adopt the five SpaceX-style principles (certify the BOOK not single families; source by "who is forced to lose AND big money cannot collect"; delete large-universe / published-anomaly / build-before-check requirements; every rule points to an incident; automate last) — orchestrator's judgment: adopt 1–4 under conditions A/B/C, not 5 yet | OWNER | open |
| 1.3 | Write the kill date (condition A) before BOOK inception, e.g. 3 years after inception without passing the 0.50 screening → close program | OWNER | open |
| 1.4 | Declare BOOK inception (`book_2026-09-09/book_manifest.json` inception = null) | OWNER | open; only after 1.1 = A and Step 0 says ≥3 admissible members |
| 1.5 | `FIRST_PRINCIPLES.md` (every claim points at a measured result) + CLAUDE.md amendments (0.95 bar → BOOK; portfolio-level sourcing pre-check with ρ vs members and a pre-declared admission threshold; ρ estimation method) | CLAUDE, after OWNER approves 1.2 | not started |

Background for 1.x: session memory `project_first_principles_and_book_roadmap_2026-09-12.md`;
`handover_2026-09-11/HANDOVER_2026-09-11.md` §2–3 (certifiability ceiling).

## 2. Step 0 — member-production trial (this week, 2026-09-12 → ~09-18)

Plan: `member_census_2026-09-12/STEP0_WEEK_PLAN_2026-09-12.md`. Owner said "start Day 1" on 2026-09-12.

| day | item | status |
|---|---|---|
| 1 | Census of the 20 existing members (16 Dormant + 4 Active): pairwise ρ + forced-loser / big-money classification → `MEMBER_CENSUS_2026-09-12.md` | DONE 2026-09-12: 20/20 ρ measured (mean 0.018, max 0.43, round_c/lps is the hub); **0 ADMISSIBLE, 4 DOUBTFUL, 16 NOT** — the existing members do not seed the BOOK under the new criterion; corner test (Day 2–3) is the only remaining route |
| 2–3 | Shared point-in-time micro-cap panel incl. delisted names (free Alpaca SIP); portfolio-level pre-check for each forced-loser mechanism in the corner | IN PROGRESS 2026-09-12 02:30: admission rule R1–R6/P1–P4 committed (41ef96a) before any result; N-PORT ownership-breadth measurement running (2019q4: 21,047 equity CUSIPs, median 4 fund owners, 6,291 with 5–47 owners); Alpaca universe probe running (14,315 active / 19,182 inactive US equities, 2,867 inactive on listed exchanges); Opus sourcing agent running on forced-flow mechanisms in the corner |
| 4–5 | Build only what passed the pre-check (pre-registration → Opus build → orchestrator re-derivation → full suite → merge) | not started |
| 6 | Report "admissible members: X"; decision point 1 (X ≥ 3 → owner decides 1.1; X ≤ 1 → discuss Path B) | not started |

## 3. Roadmap after Step 0 (only if Path A)

| step | when | item | who |
|---|---|---|---|
| 1 | weeks 2–3 | §1.3–1.5; the 17 real scorecards (§5.1) become mandatory because BOOK members need real cards; owner runs the reset scripts (§4.1) | OWNER + CLAUDE |
| 2 | months 1–6 | member factory: pre-check → pre-register → build → verify → merge; target 10 low-ρ members; decision point 2 at month 6 on production rate (<1/month → lower target, open the paid-data list §4.4, or close) | CLAUDE |
| 3 | at ≥10 members | automation: BOOK as one paper portfolio ticked daily; coverage checks; CUSUM retirement rule (already built, `retirement_rule_v2`); risk limits; storage decision (P7 was decided "local-only", would need revisiting) | CLAUDE + OWNER |
| 4 | years 1–3 | yearly no-peek looks (Dormant look schedule); keep admitting members; no capital | CLAUDE |
| 5 | year 3+ | only if the BOOK passes the 0.50 screening: live-capital discussion, full paid-data list, real costs at real size; full 0.95 ≈ year 10 | OWNER |

## 4. Owner-only actions pending (independent of §1)

| # | item | since | note |
|---|---|---|---|
| 4.1 | Run the live-registration reset, then a tick, from the MAIN checkout `backend/`: `./venv/bin/python data/research_runs/live_panel_coverage_2026-09-10/reset_live_registrations.py` then `set -a; . ./.env; set +a; ./venv/bin/python data/research_runs/live_panel_coverage_2026-09-10/tick_live_registrations.py` (reset refuses if rows moved since its backup) | 2026-09-10 | rule 6; classifier blocks the assistant |
| 4.2 | Production is DOWN: `https://aladdin2-backend.onrender.com/health` returned HTTP 503 (2026-09-10); needs the Render dashboard. Two unmerged worktrees hold earlier attempts (`backend-keepalive`: GitHub Actions ping; `disable-heavy-background-runners`: fix for a Render OOM crash loop) — decide merge/discard | 2026-09-10 | P7 decided: stores rebuilt every deploy, live tick is local-only |
| 4.3 | Rotate `FRED_API_KEY` (leaked once into a local build log, 2026-09-01; not confirmed rotated). Set `SEC_EDGAR_CONTACT` to a real monitored address before Project 2's scanner runs in production | 2026-09-01/02 | |
| 4.4 | Paid-data decisions (`PENDING_PAID_DATA_DECISIONS.md`): P1 borrow feed OPEN; P2 delisted — DO NOT BUY for 2016+ (Alpaca covers); P3 country BE/ME OPEN; P4 Norgate futures OPEN (TSMOM closed anyway); P5 Lou Table II scaling OPEN; P6 options gamma OPEN (blocks that candidate); P7 DECIDED local-only; P8 crypto liquidation data provisional | rolling | resurface all together before any go-live |
| 4.5 | Polymarket: cut for now (legal access from Thailand + on-chain execution unverified) | 2026-09-11 | reopen only if the owner wants it |
| 4.6 | Watchdog (`.claude/watchdog/resume_session.sh`) is NOT armed — owner chose "พัก" 2026-09-02; re-flag before any unattended overnight run | 2026-09-02 | |
| 4.7 | Caveman response mode: discussed, never decided; owner now wants plain language, which is a different thing | 2026-09-05 | |

## 5. Governance debt (CLAUDE, no owner input needed unless stated)

| # | item | deadline | status |
|---|---|---|---|
| 5.1 | 17 real scorecards (16 Dormant + retired `noa_neutral`), written from the papers, never reconstructed from code (`tests/test_registration_scorecards.py` is the work-list; the 1 known governance failure is this) | before the first Dormant look ≈ 2027-09 (earlier if Path A: Step 1) | 0 of 17 |
| 5.2 | `nport_flow_fit` has zero DB rows (its 09-05 worktree DB was lost); documented in `run_nport_flow_fit.py`; inventory entry corrected 2026-09-11 | — | closed as unrecoverable; re-run only if the family is ever needed |
| 5.3 | Edge-search "directions 2/3" of 2026-09-10 were paused; their definitions exist only in that session's transcript, not in a committed file | — | recover from the 09-10 transcript and record, or drop explicitly |

## 6. Data-infrastructure defects known and NOT fixed

| # | item | risk | status |
|---|---|---|---|
| 6.1 | Price store first-write-wins: a ticker that SPLITS after its rows were stored keeps stale pre-split prices (found 2026-09-04 on APH/MNST); guard + audit exist, root not fixed | bounded to local dev while production has no disk | open |
| 6.2 | PEAD has no successor-shell CIK resolution (XOM → a 29-filing shell); exposure measured 2 of 503, trigger NOT adopted | low | open, measured 2026-09-10 |
| 6.3 | EDGAR submissions store must be re-run regularly — SEC's `filings.recent` is bounded, every day not ingested loses filings permanently | medium | no schedule exists; add one when automation (§3 step 3) is built |
| 6.4 | Same class as 6.3: `sec_shares_outstanding` cache, `submissions_sic` current-day fallback | low | open |
| 6.5 | `data/dividend_payment_calendar.json` is gitignored and resolved PER WORKTREE (main checkout has the 2026-09-09 file; a worktree has none → `dividend_payment_pressure` silently replays 0 specs). Same routing gap the price store had before 09-09; fix = route it to the main checkout like the stores, or copy with a hash check. A fresh rebuild via `fetch_dividend_payment_calendar.py` would NOT be point-in-time (pay-date lags are "most recent") | medium for that one family | open; worked around by copy on 2026-09-12 |
| 6.7 | `data/form13f_raw/` (SEC fails-to-deliver archives = the CUSIP→ticker map, 29 archives in the main checkout) is gitignored and resolved PER WORKTREE like 6.5 — a worktree build of any holdings family must copy or route it | medium | open, found 2026-09-12 |
| 6.6 | Alpaca free SIP tier returns 403 for any window touching the current UTC day — every fetch ends at the last complete UTC day | operational | known, handled per script |

## 7. Live registrations (observational, no capital) — state 2026-09-12

quality_cbop/cbop_ls_h63 (definite_negative), lazy_prices_jaccard_full/lazy_jaccard_full_h126_ivol
(underpowered), short_interest_ratio/si_ratio_hedged_h21 (definite_negative), crypto/xc_btcbeta_l180_h180
(underpowered); noa_neutral retired 2026-09-06. Waiting on §4.1 reset. CUSUM retirement rule (protect 1.0)
wired. No status change without the owner (rule 6).

## 8. Project 2 (macro/event system) — optional, not on the critical path

2.1 exposure betas DONE (`ad93f16`); 2.2 event scanner DONE (`aabc590`); in a trigger-rate observation
gate since 2026-09-02 (never reviewed since). NOT built: 2.3 LLM reasoning; 2.4 execution wiring (must
also fix `ExecutionRunner._rebalance` leaving Project 2 inert when Project 1 has zero live portfolios);
2.5 `MacroEventPanel.tsx`. Signature Library / regime classifier (2.3a) designed, not built. Crisis-composite
+ formula-based leverage listed as the higher-value Project 2 item (2026-09-03).

## 9. Closed research — do NOT reopen without new evidence

58 honest negatives (`negatives_map_2026-09-11/`), 14 declined at sourcing (`DECLINED_AT_SOURCING.md`),
TSMOM (all variants, breadth gate 10.0 vs 15), LETF rebalancing (wrong sign), intraday_momentum_spy,
perp basis (extinct at retail costs 2025–26), theory-free pattern scan (placebos beat real charts on both
panels), bet-level test (rejected at its own FP gate), ONC clustering as a denominator, SPAC buy-below-trust
(~40 bets/yr), market making / MEV / retail order-flow / equity HFT (ranked out, hunting-ground review).

## 10. Closed items log (append-only)

- 2026-09-12 — Step 0 week plan written and committed (35b266f).
