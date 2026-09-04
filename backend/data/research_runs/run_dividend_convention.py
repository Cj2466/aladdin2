"""REPRODUCIBILITY SCRIPT for data/research_runs/dividend_convention_2026-09-04.txt
and its .json companion — the independent re-verification of Yahoo's
dividend-adjustment convention and the decision to make CRSP the default.

Every number in that report comes from one of the subcommands below. Run from
backend/ with PYTHONPATH=. and the venv's python.

  events     re-derive KDP 2018-07-10 and the three further special-dividend
             cases from a FRESH vendor fetch, and check each against Yahoo's
             own auto_adjust output
  sameday    dump every same-day split+distribution event in both
             point-in-time universes, with what each arm implies for that day
  crosscheck the as-traded reconstruction against externally-published
             historical closes, and the dividend-basis question
  scan       universe-wide corporate-action scan (writes
             dividend_convention_universe_scan.json)
  amplify    the r_YAHOO = r_CRSP/(1-D/P) property, measured on every
             distribution above 5% of price
  rollout    one arm of the three-arm family rollout
             (--arm yahoo|crsp_keep|crsp_drop [--families a,b,c])
  compare    diff the three arms spec by spec
  buildjson  assemble dividend_convention_2026-09-04.json

WHY THREE ARMS. The convention flag previously bundled TWO changes: the
return convention itself, and `drop_same_day_split_distributions`. They point
in opposite directions on the evidence, so they are measured separately:
  yahoo      r = P/(P_prev - D) - 1          (the pre-2026-09-04 default)
  crsp_keep  r = (P + D)/P_prev - 1          (the new default)
  crsp_drop  crsp_keep + same-day distributions discarded (NOT shipped)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

import app.services.market_data.price_store as ps_mod
from app.services.market_data.price_store import (
    AdjustmentConvention,
    PriceStore,
    cumulative_split_factor,
    total_return_close,
)
from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab import small_cap_membership_history as small
from app.services.research_lab import sp500_membership_history as sp
from app.services.research_lab.sp500_membership_history import MEMBERSHIP_DATA_START

OUT_DIR = Path(__file__).resolve().parent
START, END = date(2015, 1, 7), date(2026, 8, 31)


# ---------------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------------


def _fetch(ticker: str, start: str = "2015-01-07", end: str = "2026-08-31") -> pd.DataFrame:
    raw = yf.download(ticker, start=start, end=end, auto_adjust=False, actions=True,
                      progress=False, group_by="column")
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    raw.index = pd.DatetimeIndex(raw.index).tz_localize(None).normalize()
    return raw


def _as_traded(raw: pd.DataFrame) -> pd.DataFrame:
    fields = {
        "open": raw["Open"], "high": raw["High"], "low": raw["Low"],
        "close": raw["Close"], "volume": raw["Volume"],
        "dividend": raw.get("Dividends", pd.Series(0.0, index=raw.index)),
        "capital_gains": raw.get("Capital Gains", pd.Series(0.0, index=raw.index)),
    }
    return PriceStore.to_as_traded(fields, raw["Stock Splits"])


# ---------------------------------------------------------------------------
# events — section 1.1 / 1.1b of the report
# ---------------------------------------------------------------------------

# ticker, ex-date, published per-share distribution, source note
SPECIAL_DIVIDENDS = [
    ("KDP", "2018-07-10", 103.75,
     ("Dr Pepper Snapple / Keurig merger consideration; share retained 1:1. "
      "KDP release 2018-06-26; SEC 8-K CIK 0001418135 acc 0001104659-18-044357")),
    ("GEN", "2020-02-03", 12.00,
     ("NortonLifeLock $12.00 special dividend after the Broadcom enterprise sale; "
      "Business Wire 2020-01-09; SEC 8-K CIK 849399 acc 0001104659-20-002689")),
    ("BKR", "2017-07-05", 17.50,
     ("Baker Hughes: one BHGE Class A share plus $17.50 cash; "
      "Baker Hughes release 2017-07-03; SEC 8-K CIK 0001701605")),
    ("SHEN", "2021-08-03", 18.75,
     ("Shenandoah Telecom special dividend after the T-Mobile wireless sale; "
      "Shentel release 2021-07-02; SEC 8-K CIK 354963 acc 0001171843-21-004680")),
]


def cmd_events() -> None:
    for ticker, day, published, note in SPECIAL_DIVIDENDS:
        raw = _fetch(ticker)
        adj = yf.download(ticker, start="2015-01-07", end="2026-08-31", auto_adjust=True,
                          actions=False, progress=False, group_by="column")
        if isinstance(adj.columns, pd.MultiIndex):
            adj = adj.xs(ticker, axis=1, level=1)
        adj.index = pd.DatetimeIndex(adj.index).tz_localize(None).normalize()

        d = pd.Timestamp(day)
        prev = raw.index[raw.index < d][-1]
        frame = _as_traded(raw)
        p0, p1 = float(frame.loc[prev, "close"]), float(frame.loc[d, "close"])
        dv = float(frame.loc[d, "dividend"])
        k = dv / p0
        crsp = (p1 + dv) / p0 - 1.0
        yahoo = p1 / (p0 - dv) - 1.0
        vendor = float(adj["Close"].loc[d] / adj["Close"].loc[prev] - 1.0)
        print("=" * 78)
        print(f"{ticker} ex-date {day}   published distribution ${published}   [{note}]")
        print(f"  as-traded close {prev.date()} = {p0!r}")
        print(f"  as-traded close {d.date()} = {p1!r}")
        print(f"  recorded dividend = {dv!r}   split ratio = {float(frame.loc[d, 'split'])!r}")
        print(f"  D/P_prev = {k:.4%}")
        print(f"  CRSP  (P1+D)/P0-1     = {crsp:+.6%}   <- what a holder actually earned")
        print(f"  YAHOO P1/(P0-D)-1     = {yahoo:+.6%}")
        print(f"  Yahoo's own auto_adjust=True implied return = {vendor:+.6%}"
              f"   (agrees with YAHOO to {abs(vendor - yahoo):.2e})")
        print(f"  amplification 1/(1-D/P) = {1 / (1 - k):.4f}x ;"
              f" CRSP * that = {crsp / (1 - k):+.6%}")


# ---------------------------------------------------------------------------
# sameday — section 2 of the report
# ---------------------------------------------------------------------------

SAME_DAY_TICKERS = ["DHR", "DXC", "RILY", "SSP", "TR", "XRX"]


def cmd_sameday() -> None:
    store = PriceStore()
    for t in SAME_DAY_TICKERS:
        frame = store.read_ticker(t)
        if frame is None:
            print(f"{t}: not in store — run `scan` first")
            continue
        frame = frame.loc[(frame.index >= str(START)) & (frame.index <= str(END))]
        splits = pd.to_numeric(frame["split"], errors="coerce").fillna(0.0)
        divs = pd.to_numeric(frame["dividend"], errors="coerce").fillna(0.0)
        hits = frame.index[(~splits.isin([0.0, 1.0])) & (divs > 0)]
        print(f"\n--- {t}: {len(hits)} same-day split+distribution event(s)")
        for d in hits:
            prev = frame.index[frame.index < d][-1]
            p0, p1 = float(frame.loc[prev, "close"]), float(frame.loc[d, "close"])
            f, dv = float(frame.loc[d, "split"]), float(frame.loc[d, "dividend"])
            arms = {}
            for label, (conv, drop) in {
                "Y-keep": (AdjustmentConvention.YAHOO, False),
                "C-keep": (AdjustmentConvention.CRSP, False),
                "C-drop": (AdjustmentConvention.CRSP, True),
            }.items():
                s = total_return_close(frame, convention=conv,
                                       drop_same_day_split_distributions=drop)
                arms[label] = float(s.loc[d] / s.loc[prev] - 1.0)
            print(f"  {d.date()}  close {p0:9.4f} -> {p1:9.4f}  ratio={f!r}  "
                  f"dividend={dv!r} (D/P={dv / p0:.2%})")
            print(f"           split-implied distributed value = {p0 * (1 - 1 / f):.4f}")
            print("           " + "   ".join(f"{k}={v:+.4%}" for k, v in arms.items()))


# ---------------------------------------------------------------------------
# crosscheck — section 4 of the report
# ---------------------------------------------------------------------------

# Each published close is an externally-sourced historical fact; sources in
# section 4 of the report.
SPLIT_CHECKS = [
    ("AAPL", "2020-08-28", 499.23, "4-for-1 split effective 2020-08-31"),
    ("NVDA", "2024-06-07", 1208.88, "10-for-1 split effective 2024-06-10"),
    ("TSLA", "2022-08-24", 891.29, "3-for-1 split effective 2022-08-25"),
    ("XRX", "2017-01-03", 6.89, "closed -21.08% on the Conduent spin ex-date"),
    ("CNDT", "2017-01-03", 13.72, "Conduent's first regular-way close"),
    ("FTV", "2016-07-05", 48.60, "Fortive's first regular-way close"),
]

# ticker, ex-date, published per-share amount, cumulative factor expected
DIVIDEND_BASIS_CHECKS = [
    ("AAPL", "2020-08-07", 0.82),
    ("AAPL", "2014-05-08", 3.29),
]


def cmd_crosscheck() -> None:
    print("=" * 78)
    print("AS-TRADED RECONSTRUCTION vs EXTERNALLY-PUBLISHED CLOSES")
    print("=" * 78)
    for ticker, day, published, note in SPLIT_CHECKS:
        raw = _fetch(ticker, start="2014-01-01")
        frame = _as_traded(raw)
        d = pd.Timestamp(day)
        if d not in frame.index:
            print(f"{ticker:6s} {day}: no row")
            continue
        got = float(frame.loc[d, "close"])
        print(f"{ticker:6s} {day}  reconstructed {got:10.4f}   published {published:10.2f}   "
              f"|diff| {abs(got - published):.4f}   [{note}]")

    print()
    print("=" * 78)
    print("IS YAHOO'S `Dividends` COLUMN ON TODAY'S SPLIT BASIS?")
    print("=" * 78)
    for ticker, day, published in DIVIDEND_BASIS_CHECKS:
        raw = _fetch(ticker, start="2013-01-01")
        d = pd.Timestamp(day)
        stored = float(raw.loc[d, "Dividends"])
        factor = float(cumulative_split_factor(raw["Stock Splits"],
                                               pd.DatetimeIndex(raw.index)).loc[d])
        print(f"{ticker} {day}  declared ${published}   Yahoo holds {stored!r}   "
              f"cumulative factor {factor!r}")
        print(f"   today-basis hypothesis: {stored} * {factor} = {stored * factor:.6f}"
              f"   ({'CONFIRMED' if abs(stored * factor - published) < 1e-6 else 'REFUTED'})")


# ---------------------------------------------------------------------------
# scan — the universe-wide corporate-action scan
# ---------------------------------------------------------------------------

EXTRA_TICKERS = ["SPY", "^VIX", "TLT", "IEF", "SHY", "LQD", "HYG", "TIP", "GLD", "SLV",
                 "DBC", "USO", "UNG"]


def _universe() -> list[str]:
    tickers = set(sp.get_universe_over(START, END))
    tickers |= set(small.get_universe_over(date(2020, 1, 1), END))
    tickers |= set(EXTRA_TICKERS)
    return sorted(tickers)


def cmd_scan() -> None:
    tickers = _universe()
    print(f"universe: {len(tickers)} tickers", file=sys.stderr)
    YFinanceProvider().get_price_history(tickers, START, END)  # warm the store
    store = PriceStore()

    rows = []
    for t in tickers:
        frame = store.read_ticker(t)
        if frame is None or frame.empty:
            continue
        frame = frame.loc[(frame.index >= str(START)) & (frame.index <= str(END))]
        if len(frame) < 30:
            continue
        splits = pd.to_numeric(frame["split"], errors="coerce").fillna(0.0)
        divs = pd.to_numeric(frame["dividend"], errors="coerce").fillna(0.0)
        is_split = ~splits.isin([0.0, 1.0])
        same_day = frame.index[is_split & (divs > 0)]
        prev = pd.to_numeric(frame["close"], errors="coerce").shift(1)
        ratio = (divs / prev).replace([np.inf, -np.inf], np.nan)

        def wealth(conv: AdjustmentConvention, drop: bool, frame: pd.DataFrame = frame) -> float:
            v = total_return_close(frame, convention=conv,
                                   drop_same_day_split_distributions=drop).dropna()
            return float(v.iloc[-1] / v.iloc[0]) if len(v) > 1 and v.iloc[0] > 0 else np.nan

        wy = wealth(AdjustmentConvention.YAHOO, False)
        wc = wealth(AdjustmentConvention.CRSP, False)
        wd = wealth(AdjustmentConvention.YAHOO, True)
        wb = wealth(AdjustmentConvention.CRSP, True)
        rows.append({
            "ticker": t, "n": len(frame),
            "n_div": int((divs > 0).sum()), "n_split": int(is_split.sum()),
            "n_same_day": len(same_day),
            "same_day_dates": [str(d.date()) for d in same_day],
            "max_div_ratio": float(ratio.max()) if ratio.notna().any() else 0.0,
            "n_div_gt_1pct": int((ratio > 0.01).sum()),
            "n_div_gt_10pct": int((ratio > 0.10).sum()),
            "rel_conv_only": wc / wy - 1.0, "rel_drop_only": wd / wy - 1.0,
            "rel_full": wb / wy - 1.0,
        })

    df = pd.DataFrame(rows).set_index("ticker")
    df.to_json(OUT_DIR / "dividend_convention_universe_scan.json")
    print(f"scanned {len(df)} tickers, {int(df.n_div.sum())} distributions, "
          f"{int(df.n_split.sum())} splits")
    sd = df[df.n_same_day > 0]
    print(f"same-day split+distribution: {len(sd)} tickers, {int(sd.n_same_day.sum())} events")
    for t, r in sd.iterrows():
        print(f"  {t:6s} {r.same_day_dates}")
        print(f"         conv-only {r.rel_conv_only:+.4%}  drop-only {r.rel_drop_only:+.4%}  "
              f"both {r.rel_full:+.4%}")
    for label, col in (("convention only", "rel_conv_only"), ("convention+drop", "rel_full")):
        s = df[col].dropna()
        print(f"  {label:18s} median {s.median():+.6%}  p5 {s.quantile(0.05):+.4%}  "
              f"p95 {s.quantile(0.95):+.4%}  min {s.min():+.4%}  max {s.max():+.4%}")


# ---------------------------------------------------------------------------
# amplify — the closed form, measured
# ---------------------------------------------------------------------------


def cmd_amplify() -> None:
    store = PriceStore()
    rows = []
    for t in _universe():
        f = store.read_ticker(t)
        if f is None or f.empty:
            continue
        f = f.loc[(f.index >= str(START)) & (f.index <= str(END))]
        d = pd.to_numeric(f["dividend"], errors="coerce").fillna(0.0)
        c = pd.to_numeric(f["close"], errors="coerce")
        p = c.shift(1)
        sp_col = pd.to_numeric(f["split"], errors="coerce").fillna(0.0)
        ratio = (d / p).replace([np.inf, -np.inf], np.nan)
        for i in ratio[(ratio > 0.05) & sp_col.isin([0.0, 1.0])].dropna().index:
            P0, P1, D = float(p.loc[i]), float(c.loc[i]), float(d.loc[i])
            r_c = (P1 + D) / P0 - 1.0
            r_y = P1 / (P0 - D) - 1.0 if (P0 - D) > 0 else np.nan
            rows.append({"ticker": t, "date": str(i.date()), "dp": D / P0,
                         "r_true": r_c, "r_yahoo": r_y, "err": r_y - r_c})
    df = pd.DataFrame(rows)
    pos, neg = df[df.r_true > 0], df[df.r_true < 0]
    print(f"{len(df)} ordinary distributions above 5% of price")
    print(f"  positive true return: {len(pos)}, Yahoo overstated {int((pos.err > 0).sum())}")
    print(f"  negative true return: {len(neg)}, Yahoo made more negative "
          f"{int((neg.err < 0).sum())}")
    print(f"  |error| median {df.err.abs().median():.4%}  p90 {df.err.abs().quantile(0.9):.4%}  "
          f"max {df.err.abs().max():.4%}")
    worst = df.loc[df.err.abs().idxmax()]
    print(f"  worst: {worst.ticker} {worst.date}  D/P {worst.dp:.2%}  "
          f"true {worst.r_true:+.4%} vs yahoo {worst.r_yahoo:+.4%}")


# ---------------------------------------------------------------------------
# rollout — the three-arm family comparison
# ---------------------------------------------------------------------------

_ORIGINAL_TRC = ps_mod.total_return_close


def _install_arm(arm: str) -> None:
    """Force each arm's same-day rule EXPLICITLY rather than relying on what a
    convention happens to imply.

    That is load-bearing for reproducibility across the very change this
    script measured. Before 2026-09-04 the CRSP enum implied
    drop_same_day_split_distributions=True and YAHOO implied False; after it,
    both default to False. Pinning the flag per arm here means the three arms
    keep meaning the same three things whichever side of that change the
    library is on."""
    def _forced(drop: bool):
        def patched(frame, *, convention=AdjustmentConvention.CRSP,
                    drop_same_day_split_distributions=None):
            return _ORIGINAL_TRC(frame, convention=convention,
                                 drop_same_day_split_distributions=drop)
        return patched

    if arm == "crsp_drop":
        ps_mod.total_return_close = _forced(True)
    else:
        # yahoo and crsp_keep both keep same-day distributions; they differ
        # only in the convention the provider is constructed with.
        ps_mod.total_return_close = _forced(False)


def _provider(arm: str) -> YFinanceProvider:
    conv = AdjustmentConvention.YAHOO if arm == "yahoo" else AdjustmentConvention.CRSP
    return YFinanceProvider(adjustment=conv)


def _edgar():
    from app.services.market_data.edgar_xbrl_provider import EdgarXbrlProvider
    return EdgarXbrlProvider()


def _families() -> dict:
    from app.services.research_lab.cross_sectional_asset_growth import (
        run_asset_growth_screening,
    )
    from app.services.research_lab.cross_sectional_best_ideas import (
        run_best_ideas_screening,
    )
    from app.services.research_lab.cross_sectional_bonds import run_bonds_screening
    from app.services.research_lab.cross_sectional_buyback import run_buyback_screening
    from app.services.research_lab.cross_sectional_commodities import (
        run_commodities_screening,
    )
    from app.services.research_lab.cross_sectional_correlation_risk_premium import (
        run_crp_screening,
    )
    from app.services.research_lab.cross_sectional_country_valmom import (
        run_country_valmom_screening,
    )
    from app.services.research_lab.cross_sectional_crypto import run_crypto_screening
    from app.services.research_lab.cross_sectional_earnings_premium import (
        run_eap_screening,
    )
    from app.services.research_lab.cross_sectional_eigenportfolio import (
        run_eigenportfolio_screening,
    )
    from app.services.research_lab.cross_sectional_illiq import run_illiq_screening
    from app.services.research_lab.cross_sectional_index_removal import (
        run_index_removal_screening,
    )
    from app.services.research_lab.cross_sectional_insider import run_insider_screening
    from app.services.research_lab.cross_sectional_ivol import run_round_d1_screening
    from app.services.research_lab.cross_sectional_jump_drift import (
        run_jump_drift_screening,
    )
    from app.services.research_lab.cross_sectional_lazy_prices import (
        run_lazy_prices_screening,
    )
    from app.services.research_lab.cross_sectional_patterns import run_round_c_screening
    from app.services.research_lab.cross_sectional_patterns_d2 import (
        screen_d2_reversal_family,
    )
    from app.services.research_lab.cross_sectional_pead import run_pead_screening
    from app.services.research_lab.cross_sectional_quality import run_quality_screening
    from app.services.research_lab.cross_sectional_quality_neutral import (
        run_noa_neutral_screening,
    )
    from app.services.research_lab.cross_sectional_residual_momentum import (
        run_residual_momentum_screening,
    )
    from app.services.research_lab.cross_sectional_seasonality import (
        run_seasonality_screening,
    )
    from app.services.research_lab.cross_sectional_short_interest import (
        SHORT_INTEREST_FORMATION_START,
        run_short_interest_screening,
    )
    from app.services.research_lab.cross_sectional_small_mid_cap import (
        run_small_cap_disposition_screening,
        run_small_cap_ivol_screening,
    )
    from app.services.research_lab.small_cap_membership_history import (
        MEMBERSHIP_DATA_START as SMALL_CAP_START,
    )
    from app.services.research_lab.sp500_membership_history import get_universe_over
    from app.services.research_lab.vol_regime_timing import run_vol_regime_screening

    def quality(p):
        s = run_quality_screening(end=date(2026, 8, 28), provider=p, edgar=_edgar())
        return list(s.cbop_results) + list(s.noa_results)

    return {
        "quality": quality,
        "quality_noa": lambda p: run_noa_neutral_screening(
            end=date(2026, 8, 28), provider=p, edgar=_edgar()).results,
        "short_interest": lambda p: run_short_interest_screening(
            start=SHORT_INTEREST_FORMATION_START, end=date(2026, 9, 2),
            provider=p, edgar=_edgar()).results,
        "lazy_prices": lambda p: run_lazy_prices_screening(
            MEMBERSHIP_DATA_START, date(2026, 8, 31), provider=p,
            tickers=get_universe_over(MEMBERSHIP_DATA_START, date(2026, 8, 31))).results,
        "crypto": lambda p: run_crypto_screening(end=date(2026, 8, 31), provider=p).results,
        "residual_momentum": lambda p: run_residual_momentum_screening(
            end=date(2026, 9, 2), provider=p, edgar=_edgar()).results,
        "asset_growth": lambda p: run_asset_growth_screening(
            end=date(2026, 9, 1), provider=p, edgar=_edgar()).results,
        "bonds": lambda p: run_bonds_screening(end=date(2026, 8, 31), provider=p).results,
        "commodities": lambda p: run_commodities_screening(
            end=date(2026, 8, 31), provider=p).results,
        "illiq": lambda p: run_illiq_screening(
            MEMBERSHIP_DATA_START, date(2026, 8, 28), provider=p)[0],
        "seasonality": lambda p: run_seasonality_screening(
            MEMBERSHIP_DATA_START, date(2026, 8, 28), provider=p)[0],
        "ivol": lambda p: run_round_d1_screening(
            MEMBERSHIP_DATA_START, date(2026, 8, 28), provider=p)[0],
        "patterns_c": lambda p: run_round_c_screening(
            MEMBERSHIP_DATA_START, date(2026, 8, 30), provider=p)[0],
        "patterns_d2": lambda p: screen_d2_reversal_family(
            MEMBERSHIP_DATA_START, date(2026, 8, 30), provider=p).results,
        "jump_drift": lambda p: run_jump_drift_screening(
            MEMBERSHIP_DATA_START, date(2026, 8, 30), provider=p, run_event_study=False).results,
        "buyback": lambda p: run_buyback_screening(end=date(2026, 8, 31), provider=p).results,
        "best_ideas": lambda p: run_best_ideas_screening(
            end=date(2026, 8, 31), provider=p).results,
        "crp": lambda p: run_crp_screening(
            end=date(2026, 8, 31), provider=p, include_pit_crosscheck=False).results,
        "eigenportfolio": lambda p: run_eigenportfolio_screening(
            end=date(2026, 8, 31), provider=p, include_reversal_diagnostic=False,
            include_edge_cost_diagnostic=False).results,
        "index_removal": lambda p: run_index_removal_screening(
            MEMBERSHIP_DATA_START, date(2026, 8, 31), provider=p).results,
        "insider": lambda p: run_insider_screening(
            MEMBERSHIP_DATA_START, date(2026, 8, 31), provider=p).results,
        "pead": lambda p: run_pead_screening(
            MEMBERSHIP_DATA_START, date(2026, 8, 31), provider=p).results,
        "smallcap_disp": lambda p: run_small_cap_disposition_screening(
            SMALL_CAP_START, date(2026, 8, 31), provider=p)[0],
        "smallcap_ivol": lambda p: run_small_cap_ivol_screening(
            SMALL_CAP_START, date(2026, 8, 31), provider=p)[0],
        "vol_regime": lambda p: run_vol_regime_screening(
            end=date(2026, 8, 31), provider=p).results,
        "country_valmom": lambda p: run_country_valmom_screening(
            end=date(2026, 8, 31), provider=p).results,
        "earnings_premium": lambda p: run_eap_screening(
            MEMBERSHIP_DATA_START, date(2026, 8, 31), provider=p).results,
    }


def _num(value) -> float:
    """None -> NaN. DeflatedSharpeResult.dsr is None wherever a family has
    fewer than deflated_sharpe.MIN_TRIALS_FOR_DSR trials (patterns_d2 has 4),
    and that is a real "not computed", not a zero."""
    return float("nan") if value is None else float(value)


def _extract(results) -> dict[str, dict[str, float]]:
    out = {}
    for r in results:
        pid = getattr(r, "pattern_id", None) or getattr(r, "spec_id", None) or r.trial_id
        dsr_obj = getattr(r, "deflated_sharpe", None)
        out[str(pid)] = {
            "sharpe": _num(getattr(r, "sharpe_annualized", None)),
            "dsr": _num(getattr(dsr_obj, "dsr", None)) if dsr_obj is not None else float("nan"),
        }
    return out


def cmd_rollout(arm: str, only: str, out_suffix: str) -> None:
    _install_arm(arm)
    registry = _families()
    keys = [k for k in (only.split(",") if only else registry) if k in registry]
    payload: dict = {"arm": arm, "families": {}}
    for key in keys:
        t0 = time.time()
        try:
            specs = _extract(registry[key](_provider(arm)))
            payload["families"][key] = {"status": "ok", "specs": specs,
                                        "seconds": round(time.time() - t0, 1)}
            print(f"[{arm}] {key}: {len(specs)} specs in {time.time() - t0:.0f}s", flush=True)
        except Exception as exc:  # noqa: BLE001
            payload["families"][key] = {
                "status": "failed", "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc()[-1500:],
                "seconds": round(time.time() - t0, 1),
            }
            print(f"[{arm}] {key}: FAILED -- {type(exc).__name__}: {exc}",
                  flush=True, file=sys.stderr)
        # Dump after EVERY family: a run this long must not lose the families
        # it already finished if it is interrupted.
        (OUT_DIR / f"rollout{out_suffix}_{arm}.partial.json").write_text(
            json.dumps(payload, indent=1)
        )
    path = OUT_DIR / f"rollout{out_suffix}_{arm}.json"
    path.write_text(json.dumps(payload, indent=1))
    print(f"wrote {path}", flush=True)


# ---------------------------------------------------------------------------
# compare / buildjson
# ---------------------------------------------------------------------------

THRESHOLDS = (0.50, 0.6275, 0.95)
ARMS = ("yahoo", "crsp_keep", "crsp_drop")


def _load_arms() -> dict:
    arms = {}
    for arm in ARMS:
        arms[arm] = json.loads((OUT_DIR / f"rollout_{arm}.json").read_text())["families"]
        patch = OUT_DIR / f"rollout_patch_{arm}.json"
        if patch.exists():
            arms[arm].update(json.loads(patch.read_text())["families"])
    return arms


def _diff(arms: dict) -> tuple[dict, dict, dict, int]:
    base = arms["yahoo"]
    families, crossings, flips, n_specs = {}, {a: [] for a in ARMS[1:]}, {a: [] for a in ARMS[1:]}, 0
    for fam, b in sorted(base.items()):
        if b.get("status") != "ok":
            families[fam] = {"status": "not_compared", "reason": b.get("error", "")}
            continue
        entry: dict = {"status": "ok", "n_specs": len(b["specs"]), "specs": {}}
        n_specs += len(b["specs"])
        for arm in ARMS[1:]:
            a = arms[arm].get(fam, {})
            if a.get("status") != "ok":
                entry[arm] = {"status": "unavailable"}
                continue
            common = sorted(set(b["specs"]) & set(a["specs"]))
            ds = {s: a["specs"][s]["sharpe"] - b["specs"][s]["sharpe"] for s in common}
            dd = {s: a["specs"][s]["dsr"] - b["specs"][s]["dsr"] for s in common}
            worst = max(ds, key=lambda s: abs(ds[s])) if ds else None
            entry[arm] = {"status": "ok",
                          "max_abs_dsharpe": abs(ds[worst]) if worst else 0.0,
                          "max_abs_ddsr": max((abs(v) for v in dd.values()), default=0.0),
                          "worst_spec": worst}
            for s in common:
                b0, a0 = b["specs"][s]["dsr"], a["specs"][s]["dsr"]
                for t in THRESHOLDS:
                    if (b0 < t) != (a0 < t):
                        crossings[arm].append({"family": fam, "spec": s, "threshold": t,
                                               "yahoo_dsr": b0, "arm_dsr": a0})
                bs, as_ = b["specs"][s]["sharpe"], a["specs"][s]["sharpe"]
                if bs and as_ and (bs > 0) != (as_ > 0):
                    flips[arm].append({"family": fam, "spec": s,
                                       "yahoo_sharpe": bs, "arm_sharpe": as_})
        for s in sorted(b["specs"]):
            row = {"yahoo": b["specs"][s]}
            for arm in ARMS[1:]:
                a = arms[arm].get(fam, {})
                if a.get("status") == "ok" and s in a["specs"]:
                    row[arm] = a["specs"][s]
            entry["specs"][s] = row
        families[fam] = entry
    return families, crossings, flips, n_specs


LIVE = {
    "quality": ["cbop_ls_h63"],
    "short_interest": ["si_ratio_hedged_h21"],
    "lazy_prices": ["lazy_jaccard_full_h126_ivol"],
    "crypto": ["xc_btcbeta_l180_h180"],
}


def cmd_compare() -> None:
    arms = _load_arms()
    families, crossings, flips, n_specs = _diff(arms)
    ok = [(f, v) for f, v in families.items() if v["status"] == "ok"]
    ok.sort(key=lambda kv: -(kv[1].get("crsp_keep", {}).get("max_abs_dsharpe") or 0))
    print(f"{'family':20s} {'specs':>5s} | {'keep maxdS':>11s} {'maxdDSR':>10s} "
          f"{'worst spec':>34s} | {'drop maxdS':>11s} {'maxdDSR':>10s}")
    for fam, v in ok:
        k, d = v.get("crsp_keep", {}), v.get("crsp_drop", {})
        print(f"{fam:20s} {v['n_specs']:5d} | {k.get('max_abs_dsharpe', 0):11.6f} "
              f"{k.get('max_abs_ddsr', 0):10.6f} {(k.get('worst_spec') or ''):>34s} | "
              f"{d.get('max_abs_dsharpe', 0):11.6f} {d.get('max_abs_ddsr', 0):10.6f}")
    for fam, v in families.items():
        if v["status"] != "ok":
            print(f"{fam:20s} NOT COMPARED — {v['reason'][:70]}")
    print(f"\nfamilies compared: {len(ok)}   specs compared: {n_specs}")
    for arm in ARMS[1:]:
        print(f"\nDSR-threshold crossings under {arm}: {len(crossings[arm])}")
        for x in crossings[arm]:
            print(f"   {x['family']}/{x['spec']}: crosses {x['threshold']} — "
                  f"{x['yahoo_dsr']:.4f} -> {x['arm_dsr']:.4f}")
        print(f"Sharpe sign flips under {arm}: {len(flips[arm])}")
        for x in flips[arm]:
            print(f"   {x['family']}/{x['spec']}: {x['yahoo_sharpe']:+.4f} -> "
                  f"{x['arm_sharpe']:+.4f}")
    print("\nTHE LIVE REGISTRATIONS")
    for fam, specs in LIVE.items():
        for s in specs:
            row = families.get(fam, {}).get("specs", {}).get(s)
            if not row:
                print(f"  {s}: not measured")
                continue
            for arm in ARMS:
                if arm in row:
                    print(f"  {s:32s} {arm:10s} Sharpe {row[arm]['sharpe']:+.6f}  "
                          f"DSR {row[arm]['dsr']:.6f}")
            if "crsp_keep" in row:
                print(f"  {'':32s} delta      dSharpe "
                      f"{row['crsp_keep']['sharpe'] - row['yahoo']['sharpe']:+.6f}  "
                      f"dDSR {row['crsp_keep']['dsr'] - row['yahoo']['dsr']:+.6f}")


def cmd_buildjson() -> None:
    arms = _load_arms()
    families, crossings, flips, n_specs = _diff(arms)
    scan = json.loads((OUT_DIR / "dividend_convention_universe_scan.json").read_text())
    payload = {
        "generated": "2026-09-04",
        "what": ("Three-arm measurement of the dividend-adjustment convention: yahoo "
                 "(pre-2026-09-04 default), crsp_keep (new default), crsp_drop (the "
                 "same-day drop rule the CRSP enum previously carried; NOT shipped)."),
        "n_families_compared": sum(1 for v in families.values() if v["status"] == "ok"),
        "n_specs_compared": n_specs,
        "dsr_thresholds_checked": list(THRESHOLDS),
        "dsr_threshold_crossings": crossings,
        "sharpe_sign_flips": flips,
        "families": families,
        "universe_corporate_action_scan": {
            "n_tickers": len(scan["n"]),
            "same_day_split_distribution_events": {
                t: scan["same_day_dates"][t] for t in scan["n_same_day"]
                if scan["n_same_day"][t] > 0
            },
            "per_ticker": {
                t: {k: scan[k][t] for k in ("n_div", "n_split", "n_same_day", "max_div_ratio",
                                            "rel_conv_only", "rel_drop_only", "rel_full")
                    if k in scan}
                for t in scan["n"]
            },
        },
    }
    path = OUT_DIR / "dividend_convention_2026-09-04.json"
    path.write_text(json.dumps(payload, indent=1))
    print(f"wrote {path}: {payload['n_families_compared']} families, {n_specs} specs")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["events", "sameday", "crosscheck", "scan",
                                        "amplify", "rollout", "compare", "buildjson"])
    ap.add_argument("--arm", choices=list(ARMS))
    ap.add_argument("--families", default="")
    ap.add_argument("--suffix", default="")
    args = ap.parse_args()
    if args.command == "rollout":
        if not args.arm:
            ap.error("rollout needs --arm")
        cmd_rollout(args.arm, args.families, args.suffix)
    else:
        globals()[f"cmd_{args.command}"]()


if __name__ == "__main__":
    main()
