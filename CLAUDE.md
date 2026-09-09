# aladdin2 — project rules for Claude

## 1. Project overview

A quantitative trading-signal research platform ("Portfolio risk analytics backend" per its own package description). It searches for candidate trading factors/signals, tests them for genuine statistical and economic validity, and forward-validates them (paper/observational tracking, not real capital) before any live-capital discussion. **No real capital is currently deployed anywhere in this system** — the execution/live-order path exists in code but stays gated off (`ExecutionControl.trading_halted` defaults `True`; no brokerage credentials configured in production). The research goal is a small number of *real*, independently-verified edges — not a high pass rate. An honest negative is a valid, useful outcome; a false positive is the worst possible outcome.

## 2. Tech stack

**Backend** — Python 3.12, FastAPI + Uvicorn, SQLAlchemy 2.0 + Alembic migrations, Pydantic v2 / pydantic-settings. SQLite locally (an absolute path at `backend/aladdin2.db`, anchored to `app/config.py`'s own location rather than the process working directory — fixed 2026-09-06 after the old cwd-relative default silently lost a worktree-run family's trial rows), Postgres in production via `DATABASE_URL` (Neon, normalized to `postgresql+psycopg://`). Research/quant stack: pandas, numpy, scipy, statsmodels, scikit-learn, `bidask` (spread estimation), yfinance (market data). Auth via argon2-cffi; rate limiting via slowapi; PDF export via fpdf2.

**Frontend** — React 19 + TypeScript, Vite 8, Tailwind CSS 4, TanStack Query, Recharts, axios. Linted with oxlint; Playwright present for e2e testing.

**Deploy** — Render (`render.yaml`): free-tier Python web service, `alembic upgrade head && uvicorn app.main:app` as the start command, health check at `/health`.

**Testing** — pytest (`asyncio_mode = "auto"`, configured in `backend/pyproject.toml`, no separate `pytest.ini`) for the backend; a Node script for a frontend proxy-retry test; Playwright available for browser e2e.

## 3. Folder structure

```
aladdin2/
├── CLAUDE.md
├── render.yaml                  # Render deploy config
├── research_archive/            # dated snapshots of past research sessions
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entrypoint
│   │   ├── config.py            # Settings (Pydantic), DB URL, env vars
│   │   ├── db.py                # SQLAlchemy engine/session
│   │   ├── models/               # ORM models — one file per table, e.g.
│   │   │                         #   cross_sectional_trial_result.py,
│   │   │                         #   cross_sectional_forward_validation.py,
│   │   │                         #   execution_control.py, live_order.py
│   │   ├── routers/              # FastAPI route modules (research_lab.py,
│   │   │                         #   forward_validation.py, execution.py, ...)
│   │   ├── schemas/               # Pydantic request/response schemas
│   │   ├── auth/
│   │   └── services/
│   │       ├── research_lab/     # THE core of this project — ~80+ modules,
│   │       │                      #   one (or a few) per candidate signal family
│   │       │                      #   (cross_sectional_*.py), plus shared
│   │       │                      #   infrastructure: deflated_sharpe.py,
│   │       │                      #   preservation_score.py, effective_n_clustering.py,
│   │       │                      #   spread_estimator.py, templates/ (scorecard +
│   │       │                      #   verification-checklist templates)
│   │       ├── execution/         # live-order / broker integration (currently halted)
│   │       ├── forward_validation_service.py
│   │       ├── cross_sectional_forward_validation_service.py
│   │       ├── macro_data/, macro_event/, market_data/, historical_analog/
│   │       └── risk/              # portfolio risk analytics (RMT denoising, etc.)
│   ├── alembic/                  # DB migrations
│   ├── data/                     # persisted research artifacts: research_runs/
│   │                              #   (per-run JSON/TXT reports), price_store/,
│   │                              #   edgar_*/, form13f_raw/, finra_short_interest/,
│   │                              #   binance_futures/, fama_french_factors_monthly.csv
│   ├── tests/                     # pytest suite, mirrors app/ structure
│   ├── aladdin2.db                # local SQLite DB (gitignored data, schema via alembic)
│   └── pyproject.toml
├── frontend/
│   └── src/
│       ├── App.tsx, main.tsx
│       ├── pages/, components/, hooks/, context/, api/, lib/
└── .claude/
    ├── worktrees/                 # isolated worktrees for every change (see rules)
    ├── watchdog/                  # overnight-session resume tooling
    └── settings.json / settings.local.json
```

