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
| 2–3 | Micro-cap corner: universe + breadth + sourcing + pre-check | DONE 2026-09-12: corner exists on free data (1,070–1,810 listed names/quarter with 5–47 fund owners, 2019q4→2026q2; 2,100 delisted plain tickers on Alpaca); 3 forced-flow candidates checked against the pre-declared rule → all DECLINED (ledger #15–17); P9 logged (OTC bars) |
| 4–5 | Build only what passed the pre-check | NOTHING PASSED — no build (rule); owner may waive R3 for ledger #16 (fire-sale count on the sparse-ownership universe, paper gross Sharpe 0.44–0.70) |
| 6 | Report "admissible members: X" | REPORTED 2026-09-12: X = 0 → decision point 1 says discuss Path B, unless the owner waives R3 for #16 |

## 2b. After Step 0 — owner: "find more answers, whatever it takes" (2026-09-12)

| # | item | status |
|---|---|---|
| 2b.1 | Evidence-tiered review of small-participant-only edges incl. the Thai home market (`small_participant_edges_2026-09-12/`) | DONE, merged c02bd68; Thai 26.7y window cuts the admissibility bar 2.416 → 1.528; foreign-board premium = forced foreign buyer; odd-lot tenders dead after costs; Thai small-cap corner has no forced flow |
| 2b.2 | M1 Thai foreign-board premium: tradable or stale? (`measurements_m1_m3_2026-09-12/M1_RESULT.md`) | DONE 2026-09-12, orchestrator re-derived: BBL/KBANK two-sided 89%/93% all-time but 46%/58% last 3y; depth fell to THB 0.8–2M/day; premium autocorr 0.96–0.99, no snap-back; 12 other lines stale. OPEN operational question for the OWNER: can a Thai retail account sell local shares onto the foreign board, at what fee? |
| 2b.3 | M2 US odd-lot self-tender provisions: bet count and gross premium | IN PROGRESS (Opus, worktree measurements-m2-2026-09-12) |
| 2b.4 | M3 Thai free-feed survivorship + SET daily files (`M3_RESULT.md`) | DONE 2026-09-12, orchestrator recounted: 230/256 delisted names (89.8%) return zero bars on Yahoo; SET daily files free but market-wide/single-day → P10 logged |
| 2b.5 | Not yet researched: IPO retail allocation, rights oversubscription, Dutch auctions, small merger arb, share-class arb, OTC liquidity provision (review §3.4) | open |

## 2c. The post-publication lockbox (2026-09-12 afternoon) — FIRST POSITIVE RESULT

| # | item | status |
|---|---|---|
| 2c.1 | Set 2: 212 Open Source Asset Pricing predictors, one pre-declared look (`postpub_lockbox_2026-09-12/`) | DONE, merged b1204b1: P-clean post-publication book after a 20/P bps haircut = SR 0.599, NW t 4.27, 195 members, 1974–2024, decay 0.39 → PASS (line: SR ≥ 0.50 & PSR ≥ 0.95); re-derived by the orchestrator |
| 2c.2 | Set 1: the same on our 20 members | NOT RUN — only 1 of 20 frozen specs is paper-faithful (`RESULT_SET1_OUR_20.md`) |
| 2c.3 | Set 3: buildable subset | DONE: 163/195 in data categories we hold; buildable-only book SR 0.597 t 4.26; ρ mean 0.03, 27% of pairs ≥ 0.30; ranking in `set3_per_predictor.csv` |
| 2c.4 | Flagged, not investigated (would be a second look; needs its own declared protocol): why the post-SAMPLE window scores lower (0.24) than post-PUBLICATION (0.60) | open |
| 2c.5 | OWNER decisions now: (a) start building BOOK members from the buildable ranking — paper-faithful spec only, no grid, compare our sealed-window number with OSAP's, admit at screening level (recommend 3–5 least-correlated predictors we have NOT built before); (b) BOOK inception; (c) CLAUDE.md amendment: portfolio-level judgement replaces the per-family 0.95 bar (proposal, owner's call) | open |

## 2d. Step A — the whole-market data foundation (owner approved 2026-09-12 afternoon)

