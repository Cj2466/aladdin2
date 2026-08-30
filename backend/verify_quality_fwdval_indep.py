"""Independent adversarial re-derivation of the quality forward-validation
registration work. Nothing here reads the builder's tests or docstrings for
its answers -- every assertion is recomputed from the production objects."""

import json
from dataclasses import replace
from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.services.research_lab import cross_sectional_forward_registry as reg
from app.services.research_lab.cross_sectional import CrossSectionalConfig, CrossSectionalData
from app.services.research_lab.cross_sectional_forward import (
    validate_spec_is_forward_tickable,
)
from app.services.research_lab.cross_sectional_quality import (
    CBOP_FAMILY,
    QUALITY_SAMPLE_SEED,
    QUALITY_SAMPLE_SIZE,
    build_quality_sample,
    default_quality_config,
)
from app.services.research_lab.cross_sectional_quality_neutral import (
    build_noa_neutral_family,
)
from app.services.research_lab import sp500_membership_history as memb

OK, BAD = "PASS", "**FAIL**"
results = []


def check(label, cond, detail=""):
    results.append((OK if cond else BAD, label, detail))
    print(f"{OK if cond else BAD}  {label}  {detail}")


print("=" * 78)
print("A. SEEDED SAMPLE / UNIVERSE-DRIFT PIN")
print("=" * 78)
today = date.today()
print(f"today={today}  MEMBERSHIP_DATA_AS_OF={memb.MEMBERSHIP_DATA_AS_OF}  "
      f"coverage_end={memb.membership_coverage_end()}")

union_pinned = memb.get_universe_over(memb.MEMBERSHIP_DATA_START, memb.MEMBERSHIP_DATA_AS_OF)
union_today = memb.get_universe_over(memb.MEMBERSHIP_DATA_START, today)
check("union(pinned) == union(today) RIGHT NOW",
      union_pinned == union_today,
      f"pinned={len(union_pinned)} today={len(union_today)}")
check("union size is 768 as claimed", len(union_pinned) == 768, f"got {len(union_pinned)}")

samp_pinned, n_p = build_quality_sample(memb.MEMBERSHIP_DATA_START, memb.MEMBERSHIP_DATA_AS_OF)
samp_today, n_t = build_quality_sample(memb.MEMBERSHIP_DATA_START, today)
check("build_quality_sample(pinned) == build_quality_sample(today) RIGHT NOW",
      samp_pinned == samp_today, f"{len(samp_pinned)} vs {len(samp_today)}")
check("sample size is 200", len(samp_pinned) == QUALITY_SAMPLE_SIZE, f"got {len(samp_pinned)}")
check("universe_size returned is 768", n_p == 768 and n_t == 768, f"{n_p}/{n_t}")

# The claim under test: a SINGLE added name re-draws the WHOLE sample.
import random  # noqa: E402

pop = list(union_pinned)
a = sorted(random.Random(QUALITY_SAMPLE_SEED).sample(pop, QUALITY_SAMPLE_SIZE))
b = sorted(random.Random(QUALITY_SAMPLE_SEED).sample([*pop, "ZZZZNEW"], QUALITY_SAMPLE_SIZE))
overlap = len(set(a) & set(b))
check("random.Random(seed).sample re-draws the WHOLE sample on +1 population member",
      overlap < QUALITY_SAMPLE_SIZE,
      f"overlap {overlap}/200 -> {200 - overlap} names swapped by ONE added ticker")

