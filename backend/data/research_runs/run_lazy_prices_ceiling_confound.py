"""THE DECISIVE CONFOUND TEST for lazy_jaccard_full_h126_ivol.

QUESTION. Jaccard similarity over unique-vocabulary SETS is mathematically
bounded above by the vocabulary-size ratio:

    J(A,B) = |A n B| / |A u B|  <=  min(|A|,|B|) / max(|A|,|B|)

because |A n B| <= min(|A|,|B|) and |A u B| >= max(|A|,|B|). Call the
right-hand side the VOCABULARY-SIZE CEILING. It contains no information about
WHICH words changed -- only about how much the filing's unique-word count
grew or shrank. If a cross-sectional sort on the ceiling ALONE reproduces the
registered spec's Sharpe, then the registered spec is largely a
document-vocabulary-growth confound wearing a text-similarity costume, which
is structurally the same defect that got si_dtc rejected.

WHAT THIS SCRIPT DOES, in one sentence: it rebuilds the family's REAL
2015-2026 production panel from real SEC EDGAR filing text, adds a third
"metric" that is nothing but the vocabulary ceiling, and replays it through
the SAME run_cross_sectional_backtest path, the SAME spec parameters and the
SAME 36-trial DSR denominator as the registered spec.

REUSE, NOT REIMPLEMENTATION. Every piece of the pipeline is the family's own:
build_filing_index / get_filing_text (provider), pair_same_type_filings,
term_counts, scope_text, availability_date, build_similarity_observations,
build_similarity_panel, build_inverse_vol_basis, build_edge_half_spread_frame,
screen_lazy_prices_family, run_cross_sectional_backtest, compute_deflated_sharpe.
The ONE local addition is `vocab_ceiling_ratio`, injected into the family's
own _METRIC_FUNCTIONS registry so that build_similarity_observations computes
it with byte-identical tokenization, pairing and point-in-time dating to
Jaccard's. The injection is deliberately made HERE, in a research runner, and
NOT in the production module: LAZY_PRICES_METRICS is a frozen pre-registered
axis whose length sets the family's DSR denominator, and a confound probe is
not a new pre-registered spec.

Two stages, because stage A is thousands of real EDGAR document fetches and
must not be repeated while the analysis is iterated:
    --stage data     fetch + tokenize + build every panel, pickle the result
    --stage analyze  replay, diagnose, persist, report

Run from backend/ with the main worktree's ./venv/bin/python. The analyze
stage both READS the authoritative 2026-09-01 rows and WRITES its own, so it
must be pointed at the real database rather than a per-worktree empty one:

    DATABASE_URL="sqlite:////Users/.../aladdin2/backend/aladdin2.db" \
        ./venv/bin/python data/research_runs/run_lazy_prices_ceiling_confound.py \
        --stage analyze
"""

import argparse
import logging
import pickle
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path

# WORKTREE BINDING GUARD -- load-bearing, not boilerplate. Running this file by
# path puts data/research_runs/ on sys.path[0], NOT backend/, and the venv used
# to launch it belongs to the MAIN worktree, whose site-packages resolves `app`
# to the MAIN worktree's backend/app. Without the lines below this runner would
# silently screen main's code instead of this branch's, with no error at all.
# (Copied from run_short_interest.py, which carries the same guard.)
_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

import app

if Path(app.__file__).resolve().parent.parent != _BACKEND:
    raise SystemExit(
        f"REFUSING TO RUN: `app` resolved to {app.__file__}, which is not inside this worktree "
        f"({_BACKEND}). The screen would have run against another checkout's code."
    )

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from app.services.market_data.edgar_filing_text_provider import (
    EdgarFilingTextProvider,
    FilingIndexReport,
    load_filing_index,
    save_filing_index,
)
from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab import cross_sectional_lazy_prices as lp
from app.services.research_lab.cross_sectional import (
    MIN_REPLAY_TRADING_DAYS,
    CrossSectionalData,
    run_cross_sectional_backtest,
)
from app.services.research_lab.deflated_sharpe import compute_deflated_sharpe
from app.services.research_lab.metrics import sharpe_ratio
from app.services.research_lab.sp500_membership_history import (
    MEMBERSHIP_DATA_START,
    get_universe_over,
)
from app.services.research_lab.spread_estimator import build_edge_half_spread_frame

# --- the window of the committed production run, restated exactly ------------
# data/research_runs/lazy_prices_2026-09-01.txt section 2: "768 point-in-time
# S&P 500 tickers over 2015-01-07..2026-08-31", realized close index
# 2015-01-07..2026-08-28, 2926 trading days per spec.
RUN_START = MEMBERSHIP_DATA_START  # 2015-01-07
RUN_END = date(2026, 8, 31)

RUN_TAG = "lazy_prices_ceiling_confound_2026-09-03"
CEILING_METRIC = "vocab_ceiling"

# The registered spec under test.
REGISTERED_PATTERN_ID = "lazy_jaccard_full_h126_ivol"
REGISTERED_SHARPE = 0.6035
REGISTERED_DSR = 0.7540

SCRATCH = Path(
    "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/"
    "142109e4-1c17-421d-b8eb-cdbe7ecaf779/scratchpad"
)
PANEL_PICKLE = SCRATCH / "lazy_ceiling_panels.pkl"
FILING_INDEX_PATH = SCRATCH / "lazy_ceiling_filing_index.json"

# --smoke N truncates the universe to N tickers and writes to its own artifacts,
# so the whole path can be exercised end to end in a couple of minutes before
# the real multi-hour EDGAR pass is launched. A smoke run is NEVER persisted to
# the trial-results table and its numbers are never reported as results.
SMOKE_LIMIT: int | None = None
PERSIST = True