## 4. Coding rules

- **Never fabricate.** Every factual or numerical claim is either verified and cited, or explicitly labeled a guess. Never implement a published formula from memory — put the source paper/section in context, cite the equation number in code, and validate against synthetic data with a known true answer before trusting it on real data. (This project has already been burned once by a formula-from-memory mistake.)
- **Never `git add -A`.** Stage explicit files by name.
- **Persist every computed result to a real DB row or committed file** — never leave a result only in a scratch note or an agent transcript.
- **Every candidate signal ("family") needs, before its result is treated as real:**
  - **DSR reported across multiple N assumptions, not one point value**, with a two-tier verdict: fails even at the most lenient (family-local) N → definite negative; passes at lenient N but fails at a more conservative, more-pooled N → *unresolved*, needs more forward-validation evidence, not a pass; passes even at the most conservative N measured → a real pass. (A single "correct" N is not currently computable — correlation-clustering was tried and failed to find real structure in this project's actual trial data; see `effective_n_clustering.py` and `dsr_n_trials`. Report the honest range rather than a falsely precise single number.)
  - **`preservation_score` computed as a standard secondary check, with no exceptions** (`app/services/research_lab/preservation_score.py`). This has already been silently skipped once for a real decision before being caught — treat that as a warning, not a one-off.
  - **Mechanism-fidelity review**: every non-trivial construction choice cites its source paper/section/equation; deviations from the source are logged with reasoning; an independent reviewer signs off before results are treated as final.
  - See `app/services/research_lab/templates/` for the standard registration scorecard and verification checklist.
- **Conditional, situational rules:**
  - Regime-conditional testing (separate DSR in-regime vs. out-of-regime, regime definition pre-declared *before* looking at in-regime returns) only when the source literature's claim is explicitly conditional (e.g. trend-following's claimed "crisis alpha"). Skip for plain unconditional claims.
  - Cost realism must feed into the DSR calculation itself for every family, not sit as a side disclosure. Capacity estimates and backtest-window regime-coverage disclosure are informational, not gating, while no live capital is deployed — but must be stated honestly.
  - Don't retroactively re-apply a newly-stricter rule to already-declined candidates (a stricter gate can only keep them declined or decline them harder). Do apply new rules going forward, and to any live registration when specifically asked.
  - Paid-data gaps found mid-task get logged, not acted on immediately — keep building, resurface the full list before any real go-live discussion.

## 5. Commands

Backend (`cd backend`):
- Install: `pip install -e ".[dev]"`
- Run migrations: `alembic upgrade head`
- Dev server: `uvicorn app.main:app --reload`
- Tests: `pytest`
- Lint: `ruff check .`

Frontend (`cd frontend`):
- Install: `npm install`
- Dev server: `npm run dev`
- Build: `npm run build`
- Lint: `npm run lint`
- Tests: `npm run test`

## 6. Workflow

