"""Full expanded pattern-mining screen: 212-pattern family x the 55-ticker
pooled universe (30 large-cap + 25 verified mid/small-cap). This is the
actual, final, honestly-counted run this phase's report is based on --
n_trials = len(PATTERN_FAMILY) = 212 for every result, no early stopping,
every result recorded (not just the interesting ones).
"""
import json
import sys
import time
from dataclasses import asdict

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")

from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.intraday_patterns import (
    PATTERN_FAMILY,
    PATTERN_MINING_UNIVERSE,
    screen_pattern_universe,
)

OUT_PATH = "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/full_screen_results.json"


def main():
    print(f"[{time.strftime('%X')}] n_patterns={len(PATTERN_FAMILY)} n_tickers={len(PATTERN_MINING_UNIVERSE)}", flush=True)
    provider = YFinanceProvider()

    print(f"[{time.strftime('%X')}] fetching intraday bars for {len(PATTERN_MINING_UNIVERSE)} tickers...", flush=True)
    t0 = time.time()
    bars_by_ticker, missing = provider.get_intraday_bars(PATTERN_MINING_UNIVERSE)
    print(f"[{time.strftime('%X')}] fetched in {time.time() - t0:.1f}s, missing={missing}", flush=True)
    if missing:
        raise SystemExit(f"Universe verification was supposed to rule this out -- missing tickers: {missing}")

    for t, df in bars_by_ticker.items():
        print(f"  {t}: {len(df)} bars", flush=True)

    print(f"[{time.strftime('%X')}] running screen_pattern_universe over {len(PATTERN_FAMILY)} patterns...", flush=True)
    t0 = time.time()
    results = screen_pattern_universe(bars_by_ticker, patterns=PATTERN_FAMILY)
    elapsed = time.time() - t0
    print(f"[{time.strftime('%X')}] screen complete in {elapsed:.1f}s ({elapsed/60:.1f} min)", flush=True)
    print(f"n_results (patterns that fired somewhere and cleared MIN_POOLED_TRADING_DAYS): {len(results)}", flush=True)

    out = []
    for r in results:
        d = asdict(r)
        # DeflatedSharpeResult is a dataclass too -- asdict recurses correctly,
        # but double check it serialized to a plain dict, not an object repr.
        out.append(d)

    with open(OUT_PATH, "w") as f:
        json.dump(
            {
                "n_trials": len(PATTERN_FAMILY),
                "n_tickers_requested": len(PATTERN_MINING_UNIVERSE),
                "n_tickers_resolved": len(bars_by_ticker),
                "elapsed_seconds": elapsed,
                "results": out,
            },
            f,
            indent=2,
            default=str,
        )
    print(f"[{time.strftime('%X')}] wrote {OUT_PATH}", flush=True)

    # Immediate honest summary to stdout too.
    positive = [r for r in results if r.sharpe_annualized > 0]
    print(f"n patterns with positive raw Sharpe: {len(positive)} / {len(results)}", flush=True)
    cleared = [r for r in results if r.deflated_sharpe.dsr is not None and r.deflated_sharpe.dsr > 0.5]
    print(f"n patterns with DSR > 0.5: {len(cleared)}", flush=True)
    print("Top 10 by raw Sharpe:", flush=True)
    for r in results[:10]:
        print(
            f"  {r.pattern_id} [{r.family}] sharpe={r.sharpe_annualized:.3f} "
            f"dsr={r.deflated_sharpe.dsr} n_trades={r.n_trades} n_days={r.n_trading_days}",
            flush=True,
        )


if __name__ == "__main__":
    main()
