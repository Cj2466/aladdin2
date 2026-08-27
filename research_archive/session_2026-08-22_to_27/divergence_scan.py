"""How often does DSR-ranking actually pick a DIFFERENT configuration than
raw-Sharpe ranking, on real tickers? Honest measurement, not an assumption."""
import os
import sys

SCRATCH = "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
os.environ["DATABASE_URL"] = f"sqlite:///{SCRATCH}/scan.db"
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app import dependencies  # noqa: E402
from app.services.research_lab import autonomous_tuning, momentum, ou_pairs  # noqa: E402
from app.services.research_lab.deflated_sharpe import (  # noqa: E402
    compute_deflated_sharpe,
    derive_returns_from_equity_curve,
)

engine = create_engine(f"sqlite:///{SCRATCH}/scan.db", connect_args={"check_same_thread": False})
Session = sessionmaker(bind=engine)

MOM = ["VTV", "MET", "PRU", "STT", "ROL", "BNY", "AAPL", "MSFT", "JPM", "XOM", "KO", "PEP", "GLD", "SPY", "NVDA"]
PAIRS = [("IWM", "QUAL"), ("NVDA", "VUG"), ("USMV", "VTV"), ("NVDA", "SPY"), ("GOOG", "GOOGL"),
         ("KO", "PEP"), ("AAPL", "MSFT"), ("C", "GS")]

diverged = 0
total = 0
for strategy, a, b in [(momentum.STRATEGY_NAME, t, t) for t in MOM] + [
    (ou_pairs.STRATEGY_NAME, x, y) for x, y in PAIRS
]:
    db = Session()
    try:
        lookback = autonomous_tuning.default_lookback_years(strategy)
        rows = []
        for combo in autonomous_tuning.build_tuning_grid(strategy):
            r = autonomous_tuning._run_one_combination(
                db, dependencies.provider, strategy_name=strategy, ticker_a=a, ticker_b=b,
                config=combo, lookback_years=lookback,
            )
            if r is None or r.status != "ok" or r.sharpe_net is None:
                continue
            rows.append((combo, r))
        n_trials, sigma_sr = autonomous_tuning.sibling_trial_stats(db, strategy, a, b)
        if not rows or sigma_sr is None:
            print(f"{strategy} {a}/{b}: SKIP (no usable combos)")
            continue
        scored = []
        for combo, r in rows:
            ret = derive_returns_from_equity_curve([p.equity for p in r.equity_curve])
            res = compute_deflated_sharpe(r.sharpe_net, ret, n_trials, sigma_sr)
            scored.append((combo, r.sharpe_net, res.dsr, r.n_out_of_sample_days))
        by_sharpe = max(scored, key=lambda x: x[1])
        with_dsr = [s for s in scored if s[2] is not None]
        if not with_dsr:
            print(f"{strategy} {a}/{b}: SKIP (no finite DSR)")
            continue
        by_dsr = max(with_dsr, key=lambda x: x[2])
        total += 1
        differs = by_sharpe[0] != by_dsr[0]
        diverged += differs
        default = autonomous_tuning.default_config(strategy)
        print(
            f"{strategy:12s} {a}/{b:6s} n={len(scored)} | "
            f"sharpe-pick fit={by_sharpe[0].fit_window_days} z={by_sharpe[0].entry_z} "
            f"(SR={by_sharpe[1]:.3f}, oos={by_sharpe[3]}) | "
            f"dsr-pick fit={by_dsr[0].fit_window_days} z={by_dsr[0].entry_z} "
            f"(SR={by_dsr[1]:.3f}, DSR={by_dsr[2]:.3f}, oos={by_dsr[3]}) | "
            f"DIVERGED={differs} | tuned!=default={by_dsr[0] != default}",
            flush=True,
        )
    finally:
        db.close()

print(f"\nDSR-vs-raw-Sharpe divergence: {diverged}/{total} candidates")
