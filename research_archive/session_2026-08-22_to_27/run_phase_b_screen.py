"""Phase B screen runner: every pattern in both Phase B families against
every ticker in its group's basket, in parallel worker processes, with
per-ticker checkpointing so the run is resumable. After all backtests
finish, pools everything through the committed screen_pattern_groups with
n_trials=PHASE_B_TOTAL_TRIALS and writes the full result set.

No early stopping, no partial families — a (ticker, group) task always
runs its ENTIRE family to completion before its checkpoint is written.
"""

import pickle
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")

SCRATCH = Path("/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad")
CACHE = SCRATCH / "bars_cache"
RESULTS = SCRATCH / "screen_results"
RESULTS.mkdir(exist_ok=True)
LOG = SCRATCH / "screen_run.log"


def log(msg: str) -> None:
    """Append directly to a log file (line-buffered by open/close) AND
    stdout — a `| tail` pipe on the launching shell buffers stdout until
    process exit, which already hid one healthy run's progress entirely."""
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    with LOG.open("a") as fh:
        fh.write(line + "\n")
    print(line, flush=True)

GROUPS = {
    "15m": {"timeframe_file": "15Min", "family_name": "PATTERN_FAMILY_PHASE_B_15MIN", "fit_window_name": "FIT_WINDOW_BARS_15MIN"},
    "1m": {"timeframe_file": "1Min", "family_name": "PATTERN_FAMILY_PHASE_B_1MIN", "fit_window_name": "FIT_WINDOW_BARS_1MIN"},
}


def run_ticker(group: str, ticker: str) -> str:
    """One worker task: the ENTIRE family for one ticker at one
    granularity, checkpointed to disk."""
    from app.services.research_lab import intraday_patterns as ip

    cfg = GROUPS[group]
    out_path = RESULTS / f"stats_{group}_{ticker}.pkl"
    if out_path.exists():
        return f"{group}/{ticker}: cached"
    bars_path = CACHE / f"{ticker}_{cfg['timeframe_file']}.pkl"
    if not bars_path.exists():
        return f"{group}/{ticker}: NO BARS FILE"
    bars = pickle.loads(bars_path.read_bytes())
    family = getattr(ip, cfg["family_name"])
    fit_window = getattr(ip, cfg["fit_window_name"])
    t0 = time.time()
    stats = ip.backtest_patterns_for_ticker(bars, family, fit_window)
    tmp = out_path.with_suffix(".tmp")
    tmp.write_bytes(pickle.dumps(stats))
    tmp.rename(out_path)
    return f"{group}/{ticker}: ok n_bars={len(bars)} n_patterns={len(stats)} secs={time.time()-t0:.0f}"


def pool_and_report() -> None:
    from app.services.research_lab import intraday_patterns as ip

    groups = []
    for group, cfg in GROUPS.items():
        universe = ip.PHASE_B_UNIVERSE_15MIN if group == "15m" else ip.PHASE_B_UNIVERSE_1MIN
        family = getattr(ip, cfg["family_name"])
        stats_by_ticker = {}
        for ticker in universe:
            p = RESULTS / f"stats_{group}_{ticker}.pkl"
            if p.exists():
                stats_by_ticker[ticker] = pickle.loads(p.read_bytes())
        log(f"pooling {group}: {len(stats_by_ticker)} tickers loaded")
        groups.append(
            ip.PatternScreenGroup(timeframe=group, patterns=family, stats_by_ticker=stats_by_ticker)
        )

    results = ip.screen_pattern_groups(groups, n_trials=ip.PHASE_B_TOTAL_TRIALS)
    (RESULTS / "final_results.pkl").write_bytes(pickle.dumps(results))

    lines = []
    lines.append(f"PHASE B SCREEN — {len(results)} included patterns of {ip.PHASE_B_TOTAL_TRIALS} trials")
    positives = [r for r in results if r.sharpe_annualized > 0]
    lines.append(f"positive pooled Sharpe: {len(positives)}/{len(results)}")
    for r in results[:25]:
        d = r.deflated_sharpe
        lines.append(
            f"{r.pattern_id[:52]:52s} tf={r.timeframe:3s} sharpe={r.sharpe_annualized:+.3f} "
            f"dsr={d.dsr if d.dsr is not None else float('nan'):.3e} psr0={d.psr_vs_zero if d.psr_vs_zero is not None else float('nan'):.4f} "
            f"days={r.n_trading_days} trades={r.n_trades} hit={r.hit_rate if r.hit_rate is not None else float('nan'):.3f} "
            f"fired={r.n_tickers_fired}/{r.n_tickers_in_basket}"
        )
    report = "\n".join(lines)
    (RESULTS / "final_report.txt").write_text(report)
    log(report)


if __name__ == "__main__":
    tasks = []
    from app.services.research_lab import intraday_patterns as ip

    for ticker in ip.PHASE_B_UNIVERSE_15MIN:
        tasks.append(("15m", ticker))
    for ticker in ip.PHASE_B_UNIVERSE_1MIN:
        tasks.append(("1m", ticker))

    t0 = time.time()
    done = 0
    total_pending = len([1 for g, t in tasks if not (RESULTS / f"stats_{g}_{t}.pkl").exists()])
    log(f"{total_pending} of {len(tasks)} ticker-group tasks pending")

    with ProcessPoolExecutor(max_workers=10) as pool:
        submitted: set = set()
        futures = []
        # The bars fetcher may still be running: submit what has bars now,
        # rescan every 2 minutes for late-arriving bars files, and only
        # stop once EVERY task is either submitted or already checkpointed.
        while True:
            for g, t in tasks:
                key = (g, t)
                if key in submitted or (RESULTS / f"stats_{g}_{t}.pkl").exists():
                    continue
                if (CACHE / f"{t}_{GROUPS[g]['timeframe_file']}.pkl").exists():
                    futures.append(pool.submit(run_ticker, g, t))
                    submitted.add(key)
            remaining = [
                (g, t)
                for g, t in tasks
                if (g, t) not in submitted and not (RESULTS / f"stats_{g}_{t}.pkl").exists()
            ]
            if not remaining:
                break
            log(f"waiting for bars: {len(remaining)} tasks still lack bars files")
            time.sleep(120)

        for fut in as_completed(futures):
            done += 1
            try:
                msg = fut.result()
            except Exception as exc:
                msg = f"TASK FAILED: {type(exc).__name__}: {str(exc)[:120]}"
            log(f"[{done}/{len(futures)}] {msg} total_elapsed={time.time()-t0:.0f}s")

    log(f"backtests complete in {time.time()-t0:.0f}s — pooling")
    missing = [(g, t) for g, t in tasks if not (RESULTS / f"stats_{g}_{t}.pkl").exists()]
    if missing:
        log(f"WARNING: {len(missing)} stats files missing; NOT pooling. Rerun to finish: {missing[:10]}")
    else:
        pool_and_report()
