"""Full Phase C screening run: all 28 low-frequency patterns x all 284
cached tickers, engine.py walk-forward, pooled equal-weighted baskets,
DSR at n_trials=28. 3 worker processes (the machine's other ~10 cores are
running Phase B). No early stopping — every ticker, every pattern."""

import glob
import os
import pickle
import sys
import time
from multiprocessing import Pool

BACKEND = "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/agent-a2520e5862565ddbf/backend"
sys.path.insert(0, BACKEND)
SCRATCH = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(SCRATCH, "bars_cache")
OUT = os.path.join(SCRATCH, "lowfreq_screening_outcomes.pkl")
N_WORKERS = 3


def run_ticker(ticker: str):
    import app.services.research_lab.low_frequency_patterns as lf

    with open(f"{CACHE}/{ticker}_15Min.pkl", "rb") as f:
        bars = pickle.load(f)
    t0 = time.time()
    outcomes = lf.run_patterns_for_ticker(bars)
    return ticker, outcomes, time.time() - t0


def main():
    tickers = sorted(
        os.path.basename(p).replace("_15Min.pkl", "") for p in glob.glob(f"{CACHE}/*_15Min.pkl")
    )
    done: dict = {}
    if os.path.exists(OUT):
        with open(OUT, "rb") as f:
            done = pickle.load(f)
        print(f"resuming: {len(done)} tickers already done", flush=True)
    todo = [t for t in tickers if t not in done]
    print(f"{len(tickers)} tickers total, {len(todo)} to run, {N_WORKERS} workers", flush=True)

    t_start = time.time()
    with Pool(N_WORKERS) as pool:
        for i, (ticker, outcomes, dt) in enumerate(pool.imap_unordered(run_ticker, todo), 1):
            done[ticker] = outcomes
            if i % 10 == 0 or i == len(todo):
                with open(OUT, "wb") as f:
                    pickle.dump(done, f)
                elapsed = time.time() - t_start
                rate = elapsed / i
                print(
                    f"[{i}/{len(todo)}] {ticker} ({dt:.0f}s) — elapsed {elapsed/60:.1f}m, "
                    f"ETA {(len(todo)-i)*rate/60:.0f}m",
                    flush=True,
                )

    with open(OUT, "wb") as f:
        pickle.dump(done, f)

    import app.services.research_lab.low_frequency_patterns as lf

    summary = lf.aggregate_ticker_outcomes(done)
    with open(os.path.join(SCRATCH, "lowfreq_screening_summary.pkl"), "wb") as f:
        pickle.dump(summary, f)

    print("\n================ PHASE C SCREENING SUMMARY ================", flush=True)
    print(f"n_trials={summary.n_trials}  sigma_SR={summary.sigma_sr_annualized}  SR0={summary.sr0_annualized}")
    print(f"{'pattern':45s} {'sharpe':>8s} {'DSR':>10s} {'PSR0':>7s} {'trades':>7s} {'t/tkr-yr':>8s} {'hit':>6s} {'fired':>5s}")
    for r in summary.results:
        d = r.deflated_sharpe
        dsr = f"{d.dsr:.2e}" if d.dsr is not None else "n/a"
        psr = f"{d.psr_vs_zero:.3f}" if d.psr_vs_zero is not None else "n/a"
        hit = f"{r.hit_rate:.1%}" if r.hit_rate is not None else "n/a"
        print(
            f"{r.pattern_id:45s} {r.sharpe_annualized:8.2f} {dsr:>10s} {psr:>7s} "
            f"{r.n_trades:7d} {r.trades_per_ticker_year:8.1f} {hit:>6s} {r.n_tickers_fired:5d}"
        )
    missing = {p.pattern_id for p in lf.LOW_FREQUENCY_PATTERN_FAMILY} - {r.pattern_id for r in summary.results}
    if missing:
        print(f"\npatterns with no reportable result (never fired / too few pooled days): {sorted(missing)}")


if __name__ == "__main__":
    main()