| # | item | status |
|---|---|---|
| 2d.1 | **A1** whole-market US daily price panel from Alpaca 2016→, including delisted names, in a NEW store `data/price_store_alpaca/` (never the yfinance store the live registrations read) | DONE 2026-09-12: 14,451 symbols / 20,345,521 rows / 290 MB; 1,817 dead names retained; breadth 5,218 (2016) → 9,554 (2025) names with ≥200 bars; raw (as-traded) bars verified against AAPL's pre-split close; dividends + splits populated from Alpaca's free corporate-actions feed and spot-verified (AAPL 4:1, TSLA 5:1 and 3:1). Orchestrator re-derived every headline number with separate code |
| 2d.2 | **A1b** delisting outcomes | DONE 2026-09-12 — and the orchestrator's stated hypothesis was WRONG, measured: the median implied final return is **+0.03%**, not a missing premium, because the last trade already converges to the deal (94.6% of deals close within 3 days of the last bar). Outcomes of the 1,817 dead names: 480 acquisitions (26.4%), 1,235 no action found (68.0%), 102 other. FIT is a real +6.06% (6.93 → 7.35). A wrong-record bug that fabricated +4,800% was caught by the agent and fixed. Orchestrator re-derived counts, median and FIT exactly. **Correction to the brief**: Alpaca's `types=` filter takes SINGULAR names (`cash_merger`, not `cash_mergers`) |
| 2d.2b | Found while doing 2d.2, NOT fixed: an EDGAR spot-check of 10 `no_action_found` names found 10/10 have a real Form 25, and **8 of 10 are SPAC renames** — those tickers are not dead, they continue under a new symbol, and the panel treats the rename as a death. Ticker-continuity across renames is its own data question | open |
| 2d.3 | **A2** per-ticker spread/cost estimate on the whole-market panel (the current flat 5 bps is ~3-5× too expensive for large caps and far too cheap for micro caps) | not started |
| 2d.4 | **A3** whole-market point-in-time accounting from SEC's Financial Statement Data Sets (~5,500 filers/quarter, `filed` date = exact point-in-time). Coverage measured 2026-09-12 (`fsds_coverage_2026-09-12/`): core fields 87–99% after tag ladders, revenue 73%, COGS only 44–47%, federal/foreign tax split unusable | not started |
| 2d.5 | **Noted for later, not started (owner: "จดไว้ก่อน")**: build our own versions of the 36 buildable financing/leverage/investment predictors (XFIN 0.83, ShareIss5Y 0.76, NetEquityFinance 0.71, ShareIss1Y 0.64, AssetGrowth 0.63, NetDebtFinance 0.61 …) — none is built yet; the OSAP numbers are third-party evidence only | noted |
| 2d.6 | Owner's idea, noted not started: classify delisted names with AI (failed vs acquired) and study both sides of acquisitions as a MECHANISM. Two uses separated: (a) recording the factual outcome = 2d.2, safe and valuable; (b) predicting takeovers = must pass pre-registration + placebo, my prior is negative, and note ZERO of the 212 published predictors cover mergers/distress (Altman Z-Score and Failure Probability are in the dataset as PLACEBOS). Also flagged: an LLM reading a 2018 filing already knows 2019's outcome — look-ahead contamination that is hard to remove | noted |

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
| 4.4 | Paid-data decisions (`PENDING_PAID_DATA_DECISIONS.md`): P1 borrow feed OPEN; P2 delisted — DO NOT BUY for 2016+ (Alpaca covers); P3 country BE/ME OPEN; P4 Norgate futures OPEN (TSMOM closed anyway); P5 Lou Table II scaling OPEN; P6 options gamma OPEN (blocks that candidate); P7 DECIDED local-only; P8 crypto liquidation data provisional; P9 post-delisting OTC bars (Alpaca `feed=otc` 403 on free tier) provisional, no purchase recommended; P10 Thai per-stock daily panels with history (SETSMART) provisional, not recommended | rolling | resurface all together before any go-live |
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
| 6.5 | `data/dividend_payment_calendar.json` is gitignored and resolved PER WORKTREE (main checkout has the 2026-09-09 file; a worktree has none → `dividend_payment_pressure` silently replays 0 specs). Same routing gap the price store had before 09-09; fix = route it to the main checkout like the stores, or copy with a hash check. A fresh rebuild via `fetch_dividend_payment_calendar.py` would NOT be point-in-time (pay-date lags are "most recent") | medium for that one family | CLOSED 2026-09-12: `PAYMENT_CACHE_PATH` routed to the main checkout (branch route-caches-2026-09-12), test pins it |
| 6.7 | `data/form13f_raw/` (SEC fails-to-deliver archives = the CUSIP→ticker map, 29 archives in the main checkout) is gitignored and resolved PER WORKTREE like 6.5 — a worktree build of any holdings family must copy or route it | medium | CLOSED 2026-09-12: `form13f_provider.DEFAULT_CACHE_DIR` and `nport_provider.DEFAULT_CACHE_DIR` routed to the main checkout, test pins both |
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
- 2026-09-12 — three gitignored vendor caches routed to the main checkout (worklist 6.5/6.7 closed).
- 2026-09-12 — Step 0 Days 1–3 done in one night: census (0 admissible of 20), corner measured, 3 candidates declined at sourcing (#15–17), P9 logged.
