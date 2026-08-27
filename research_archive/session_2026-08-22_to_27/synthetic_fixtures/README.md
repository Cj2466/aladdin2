# Synthetic fixtures — NOT real research results

Everything in this directory is **fabricated data used to verify code changes
don't alter behavior**, not output from a real backtest against real market
data. It was moved here 2026-08-27 after an adversarial-verification pass
found that an unrelated analysis (empirical-Bayes shrinkage over this
project's real trial population) had ingested `POST.json` as if it were a
genuine cross-sectional family result — it isn't, and the mistake produced a
fabricated "positive finding" (round_c/buyback) that dissolved once traced
back to its source. See the session transcript around 2026-08-27 for the
full story.

## What's actually in here

- **`PRE.json`, `PRE2.json`, `POST.json`, `POST2.json`** — byte-identical
  (md5 `aaf90c340f9bf22946bad22730e92538`, confirmed). Output of
  `indep_regress.py`, run once before and once after a code change, to prove
  the change was a no-op. All four were generated from **`SEED = 777001`, 60
  fake tickers (`T00`..`T59`), synthetic price panels** — never real market
  data, never a real ticker.
- **`indep_regress.py`, `regression_check.py`** — the generator scripts.
  Both say so themselves in their own docstrings ("offline synthetic data
  (fake providers...)", "Runs on both the pre-fix and post-fix trees").

## The rule going forward

Any future ingestion of `research_archive/` for real analysis (shrinkage,
meta-correction, anything treating trial statistics as evidence about real
markets) must exclude this directory. If you're writing a script that walks
`research_archive/` for result files, either skip `*/synthetic_fixtures/*`
explicitly or — better — only read from an allowlist of files you've
confirmed are real. Filename alone does not distinguish a real result from a
synthetic one; `POST.json`'s name gave no hint.