# The gitignored, refetchable EDGAR narrative-text cache. Stated explicitly and
# pointed at the MAIN worktree's copy rather than left to a per-worktree
# default: it is vendor input, not results, an archived filing is immutable, and
# ~0.6GB of it should be built once and shared, not once per branch.
SHARED_TEXT_CACHE = Path(
    "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend/data/edgar_filing_text/v1"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("ceiling_confound")


# --- the confound variable ---------------------------------------------------


def vocab_ceiling_ratio(a: Counter, b: Counter) -> float:
    """min(|A|,|B|) / max(|A|,|B|) over the two documents' UNIQUE-TERM sets --
    the mathematical upper bound on jaccard_similarity(a, b), and NOTHING
    ELSE.

    Deliberately shaped as a drop-in for the family's own metric functions
    (same Counter-in/float-out signature, same NaN-on-empty contract as
    jaccard_similarity) so build_similarity_observations can compute it with
    byte-identical tokenization, same-type pairing and availability dating.

    It reads only SET SIZES. Which words are shared, which appeared and which
    vanished is information this function cannot see. So a cross-sectional
    sort on it is a sort on 'did this filer's vocabulary stay the same size',
    which is the null the registered spec must beat to be about LANGUAGE at
    all."""
    set_a, set_b = set(a), set(b)
    if not set_a or not set_b:
        return float("nan")
    n_a, n_b = len(set_a), len(set_b)
    return min(n_a, n_b) / max(n_a, n_b)


def _install_ceiling_metric() -> None:
    """Register the probe in the family's own metric registry.

    Mutating a module-level private dict is not something to do lightly, so:
    it is done in a RESEARCH RUNNER, at import-free call time, and it ADDS a
    key rather than replacing one, so 'cosine' and 'jaccard' still resolve to
    the exact functions the production run used. The alternative -- adding
    'vocab_ceiling' to LAZY_PRICES_METRICS -- would change a frozen
    pre-registered axis and, through LAZY_PRICES_N_TRIALS, every future run's
    DSR denominator. That would be a far worse trade than this."""
    lp._METRIC_FUNCTIONS[CEILING_METRIC] = vocab_ceiling_ratio


# --- stage A: the real panel --------------------------------------------------


def stage_data() -> None:
    t0 = time.time()
    _install_ceiling_metric()

    provider = YFinanceProvider()
    text_provider = EdgarFilingTextProvider(cache_dir=SHARED_TEXT_CACHE)

    universe = get_universe_over(RUN_START, RUN_END)
    logger.info("point-in-time universe over %s..%s: %d tickers", RUN_START, RUN_END, len(universe))
    if SMOKE_LIMIT is not None:
        universe = set(sorted(universe)[:SMOKE_LIMIT])
        logger.warning("SMOKE RUN -- universe truncated to %d tickers, NOT a result", len(universe))

    frames, missing = provider.get_daily_ohlcv(sorted(universe), RUN_START, RUN_END)
    if not frames:
        raise SystemExit("no price history resolved -- data failure, not a finding")
    close = frames["close"]
    priced = list(close.columns)
    logger.info(
        "priced %d/%d tickers; close index %s..%s (%d rows)",
        len(priced),
        len(universe),
        close.index[0].date(),
        close.index[-1].date(),
        len(close.index),
    )

    cached = load_filing_index(FILING_INDEX_PATH)
    if cached is not None:
        filing_index, filing_report = cached
        logger.info("reusing saved filing index (%d tickers)", len(filing_index))
    else:
        filing_index, filing_report = text_provider.build_filing_index(
            priced, forms=lp.LAZY_PRICES_FORMS
        )
        save_filing_index(filing_index, filing_report, FILING_INDEX_PATH)
    if filing_report is None:
        filing_report = FilingIndexReport(n_tickers_requested=len(priced))
    logger.info(
        "filing index: cik_resolved=%d indexed=%d older_pages=%d filings_listed=%d",
        filing_report.n_tickers_cik_resolved,
        filing_report.n_tickers_indexed,
        filing_report.n_older_pages_fetched,
        filing_report.n_filings_listed,
    )

    # run_lazy_prices_screening's own warm-up trim, restated identically.
    warmup_floor = RUN_START.toordinal() - lp.LAZY_PRICES_FILING_WARMUP_DAYS
    trimmed = {
        ticker: [f for f in filings if f.filing_date.toordinal() >= warmup_floor]
        for ticker, filings in filing_index.items()
        if ticker in close.columns
    }
    logger.info("filings inside warm-up horizon: %d", sum(len(v) for v in trimmed.values()))

    metrics = (*lp.LAZY_PRICES_METRICS, CEILING_METRIC)
    observations, similarity_report = lp.build_similarity_observations(
        text_provider, trimmed, metrics=metrics, scopes=lp.LAZY_PRICES_SCOPES
    )
    logger.info(
        "pairs=%d scored=%s section_missing=%s fetch_failures=%d (docs fetched %d, from cache %d)",
        similarity_report.n_pairs,
        similarity_report.n_pairs_scored,
        similarity_report.n_pairs_section_missing,
        similarity_report.n_text_fetch_failures,
        text_provider.n_documents_fetched,
        text_provider.n_documents_from_cache,
    )

    panels: dict[tuple[str, str], pd.DataFrame] = {}
    ages: dict[tuple[str, str], pd.DataFrame] = {}
    dispersion: list[lp.ScopeDispersion] = []
    for (metric, scope), by_ticker in observations.items():
        panel, age, _unusable = lp.build_similarity_panel(close, by_ticker)
        panels[(metric, scope)] = panel
        ages[(metric, scope)] = age
        dispersion.append(lp.compute_scope_dispersion(metric, scope, panel, age))

    half_spread = build_edge_half_spread_frame(
        frames["open"], frames["high"], frames["low"], close
    )
    leg_weight_basis = lp.build_inverse_vol_basis(close)

    payload = {
        "close": close,
        "panels": panels,
        "ages": ages,
        "half_spread": half_spread,
        "leg_weight_basis": leg_weight_basis,
        "dispersion": dispersion,
        "observations_full": {
            m: observations[(m, "full")] for m in ("jaccard", CEILING_METRIC)
        },
        "universe_size": len(universe),
        "priced": priced,
        "missing_price_tickers": sorted(missing),
        "filing_report": filing_report,
        "similarity_report": similarity_report,
        "elapsed_seconds": time.time() - t0,
    }
    PANEL_PICKLE.parent.mkdir(parents=True, exist_ok=True)
    with PANEL_PICKLE.open("wb") as handle:
        pickle.dump(payload, handle, protocol=pickle.HIGHEST_PROTOCOL)
    logger.info("stage data done in %.1f min -> %s", (time.time() - t0) / 60.0, PANEL_PICKLE)


# --- stage B: replay + diagnose ----------------------------------------------


def _load_committed_rows() -> dict[str, tuple[float, float]]:
    """{pattern_id: (sharpe, dsr)} for the 2026-09-01 production run, read
    from the authoritative persisted table rather than from the git-tracked
    text summary of it."""
    from sqlalchemy import text as sql_text

    from app.db import SessionLocal

    db = SessionLocal()
    try:
        rows = db.execute(
            sql_text(
                "SELECT trial_id, sharpe_annualized, dsr FROM cross_sectional_trial_results "
                "WHERE run_tag = :tag"
            ),
            {"tag": "lazy_prices_2026-09-01"},
        ).all()
    except Exception as exc:  # noqa: BLE001 — a missing local DB is not a result
        logger.warning("could not read committed trial rows: %s", exc)
        return {}
    finally:
        db.close()
    return {r[0]: (float(r[1]), float(r[2])) for r in rows if r[1] is not None and r[2] is not None}


def _replay(close, panel, spec, config, half_spread, leg_weight_basis):
    data = CrossSectionalData(
        close=close,
        fundamental_signal=panel,
        half_spread=half_spread,
        leg_weight_basis=leg_weight_basis,
    )
    return run_cross_sectional_backtest(data, spec, config, None)


def stage_analyze() -> None:
    _install_ceiling_metric()
    with PANEL_PICKLE.open("rb") as handle:
        payload = pickle.load(handle)

    close = payload["close"]
    panels = payload["panels"]
    half_spread = payload["half_spread"]
    leg_weight_basis = payload["leg_weight_basis"]

    config = lp.default_lazy_prices_config()
    config.formation_start = RUN_START

    out: list[str] = []
    add = out.append

    # --- 1. reproduce the committed 36-spec family (the control) -------------
    family_results = lp.screen_lazy_prices_family(
        close,
        {k: v for k, v in panels.items() if k[0] in lp.LAZY_PRICES_METRICS},
        config,
        half_spread=half_spread,
        leg_weight_basis=leg_weight_basis,
    )
    by_id = {r.pattern_id: r for r in family_results}
    sharpes_36 = [r.sharpe_annualized for r in family_results]
    sigma_sr_36 = float(np.std(sharpes_36, ddof=1)) if len(sharpes_36) >= 2 else None

    add("=" * 78)
    add("A. REPRODUCTION OF THE COMMITTED 36-SPEC FAMILY (the control)")
    add("=" * 78)
    add(
        f"specs replayed: {len(family_results)}  sigma_sr = "
        f"{'n/a' if sigma_sr_36 is None else format(sigma_sr_36, '.4f')}"
    )
    add(f"{'pattern_id':34s} {'Sharpe':>9s} {'DSR':>8s} {'PSR':>8s} {'forms':>6s} {'days':>6s}")
    for r in family_results:
        d = r.deflated_sharpe
        add(
            f"{r.pattern_id:34s} {r.sharpe_annualized:+9.4f} "
            f"{(d.dsr if d and d.dsr is not None else float('nan')):8.4f} "
            f"{(d.psr_vs_zero if d and d.psr_vs_zero is not None else float('nan')):8.4f} "
            f"{r.n_formations:6d} {r.n_trading_days:6d}"
        )
    # Diffed against the PERSISTED rows, not against the text report: the
    # sqlite table is the authoritative record of the 2026-09-01 run (the run
    # report says so itself), so this is the reproduction check with teeth.
    committed = _load_committed_rows()
    if committed:
        add("")
        add("REPRODUCTION DIFF vs the persisted cross_sectional_trial_results rows")
        add(f"  (run_tag lazy_prices_2026-09-01, {len(committed)} rows)")
        worst_sharpe = worst_dsr = 0.0
        n_matched = 0
        for pid, (c_sharpe, c_dsr) in sorted(committed.items()):
            got = by_id.get(pid)
            if got is None:
                add(f"  {pid:34s} MISSING from this reproduction")
                continue
            n_matched += 1
            d_s = got.sharpe_annualized - c_sharpe
            d_d = (got.deflated_sharpe.dsr or float("nan")) - c_dsr
            worst_sharpe = max(worst_sharpe, abs(d_s))
            worst_dsr = max(worst_dsr, abs(d_d) if np.isfinite(d_d) else 0.0)
        add(
            f"  {n_matched}/{len(committed)} pattern_ids matched; largest |delta Sharpe| "
            f"{worst_sharpe:.6f}, largest |delta DSR| {worst_dsr:.6f}"
        )
        add(
            "  sigma_sr: reproduced "
            f"{'n/a' if sigma_sr_36 is None else format(sigma_sr_36, '.7f')} "
            "vs committed 0.1871290"
        )

    reg = by_id.get(REGISTERED_PATTERN_ID)
    add("")
    if reg is None:
        add(f"!! {REGISTERED_PATTERN_ID} DID NOT REPLAY -- reproduction failed, stop here.")
    else:
        add(
            f"REGISTERED SPEC {REGISTERED_PATTERN_ID}: reproduced Sharpe "
            f"{reg.sharpe_annualized:+.4f} / DSR {reg.deflated_sharpe.dsr:.4f} "
            f"vs committed {REGISTERED_SHARPE:+.4f} / {REGISTERED_DSR:.4f} "
            f"(deltas {reg.sharpe_annualized - REGISTERED_SHARPE:+.4f} / "
            f"{reg.deflated_sharpe.dsr - REGISTERED_DSR:+.4f})"
        )

    # --- 2. the ceiling-only signal, same specs, same denominator -----------
    add("")
    add("=" * 78)
    add("B. THE CEILING-ONLY SIGNAL -- same universe, same specs, same denominator")
    add("=" * 78)
    ceiling_panel = panels[(CEILING_METRIC, "full")]
    ceiling_rows = []
    for spec in lp.specs_for_panel("jaccard", "full"):
        replay = _replay(close, ceiling_panel, spec, config, half_spread, leg_weight_basis)
        if replay.status != "ok" or len(replay.daily_returns) < MIN_REPLAY_TRADING_DAYS:
            add(f"  {spec.pattern_id}: NOT REPLAYABLE ({replay.status})")
            continue
        sharpe = sharpe_ratio(replay.daily_returns, periods_per_year=config.periods_per_year)
        # SAME DSR denominator as the registered spec's 0.7540: n_trials=36 and
        # the sigma_sr of the 36 real specs. That is what makes the two numbers
        # comparable at all.
        dsr = compute_deflated_sharpe(
            sharpe,
            replay.daily_returns,
            lp.LAZY_PRICES_N_TRIALS,
            sigma_sr_36,
            periods_per_year=config.periods_per_year,
        )
        formed = [f for f in replay.formations if f.skipped_reason is None]
        ceiling_rows.append(
            {
                "pattern_id": spec.pattern_id.replace("lazy_jaccard_", "ceiling_"),
                "sharpe": sharpe,
                "dsr": dsr,
                "n_formations": len(formed),
                "n_days": len(replay.daily_returns),
                "replay": replay,
                "spec": spec,
            }
        )

    add(f"{'ceiling spec':34s} {'Sharpe':>9s} {'DSR':>8s} {'PSR':>8s} {'forms':>6s} {'days':>6s}")
    for row in sorted(ceiling_rows, key=lambda r: -r["sharpe"]):
        d = row["dsr"]
        add(
            f"{row['pattern_id']:34s} {row['sharpe']:+9.4f} "
            f"{(d.dsr if d.dsr is not None else float('nan')):8.4f} "
            f"{(d.psr_vs_zero if d.psr_vs_zero is not None else float('nan')):8.4f} "
            f"{row['n_formations']:6d} {row['n_days']:6d}"
        )

    head_to_head = next(
        (r for r in ceiling_rows if r["pattern_id"] == "ceiling_full_h126_ivol"), None
    )
    add("")
    if head_to_head is not None and reg is not None:
        ratio = (
            head_to_head["sharpe"] / reg.sharpe_annualized
            if reg.sharpe_annualized != 0
            else float("nan")
        )
        add(
            "HEAD TO HEAD, identical spec parameters (h126, inverse_vol, quintiles, long_short):"
        )
        add(
            f"  registered jaccard : Sharpe {reg.sharpe_annualized:+.4f}  "
            f"DSR {reg.deflated_sharpe.dsr:.4f}"
        )
        add(
            f"  ceiling-only       : Sharpe {head_to_head['sharpe']:+.4f}  "
            f"DSR {(head_to_head['dsr'].dsr if head_to_head['dsr'].dsr is not None else float('nan')):.4f}"
        )
        add(f"  ceiling / jaccard Sharpe ratio = {ratio:+.3f}")

    # --- 2b. Jaccard ORTHOGONALIZED to the ceiling ---------------------------
    # The complement of the ceiling-only test, and the more informative half
    # if the ceiling-only leg turns out weak: strip out of Jaccard everything
    # the vocabulary ceiling can linearly explain WITHIN each formation's own
    # cross-section, and re-run. A residual signal that keeps the registered
    # spec's Sharpe says the edge lives in WHICH words changed; a residual
    # that loses it says the edge lived in the set-size ratio all along.
    #
    # POINT-IN-TIME SAFE BY CONSTRUCTION: the regression is fitted per ROW,
    # across names, using only that row's own two panels. No future row and no
    # pooled/corpus-wide fit enters any cell — the same reasoning
    # cross_sectional_quality_neutral's industry demeaning relies on, and the
    # reason the family refuses TF-IDF.
    jac_panel = panels[("jaccard", "full")]
    cei_panel = panels[(CEILING_METRIC, "full")]
    resid = pd.DataFrame(
        np.nan, index=jac_panel.index, columns=jac_panel.columns, dtype=float
    )
    n_resid_rows = 0
    for ts in jac_panel.index:
        y = jac_panel.loc[ts].to_numpy(dtype=float)
        x = cei_panel.loc[ts].to_numpy(dtype=float)
        m = np.isfinite(y) & np.isfinite(x)
        if m.sum() < 25:  # below the family's own rankable floor anyway
            continue
        slope, intercept = np.polyfit(x[m], y[m], 1)
        resid.loc[ts, jac_panel.columns[m]] = y[m] - (slope * x[m] + intercept)
        n_resid_rows += 1

    add("")
    add("=" * 78)
    add("B2. JACCARD ORTHOGONALIZED TO THE CEILING (per-formation cross-sectional")
    add("    residual) -- same specs, same denominator")
    add("=" * 78)
    add(f"rows with a fitted cross-sectional residual: {n_resid_rows} of {len(jac_panel.index)}")
    resid_rows = []
    for spec in lp.specs_for_panel("jaccard", "full"):
        replay = _replay(close, resid, spec, config, half_spread, leg_weight_basis)
        if replay.status != "ok" or len(replay.daily_returns) < MIN_REPLAY_TRADING_DAYS:
            add(f"  {spec.pattern_id}: NOT REPLAYABLE ({replay.status})")
            continue
        sharpe = sharpe_ratio(replay.daily_returns, periods_per_year=config.periods_per_year)
        dsr = compute_deflated_sharpe(
            sharpe,
            replay.daily_returns,
            lp.LAZY_PRICES_N_TRIALS,
            sigma_sr_36,
            periods_per_year=config.periods_per_year,
        )
        resid_rows.append(
            {
                "pattern_id": spec.pattern_id.replace("lazy_jaccard_", "resid_"),
                "sharpe": sharpe,
                "dsr": dsr,
                "n_formations": len([f for f in replay.formations if f.skipped_reason is None]),
                "n_days": len(replay.daily_returns),
                "replay": replay,
            }
        )
    add(f"{'residual spec':34s} {'Sharpe':>9s} {'DSR':>8s} {'PSR':>8s} {'forms':>6s} {'days':>6s}")
    for row in sorted(resid_rows, key=lambda r: -r["sharpe"]):
        d = row["dsr"]
        add(
            f"{row['pattern_id']:34s} {row['sharpe']:+9.4f} "
            f"{(d.dsr if d.dsr is not None else float('nan')):8.4f} "
            f"{(d.psr_vs_zero if d.psr_vs_zero is not None else float('nan')):8.4f} "
            f"{row['n_formations']:6d} {row['n_days']:6d}"
        )

    # --- 2c. the ANALYTIC decomposition, which is stronger than 2b ----------
    # Jaccard is an exact function of exactly two things, and they can be
    # separated in closed form rather than by regression. Write m =
    # min(|A|,|B|), M = max(|A|,|B|), i = |A n B|. Then
    #
    #     J = i / (|A| + |B| - i)          and      c = m / M
    #
    # so |A| + |B| = m + M = m(1 + 1/c), i = J(|A| + |B|)/(1 + J), and
    #
    #     o == i / m = J (1 + 1/c) / (1 + J)
    #
    # o is the CONTAINMENT RATIO: the fraction of the SMALLER filing's
    # vocabulary that also appears in the larger one. It is 1.0 whenever one
    # vocabulary contains the other, no matter how different their sizes are,
    # and it falls only when terms were genuinely DROPPED rather than merely
    # added. So (c, o) is a complete, exact reparameterization of Jaccard into
    # "how much did the vocabulary change SIZE" and "how much of it was
    # REPLACED" — and, crucially, o is computable cell-by-cell from the two
    # panels already built, with no second pass over 7,785 documents.
    #
    # Verified below on the panels themselves rather than trusted: J is
    # reconstructed from (c, o) and the largest cell error is reported.
    ceil_p = panels[(CEILING_METRIC, "full")]
    jac_p = panels[("jaccard", "full")]
    with np.errstate(divide="ignore", invalid="ignore"):
        containment = jac_p * (1.0 + 1.0 / ceil_p) / (1.0 + jac_p)
        # round-trip: J = o*m / (m + M - o*m) = o / (1 + 1/c - o)
        rebuilt = containment / (1.0 + 1.0 / ceil_p - containment)
    err = (rebuilt - jac_p).abs().to_numpy(dtype=float)
    err = err[np.isfinite(err)]

    add("")
    add("=" * 78)
    add("B3. THE ANALYTIC DECOMPOSITION: Jaccard = f(vocabulary ceiling,")
    add("    CONTAINMENT ratio). The containment half, replayed alone.")
    add("=" * 78)
    add(
        f"round-trip check (J rebuilt from (ceiling, containment)): largest absolute "
        f"cell error {err.max():.3e} over {err.size:,} cells"
    )
    cvals = containment.to_numpy(dtype=float).ravel()
    cvals = cvals[np.isfinite(cvals)]
    add(
        f"containment ratio: mean {cvals.mean():.5f} sd {cvals.std(ddof=1):.5f} "
        f"p10 {np.quantile(cvals, 0.10):.5f} p50 {np.quantile(cvals, 0.50):.5f} "
        f"p90 {np.quantile(cvals, 0.90):.5f} max {cvals.max():.5f}"
    )
    contain_rows = []
    for spec in lp.specs_for_panel("jaccard", "full"):
        replay = _replay(close, containment, spec, config, half_spread, leg_weight_basis)
        if replay.status != "ok" or len(replay.daily_returns) < MIN_REPLAY_TRADING_DAYS:
            add(f"  {spec.pattern_id}: NOT REPLAYABLE ({replay.status})")
            continue
        sharpe = sharpe_ratio(replay.daily_returns, periods_per_year=config.periods_per_year)
        dsr = compute_deflated_sharpe(
            sharpe,
            replay.daily_returns,
            lp.LAZY_PRICES_N_TRIALS,
            sigma_sr_36,
            periods_per_year=config.periods_per_year,
        )
        contain_rows.append(
            {
                "pattern_id": spec.pattern_id.replace("lazy_jaccard_", "contain_"),
                "sharpe": sharpe,
                "dsr": dsr,
                "n_formations": len([f for f in replay.formations if f.skipped_reason is None]),
                "n_days": len(replay.daily_returns),
                "replay": replay,
            }
        )
    add(f"{'containment spec':34s} {'Sharpe':>9s} {'DSR':>8s} {'PSR':>8s} {'forms':>6s} {'days':>6s}")
    for row in sorted(contain_rows, key=lambda r: -r["sharpe"]):
        d = row["dsr"]
        add(
            f"{row['pattern_id']:34s} {row['sharpe']:+9.4f} "
            f"{(d.dsr if d.dsr is not None else float('nan')):8.4f} "
            f"{(d.psr_vs_zero if d.psr_vs_zero is not None else float('nan')):8.4f} "
            f"{row['n_formations']:6d} {row['n_days']:6d}"
        )
    cm = np.isfinite(containment.to_numpy(dtype=float).ravel()) & np.isfinite(
        ceil_p.to_numpy(dtype=float).ravel()
    )
    add(
        "  Spearman rho(containment, ceiling) over all panel cells = "
        f"{spearmanr(containment.to_numpy(dtype=float).ravel()[cm], ceil_p.to_numpy(dtype=float).ravel()[cm]).statistic:+.4f}"
    )

    # --- 3. how close are the two signals, on the FULL panel ----------------
    add("")
    add("=" * 78)
    add("C. RANK AGREEMENT BETWEEN JACCARD AND ITS CEILING, ON THE FULL PANEL")
    add("=" * 78)
    jac = panels[("jaccard", "full")]
    cei = ceiling_panel
    common_cols = [c for c in jac.columns if c in cei.columns]
    a = jac[common_cols].to_numpy(dtype=float).ravel()
    b = cei[common_cols].to_numpy(dtype=float).ravel()
    ok = np.isfinite(a) & np.isfinite(b)
    add(f"panel cells with both values: {int(ok.sum()):,} of {a.size:,}")
    add(f"  Spearman rho (all panel cells) = {spearmanr(a[ok], b[ok]).statistic:+.4f}")
    add(f"  Pearson  r   (all panel cells) = {float(np.corrcoef(a[ok], b[ok])[0, 1]):+.4f}"
        f"   R^2 = {float(np.corrcoef(a[ok], b[ok])[0, 1]) ** 2:.4f}")

    # observation level: one row per real filing pair, no step-frame repetition
    obs = payload["observations_full"]
    pair_j, pair_c = [], []
    for ticker, jrows in obs["jaccard"].items():
        crows = obs[CEILING_METRIC].get(ticker)
        if not crows:
            continue
        cmap = {(o.end, o.available): o.value for o in crows}
        for o in jrows:
            key = (o.end, o.available)
            if key in cmap:
                pair_j.append(o.value)
                pair_c.append(cmap[key])
    if len(pair_j) > 10:
        pj, pc = np.array(pair_j), np.array(pair_c)
        add(f"filing-pair observations matched: {len(pj):,}")
        add(f"  Spearman rho (per filing pair) = {spearmanr(pj, pc).statistic:+.4f}")
        r = float(np.corrcoef(pj, pc)[0, 1])
        add(f"  Pearson  r   (per filing pair) = {r:+.4f}   R^2 = {r * r:.4f}")
        slack = pc - pj
        add(
            f"  ceiling slack (ceiling - jaccard): mean {slack.mean():.4f} "
            f"sd {slack.std(ddof=1):.4f} min {slack.min():.4f} max {slack.max():.4f}"
        )

    # --- 3b. the same question, asked of the PROPOSED FALLBACK spec ---------
    # lazy_cosine_rf_h126_ivol (DSR 0.6305, the family's third-best) is the
    # spec a demotion would move to, on the argument that cosine is
    # frequency-weighted and therefore NOT subject to a set-size cap: it reads
    # raw term-count vectors and is invariant to each vector's magnitude, so
    # there is no min/max unique-vocabulary bound of the Jaccard kind. Stated
    # as maths that is right; measured here rather than asserted, because
    # "no analytic bound" does not by itself mean "empirically unrelated to
    # vocabulary size".
    add("")
    add("=" * 78)
    add("C2. THE SAME TEST ON THE PROPOSED FALLBACK: cosine/risk_factors vs the")
    add("    risk_factors vocabulary ceiling")
    add("=" * 78)
    cos_rf = panels.get(("cosine", "risk_factors"))
    cei_rf = panels.get((CEILING_METRIC, "risk_factors"))
    if cos_rf is not None and cei_rf is not None:
        cols_rf = [c for c in cos_rf.columns if c in cei_rf.columns]
        x = cos_rf[cols_rf].to_numpy(dtype=float).ravel()
        y = cei_rf[cols_rf].to_numpy(dtype=float).ravel()
        m = np.isfinite(x) & np.isfinite(y)
        r = float(np.corrcoef(x[m], y[m])[0, 1])
        add(f"panel cells with both values: {int(m.sum()):,}")
        add(f"  Spearman rho (cosine/rf vs rf ceiling) = {spearmanr(x[m], y[m]).statistic:+.4f}")
        add(f"  Pearson  r                             = {r:+.4f}   R^2 = {r * r:.4f}")
        # And the ceiling-only replay on the rf ceiling, against the same
        # denominator, so the fallback's own confound exposure is a number too.
        for spec in lp.specs_for_panel("cosine", "risk_factors"):
            if spec.pattern_id != "lazy_cosine_rf_h126_ivol":
                continue
            replay = _replay(close, cei_rf, spec, config, half_spread, leg_weight_basis)
            if replay.status != "ok" or len(replay.daily_returns) < MIN_REPLAY_TRADING_DAYS:
                add(f"  rf-ceiling-only replay: NOT REPLAYABLE ({replay.status})")
                break
            sharpe = sharpe_ratio(replay.daily_returns, periods_per_year=config.periods_per_year)
            dsr = compute_deflated_sharpe(
                sharpe,
                replay.daily_returns,
                lp.LAZY_PRICES_N_TRIALS,
                sigma_sr_36,
                periods_per_year=config.periods_per_year,
            )
            fallback_reg = by_id.get("lazy_cosine_rf_h126_ivol")
            add(
                f"  rf-ceiling-only, h126/ivol: Sharpe {sharpe:+.4f}  DSR "
                f"{(dsr.dsr if dsr.dsr is not None else float('nan')):.4f}"
            )
            if fallback_reg is not None:
                add(
                    f"  registered fallback candidate lazy_cosine_rf_h126_ivol: Sharpe "
                    f"{fallback_reg.sharpe_annualized:+.4f}  DSR "
                    f"{fallback_reg.deflated_sharpe.dsr:.4f}"
                )

    # --- 4. leg overlap at the real formation dates -------------------------
    add("")
    add("=" * 78)
    add("D. DO THE TWO SIGNALS TRADE THE SAME NAMES? (leg overlap at every")
    add("   formation of the registered spec)")
    add("=" * 78)
    if reg is not None and head_to_head is not None:
        jac_replay = _replay(
            close,
            jac,
            next(s for s in lp.specs_for_panel("jaccard", "full") if s.pattern_id == REGISTERED_PATTERN_ID),
            config,
            half_spread,
            leg_weight_basis,
        )
        cei_replay = head_to_head["replay"]
        jf = {f.date: f for f in jac_replay.formations if f.skipped_reason is None}
        cf = {f.date: f for f in cei_replay.formations if f.skipped_reason is None}
        shared_dates = sorted(set(jf) & set(cf))
        long_ov, short_ov, xs_rho = [], [], []
        add(f"{'formation':12s} {'long overlap':>13s} {'short overlap':>14s} {'xs Spearman':>12s}")
        for d in shared_dates:
            jl, js = set(jf[d].long_tickers), set(jf[d].short_tickers)
            cl, cs = set(cf[d].long_tickers), set(cf[d].short_tickers)
            lo = len(jl & cl) / len(jl) if jl else float("nan")
            so = len(js & cs) / len(js) if js else float("nan")
            long_ov.append(lo)
            short_ov.append(so)
            ts = pd.Timestamp(d)
            if ts in jac.index and ts in cei.index:
                rj = jac.loc[ts, common_cols].astype(float)
                rc = cei.loc[ts, common_cols].astype(float)
                m = np.isfinite(rj.to_numpy()) & np.isfinite(rc.to_numpy())
                if m.sum() > 10:
                    rho = spearmanr(rj.to_numpy()[m], rc.to_numpy()[m]).statistic
                    xs_rho.append(rho)
                else:
                    rho = float("nan")
            else:
                rho = float("nan")
            add(f"{d.date().isoformat():12s} {lo:13.3f} {so:14.3f} {rho:12.3f}")
        add("")
        add(
            f"MEAN over {len(shared_dates)} shared formations: long overlap "
            f"{float(np.nanmean(long_ov)):.3f}, short overlap {float(np.nanmean(short_ov)):.3f}, "
            f"cross-sectional Spearman {float(np.nanmean(xs_rho)):.3f}"
        )
        add(
            "  A quintile sort has a 0.20 chance baseline of putting any given name in a "
            "given leg, so overlap near 0.20 means the two signals pick largely different "
            "portfolios and overlap near 1.0 means they pick the same one."
        )
        # return correlation of the two strategies
        jr = jac_replay.daily_returns
        cr = cei_replay.daily_returns
        joined = pd.concat([jr.rename("jaccard"), cr.rename("ceiling")], axis=1).dropna()
        if len(joined) > 50:
            add(
                f"  daily net-return correlation of the two strategies over "
                f"{len(joined)} shared days = "
                f"{float(joined['jaccard'].corr(joined['ceiling'])):+.4f}"
            )
        # The same question for the containment half, which is the ceiling's
        # exact analytic complement: if the registered strategy IS the
        # containment strategy, that correlation is near 1.
        contain_h126 = next(
            (r for r in contain_rows if r["pattern_id"] == "contain_full_h126_ivol"), None
        )
        if contain_h126 is not None:
            joined_c = pd.concat(
                [
                    jr.rename("jaccard"),
                    contain_h126["replay"].daily_returns.rename("containment"),
                ],
                axis=1,
            ).dropna()
            if len(joined_c) > 50:
                add(
                    f"  daily net-return correlation jaccard vs CONTAINMENT over "
                    f"{len(joined_c)} shared days = "
                    f"{float(joined_c['jaccard'].corr(joined_c['containment'])):+.4f}"
                )
            cf2 = {
                f.date: f
                for f in contain_h126["replay"].formations
                if f.skipped_reason is None
            }
            ov_l, ov_s = [], []
            for d in sorted(set(jf) & set(cf2)):
                jl, js = set(jf[d].long_tickers), set(jf[d].short_tickers)
                kl, ks = set(cf2[d].long_tickers), set(cf2[d].short_tickers)
                if jl:
                    ov_l.append(len(jl & kl) / len(jl))
                if js:
                    ov_s.append(len(js & ks) / len(js))
            if ov_l:
                add(
                    f"  jaccard vs CONTAINMENT leg overlap: long "
                    f"{float(np.mean(ov_l)):.3f}, short {float(np.mean(ov_s)):.3f}"
                )

    # --- 5. dispersion, for the record --------------------------------------
    add("")
    add("=" * 78)
    add("E. REALIZED PANEL DISPERSION (all nine panels, ceiling included)")
    add("=" * 78)
    for d in sorted(payload["dispersion"], key=lambda x: (x.metric, x.scope)):
        add(
            f"  {d.metric:14s} {d.scope:13s} n={d.n_observations:7d} mean {d.mean:.5f} "
            f"sd {d.std:.5f} p10 {d.p10:.5f} p50 {d.p50:.5f} p90 {d.p90:.5f} "
            f"age {d.median_age_days:.0f}d"
        )

    add("")
    add("SAMPLE: " + payload["similarity_report"].__class__.__name__)
    sr = payload["similarity_report"]
    add(
        f"  universe {payload['universe_size']} -> priced {len(payload['priced'])}; "
        f"filings {sr.n_filings}, pairs {sr.n_pairs}, scored {sr.n_pairs_scored}, "
        f"section-missing {sr.n_pairs_section_missing}, text-fetch failures "
        f"{sr.n_text_fetch_failures}"
    )
    add(f"  close index {close.index[0].date()}..{close.index[-1].date()} ({len(close.index)} rows)")

    text = "\n".join(out)
    print(text)
    (SCRATCH / "ceiling_confound_report.txt").write_text(text)

    # --- 6. persist ----------------------------------------------------------
    # ALL EIGHTEEN probe replays, not just the ceiling six: this project's
    # standing rule is that every computed trial reaches a real table rather
    # than a scratchpad, and the containment and residual columns are the two
    # that carry the verdict's nuance. Re-running the analyze stage replaces
    # this run_tag's rows rather than duplicating them.
    if PERSIST and (ceiling_rows or contain_rows or resid_rows):
        from sqlalchemy import text as sql_text

        from app.db import SessionLocal
        from app.services.research_lab.cross_sectional import (
            CrossSectionalScreeningResult,
        )
        from app.services.research_lab.cross_sectional_persistence import (
            persist_cross_sectional_trial_results,
        )

        _CITATIONS = {
            "ceiling": (
                "vocabulary-size ceiling min(|A|,|B|)/max(|A|,|B|) over unique-term sets -- the "
                "analytic upper bound on Jaccard, replayed ALONE as the confound null"
            ),
            "contain": (
                "containment ratio |A n B|/min(|A|,|B|) = J(1+1/c)/(1+J) -- the exact analytic "
                "complement of the vocabulary ceiling in Jaccard, replayed ALONE"
            ),
            "resid": (
                "Jaccard minus its per-formation cross-sectional linear fit on the vocabulary "
                "ceiling -- the registered signal with the mechanical component removed"
            ),
        }

        def _to_result(r: dict) -> CrossSectionalScreeningResult:
            replay = r["replay"]
            formed = [f for f in replay.formations if f.skipped_reason is None]
            kind = r["pattern_id"].split("_", 1)[0]
            return CrossSectionalScreeningResult(
                pattern_id=r["pattern_id"],
                family="lazy_prices_vocab_ceiling_confound",
                citation=_CITATIONS[kind],
                n_formations=r["n_formations"],
                n_skipped_formations=len(replay.formations) - len(formed),
                avg_names_per_leg=(
                    float(np.mean([len(f.long_tickers) for f in formed])) if formed else 0.0
                ),
                n_trading_days=r["n_days"],
                sharpe_annualized=r["sharpe"],
                total_cost_drag=replay.total_cost,
                total_financing_drag=replay.total_financing_cost,
                deflated_sharpe=r["dsr"],
                total_turnover=float(sum(f.turnover for f in replay.formations)),
                edge_flat_fallback_notional=float(
                    sum(f.edge_flat_fallback_notional for f in replay.formations)
                ),
            )

        rows = [_to_result(r) for r in (*ceiling_rows, *contain_rows, *resid_rows)]
        db = SessionLocal()
        try:
            deleted = db.execute(
                sql_text("DELETE FROM cross_sectional_trial_results WHERE run_tag = :tag"),
                {"tag": RUN_TAG},
            ).rowcount
            db.commit()
            n = persist_cross_sectional_trial_results(
                db, "lazy_prices_vocab_ceiling_confound", rows, run_tag=RUN_TAG
            )
            logger.info(
                "persisted %d probe rows under run_tag=%s (replaced %d earlier rows)",
                n,
                RUN_TAG,
                deleted,
            )
        finally:
            db.close()


def main() -> None:
    global SMOKE_LIMIT, PANEL_PICKLE, FILING_INDEX_PATH, PERSIST
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("data", "analyze"), required=True)
    parser.add_argument(
        "--smoke",
        type=int,
        default=None,
        help="truncate the universe to N tickers and use separate artifacts; never persisted",
    )
    args = parser.parse_args()
    if args.smoke is not None:
        SMOKE_LIMIT = args.smoke
        PANEL_PICKLE = SCRATCH / "lazy_ceiling_panels_smoke.pkl"
        FILING_INDEX_PATH = SCRATCH / "lazy_ceiling_filing_index_smoke.json"
        PERSIST = False
    if args.stage == "data":
        stage_data()
    else:
        stage_analyze()


if __name__ == "__main__":
    main()