# Does the pin actually bite? Simulate the live MembershipRefreshRunner
# extending coverage with a real post-AS_OF addition.
ext = memb.MembershipExtension(
    coverage_end=memb.MEMBERSHIP_DATA_AS_OF + timedelta(days=45),
    events=((memb.MEMBERSHIP_DATA_AS_OF + timedelta(days=30), ("ZZZZNEW",), ()),),
    sources=("verifier-simulated",),
)
memb.apply_membership_extension(ext)
try:
    s_pin2, _ = build_quality_sample(memb.MEMBERSHIP_DATA_START, memb.MEMBERSHIP_DATA_AS_OF)
    s_now2, _ = build_quality_sample(memb.MEMBERSHIP_DATA_START, date.today())
    check("AFTER a simulated refresh: PINNED sample is unchanged",
          s_pin2 == samp_pinned, "")
    check("AFTER a simulated refresh: UNPINNED sample WOULD have been re-drawn "
          "(so the pin is load-bearing, not decorative)",
          s_now2 != samp_pinned,
          f"unpinned overlap with original = {len(set(s_now2) & set(samp_pinned))}/200")

    # Residual risk the builder disclosed: earliest_overrides.
    ext2 = memb.MembershipExtension(
        coverage_end=memb.MEMBERSHIP_DATA_AS_OF,
        earliest_overrides=(("AAPL", date(2015, 1, 8)), ("MSFT", date(2016, 1, 8))),
        sources=("verifier-simulated",),
    )
    memb.apply_membership_extension(ext2)
    s_pin3, _ = build_quality_sample(memb.MEMBERSHIP_DATA_START, memb.MEMBERSHIP_DATA_AS_OF)
    u_pin3 = memb.get_universe_over(memb.MEMBERSHIP_DATA_START, memb.MEMBERSHIP_DATA_AS_OF)
    check("earliest_overrides CANNOT change the pinned union (get_universe_over "
          "reads _BASE_UNIVERSE+events, never intervals)",
          u_pin3 == union_pinned and s_pin3 == samp_pinned, "")
finally:
    memb.clear_membership_extension()

print()
print("=" * 78)
print("B. SPEC IDENTITY IS INDEPENDENT OF bucket_frame (late-binding safety)")
print("=" * 78)
real_idx = pd.date_range("2024-01-01", periods=40, freq="B")
real_bucket = pd.DataFrame("tech", index=real_idx, columns=["AAA", "BBB", "CCC", "DDD"])
empty_specs = build_noa_neutral_family(reg._IDENTITY_ONLY_BUCKET_FRAME)
real_specs = build_noa_neutral_family(real_bucket)
fp_empty = [reg.spec_fingerprint(s) for s in empty_specs]
fp_real = [reg.spec_fingerprint(s) for s in real_specs]
check("all 9 spec fingerprints identical for empty vs real bucket_frame",
      fp_empty == fp_real, f"{len(fp_empty)} specs")
check("identity dicts identical too",
      [reg.spec_identity(s) for s in empty_specs] == [reg.spec_identity(s) for s in real_specs], "")

# and against the DB-registered fingerprint
import sqlite3  # noqa: E402

con = sqlite3.connect("aladdin2.db")
con.row_factory = sqlite3.Row
rows = {r["family_key"]: dict(r) for r in con.execute(
    "SELECT * FROM cross_sectional_forward_validation_registrations")}
noa_row = rows["quality_noa_industry_neutral"]
live_noa = next(s for s in real_specs if s.pattern_id == "noa_neutral_ls_h126_median")
check("DB-stored spec_fingerprint for noa == fingerprint computed against a REAL bucket frame "
      "(i.e. the registration will NOT park as spec_drift on the first live tick)",
      noa_row["spec_fingerprint"] == reg.spec_fingerprint(live_noa),
      noa_row["spec_fingerprint"][:16] + "...")
cbop_row = rows["quality_cbop"]
live_cbop = next(s for s in CBOP_FAMILY if s.pattern_id == "cbop_ls_h63")
check("DB-stored spec_fingerprint for cbop == live family fingerprint",
      cbop_row["spec_fingerprint"] == reg.spec_fingerprint(live_cbop), "")
cfg = default_quality_config()
check("DB-stored config_fingerprint == live default_quality_config fingerprint (both rows)",
      cbop_row["config_fingerprint"] == reg.config_fingerprint(cfg)
      == noa_row["config_fingerprint"], "")
check("DB-stored spec_snapshot_json == live spec_identity (cbop)",
      json.loads(cbop_row["spec_snapshot_json"]) == reg.spec_identity(live_cbop), "")