1. **Git worktree isolation, always — even a small or "safe-looking" edit.** Every change happens in an isolated worktree (`.claude/worktrees/<name>`), never a direct commit on `main`. Merge into `main` only after independent verification. (Violated once before under time pressure with the excuse "it's just a small edit" — that excuse doesn't hold; don't accept it from yourself either.)
2. **Independent verification is required before declaring any deliverable done.** Re-derive key numbers by hand from primitives, diff any formula file that should be unchanged and confirm it actually is, run the relevant test suite and confirm nothing new broke, check that no test was quietly weakened just to make it pass.
3. **Dispatch agents sequentially — never more than one in parallel for a single task.** (A 4-way parallel dispatch once caused a real account-wide rate-limit incident.) Never drop part of a task's scope to finish a round-trip faster; brief each sequential dispatch with full context so it doesn't waste its turn rediscovering what's already known.
4. **Model choice is an active decision, not a default — think it through carefully and in detail every time, not a quick reflex either way.** Start from Sonnet; escalate to Opus or Fable 5.1 specifically when a task needs genuine judgment — adversarial/skeptical verification, methodological calls, synthesis across conflicting findings, safety-critical review. (`claude-fable-5-1` was banned outright from 2026-09-02 to 2026-09-07 after a Fable-tagged HTTP 429 "session limit" hit the orchestrating agent mid-research during a 4-way parallel fan-out; the project owner explicitly lifted the ban on 2026-09-07. Lifting it does not relax rule 3 in any way. Known hazard, recorded honestly: the very first Fable dispatch after the lift — a SINGLE sequential agent, at the end of a heavy night — was also killed by a Fable-tagged 429 before doing any work, so parallelism is NOT established as the cause; whether Fable has its own smaller session quota or the account-wide session window was simply already drained is unresolved. Practical rule: a Fable agent must commit to its worktree frequently so an interruption is resumable, and if it 429s mid-task, fall back to Opus rather than wait for the reset.)
   **Model policy, set by the project owner 2026-09-09 (supersedes "start from Sonnet" for the MAIN session):**
   - The main session is the orchestrator: it decides, briefs, and independently verifies every sub-agent's work. It must therefore be at least as strong as any sub-agent it checks. Use **Fable 5.1** on days whose work is methodological judgment (criteria design, adversarial verification, synthesis across conflicting findings); use **Opus** on days whose work is building/merging along an already-agreed plan.
   - Sub-agents get the model the orchestrator chooses per task: **Sonnet** for well-specified builds, test runs and file handling; **Opus** for research builds needing source-paper interpretation or construction judgment; **Fable** only for a stand-alone adversarial review. Always one at a time (rule 3), always committing to the worktree frequently.
   - The orchestrator cannot change the main session's model; only the owner can, via `/model`. **The orchestrator must tell the owner explicitly, every time the phase of work changes, which model the main session should be on and why** — the owner has said they will switch on request. Do not infer the right model from whatever is currently selected; decide it from the work. There is no settings mechanism that auto-switches models by task.
5. **Never let an unrelated message silently pause background work** — but an explicit "stop" instruction must be honored immediately and completely.
6. **Never change a live/forward-validation registration's operational status** (promote, retire, withdraw) without the project owner's explicit sign-off. Recommend; never unilaterally execute.

## 7. Goal

**The end deliverable is a real, live, automated trading system — not just a research pipeline.** The project owner's objective is a Renaissance/Medallion-style automated trading operation: one that finds, combines, and eventually trades many independent, small, honestly-verified micro-edges at scale (process over prediction, law-of-large-numbers diversification across genuinely uncorrelated bets), rather than betting everything on any single "big idea" factor.

Everything in this file — signal research, forward-validation, the DSR/preservation_score/mechanism-fidelity rules — exists in service of that end system, not as an end in itself. Their job is to make sure that when something eventually does go live, it's a real edge, never a manufactured or uncorrected positive. Capital preservation and honesty take priority over maximizing any individual result, hit rate, or speed toward deployment — going live with something fake is a worse outcome than staying in research mode longer.

**Honest gap, stated directly rather than glossed over**: this project's actual resources (a solo researcher plus AI assistance, free/retail-grade data, no low-latency execution infrastructure) are far short of Renaissance's real scale (decades of compute, PhD headcount, proprietary data, and first-mover advantage). Chasing this direction is a deliberate choice, not a claim that the gap is already closed. The practical implication: prioritize finding genuinely new, not-yet-arbitraged, resource-appropriate mechanisms (see project research history/memory for what's already been tried and ruled out) over further refining how already-exhausted ideas get scored, and expect the path to automated live trading to run through many honest negatives first.

## 8. Where the reasoning behind these rules lives

The history and reasoning behind each rule above — why it exists, what incident it came from — lives in this project's Claude session memory, not in this file. If a rule here seems to need more context than is written, ask rather than guessing at the reason.
