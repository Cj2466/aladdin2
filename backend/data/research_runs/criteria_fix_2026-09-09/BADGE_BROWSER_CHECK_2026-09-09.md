# UnderperformanceAdvisoryBadge — headless browser check (2026-09-09)

Follow-up to CRITERIA_FIX_2026-09-09.md (the advisory replaces the retired
auto-park rule). The badge had been unit-tested but never rendered in a real
browser against the real API. This records that check. Result: PASS.

## Method

- Real FastAPI app (`app.main`, merged main `203e82d`) run against a
  SCRATCHPAD COPY of the local SQLite DB, every background runner's `run()`
  replaced by a no-op, CORS opened to a throwaway Vite port. Nothing touched
  `backend/aladdin2.db`; the copy was deleted afterwards.
- Real dashboard: `vite` dev build of `frontend/` with `VITE_API_BASE_URL`
  pointed at that API.
- Local registrations have at most 11 realized days (below the badge's
  20-day floor, where it correctly renders nothing), so in the COPY three
  registrations' `day_results_json` were padded to 70 synthetic days:
  quality_cbop mildly positive, short_interest_ratio clearly negative,
  one pairs `momentum_v1` row (re-owned by a throwaway verified user)
  mildly negative. The numbers below are therefore synthetic; only the
  rendering path is under test.
- Playwright 1.62.1 / Chromium headless: log in through the AuthPage form,
  click "Research Lab", wait for the badge text, then (a) read every badge's
  text, tooltip and border colour from the DOM, (b) fetch both
  registration lists through the same cookie session and compute the text
  the badge SHOULD show from `underperformance_advisory` in the JSON,
  (c) diff the two sets, (d) collect console errors.

## What rendered

| card | badge text | tooltip | border |
|---|---|---|---|
| quality_cbop | `P(edge>0) 96% over 70d` | Advisory: P(true Sharpe of the whole realized record > 0). Not a rule. | `var(--text-muted)` |
| short_interest_ratio | `trailing window weak · P(edge>0) 0% over 70d` | Trailing 60-day Sharpe -7.55 — the retired auto-park rule would have fired here. Advisory only; a 60-day Sharpe has a standard error of ~2.0. | `var(--status-warning)` |
| NVDA momentum_v1 (pairs panel) | `trailing window weak · P(edge>0) 6% over 70d` | Trailing 60-day Sharpe -2.00 — … | `var(--status-warning)` |

Expected-from-API set: the same three strings. MISSING: [] EXTRA: [].
Registrations below the floor (lazy_prices, crypto, retired noa_neutral,
the 1-day pairs rows) rendered no badge, as designed.

Console errors: exactly two, both `401` on `GET /api/auth/me` BEFORE login
(the app's session probe, doubled by React StrictMode in dev). Not the
badge path; identical on main without this change.

## Observation, not fixed here

In the narrow cross-sectional card header the flagged badge wraps to three
lines (`trailing window weak · / P(edge>0) 0% / over 70d`). Cosmetic;
readable; left as-is so this record stays a check, not a change.

## Reproduction

Scripts lived in the session scratchpad (`badge_prep.py`, `badge_server.py`,
`badge_check.mjs`); the method above is complete enough to redo them. The
full-page screenshot was inspected by the merger; not committed (4475 px
PNG of synthetic data adds nothing the table does not).