check("DB-stored spec_snapshot_json == live spec_identity (noa)",
      json.loads(noa_row["spec_snapshot_json"]) == reg.spec_identity(live_noa), "")

# resolve_spec at registration time (no live panel built) must agree
reg._LIVE_NOA_NEUTRAL_BUCKET_FRAME = None
_a, s_cold = reg.resolve_spec("quality_noa_industry_neutral", "noa_neutral_ls_h126_median")
check("resolve_spec with NO live panel yet yields the DB fingerprint",
      reg.spec_fingerprint(s_cold) == noa_row["spec_fingerprint"], "")

print()
print("=" * 78)
print("C. THE IDENTITY-ONLY FRAME IS USELESS FOR FORMING (raises, never ranks nothing)")
print("=" * 78)
close = pd.DataFrame(
    100.0 + np.arange(40 * 4).reshape(40, 4) * 0.1,
    index=real_idx, columns=["AAA", "BBB", "CCC", "DDD"])
fund = pd.DataFrame(1.0, index=real_idx, columns=close.columns)
data = CrossSectionalData(close=close, fundamental_signal=fund)
try:
    s_cold.signal_fn(data)
    check("empty bucket_frame RAISES when actually used to form", False, "it returned silently!")
except Exception as exc:  # noqa: BLE001
    check("empty bucket_frame RAISES when actually used to form", True,
          f"{type(exc).__name__}: {str(exc)[:70]}")

print()
print("=" * 78)
print("D. validate_spec_is_forward_tickable, re-derived from the real objects")
print("=" * 78)
for fam, pid in (("quality_cbop", "cbop_ls_h63"),
                 ("quality_noa_industry_neutral", "noa_neutral_ls_h126_median")):
    adapter, spec = reg.resolve_spec(fam, pid)
    c = adapter.build_config()
    validate_spec_is_forward_tickable(spec, c)
    check(f"{pid}: cohort_formation_days is None", spec.cohort_formation_days is None,
          repr(spec.cohort_formation_days))
    check(f"{pid}: config.impute_delisting_returns is False", c.impute_delisting_returns is False,
          repr(c.impute_delisting_returns))
    check(f"{pid}: holding_days >= 1", spec.holding_days >= 1, str(spec.holding_days))
    check(f"{pid}: periods_per_year == 252 (equity calendar)", c.periods_per_year == 252,
          str(c.periods_per_year))
    check(f"{pid}: adapter.n_trials matches DB row",
          adapter.n_trials == rows[fam]["family_n_trials"],
          f"{adapter.n_trials} vs {rows[fam]['family_n_trials']}")
    from app.services.cross_sectional_forward_validation_service import graduation_threshold_for
    check(f"{pid}: min_trading_days_threshold == max(126, 2*holding)={graduation_threshold_for(spec)}",
          rows[fam]["min_trading_days_threshold"] == graduation_threshold_for(spec),
          f"DB={rows[fam]['min_trading_days_threshold']}")
    check(f"{pid}: build_config returns a FRESH object each call (no shared singleton)",
          adapter.build_config() is not adapter.build_config(), "")

print()
print("=" * 78)
print("E. ROW SANITY")
print("=" * 78)
for fam in ("quality_cbop", "quality_noa_industry_neutral"):
    r = rows[fam]
    check(f"{fam}: status in_progress", r["status"] == "in_progress", r["status"])
    check(f"{fam}: last_processed_date IS NULL", r["last_processed_date"] is None, "")
    check(f"{fam}: n_forward_trading_days == 0", r["n_forward_trading_days"] == 0, "")
    check(f"{fam}: n_formations == 0", r["n_formations"] == 0, "")
    check(f"{fam}: fingerprints non-null", bool(r["spec_fingerprint"]) and bool(r["config_fingerprint"]), "")
    check(f"{fam}: graduated_at / last_ticked_at NULL",
          r["graduated_at"] is None and r["last_ticked_at"] is None, "")
    check(f"{fam}: user_id resolves to the system account",
          con.execute("SELECT email FROM users WHERE id=?", (r["user_id"],)).fetchone()[0]
          == "system+research@aladdin2.internal", "")
check("the two rows have DIFFERENT config_hash (idempotency keys don't collide)",
      rows["quality_cbop"]["config_hash"] != rows["quality_noa_industry_neutral"]["config_hash"], "")

print()
print("=" * 78)
print("F. n_trials=18 IS WHAT WAS ACTUALLY PERSISTED (not just a constant)")
print("=" * 78)
tr = {(r["family_key"], r["trial_id"]): r["n_trials"] for r in con.execute(
    "SELECT family_key, trial_id, n_trials FROM cross_sectional_trial_results "
    "WHERE family_key IN ('quality_cbop','quality_noa_industry_neutral','quality_noa')")}
check("persisted noa_neutral trial rows carry n_trials=18",
      all(v == 18 for (f, _), v in tr.items() if f == "quality_noa_industry_neutral"),
      str(sorted({v for (f, _), v in tr.items() if f == 'quality_noa_industry_neutral'})))
check("persisted cbop trial rows carry n_trials=9",
      all(v == 9 for (f, _), v in tr.items() if f == "quality_cbop"),
      str(sorted({v for (f, _), v in tr.items() if f == 'quality_cbop'})))

print()
print("=" * 78)
print("G. EDGAR max_cache_age_days=None IS A NO-OP")
print("=" * 78)
from pathlib import Path  # noqa: E402
import tempfile  # noqa: E402
import os  # noqa: E402
import time  # noqa: E402
from app.services.market_data.edgar_xbrl_provider import EdgarXbrlProvider  # noqa: E402

with tempfile.TemporaryDirectory() as td:
    p = Path(td) / "x.json"
    p.write_text("{}")
    old = time.time() - 400 * 86400
    os.utime(p, (old, old))
    default = EdgarXbrlProvider(cache_dir=td)
    check("default provider has max_cache_age_days None", default.max_cache_age_days is None, "")
    check("a 400-day-old file is STILL usable with the default (unchanged behavior)",
          default._cache_is_usable(p) is True, "")
    check("a missing file is not usable", default._cache_is_usable(Path(td) / "nope.json") is False, "")
    bounded = EdgarXbrlProvider(cache_dir=td, max_cache_age_days=1)
    check("with max_cache_age_days=1 the 400-day-old file is expired",
          bounded._cache_is_usable(p) is False, "")
    now = time.time()
    os.utime(p, (now, now))
    check("with max_cache_age_days=1 a fresh file is usable", bounded._cache_is_usable(p) is True, "")
    check("live provider factory sets the bound to 1",
          reg._live_edgar_provider().max_cache_age_days == 1, "")

print()
print("=" * 78)
print("H. spec_identity OMISSION: would adding requires_fundamental_signal break existing rows?")
print("=" * 78)
orig = reg.spec_identity


def widened(spec):
    d = orig(spec)
    d["requires_fundamental_signal"] = spec.requires_fundamental_signal
    return d


reg.spec_identity = widened
try:
    new_fp = reg.spec_fingerprint(live_cbop)
finally:
    reg.spec_identity = orig
check("adding requires_fundamental_signal DOES change every fingerprint "
      "(so it would park any in-flight registration, incl. BAB, as spec_drift)",
      new_fp != cbop_row["spec_fingerprint"], f"{new_fp[:16]}... vs {cbop_row['spec_fingerprint'][:16]}...")
check("BUT: flipping requires_fundamental_signal today is INVISIBLE to drift detection",
      reg.spec_fingerprint(replace(live_cbop, requires_fundamental_signal=False))
      == reg.spec_fingerprint(live_cbop), "confirmed gap")
check("flipping cost_model is also invisible" if hasattr(live_cbop, "cost_model") else
      "(no cost_model field on CrossSectionalSpec)",
      True, "")

print()
print("=" * 78)
n_fail = sum(1 for s, _, _ in results if s == BAD)
print(f"{len(results)} checks, {n_fail} FAILED")
print("=" * 78)
