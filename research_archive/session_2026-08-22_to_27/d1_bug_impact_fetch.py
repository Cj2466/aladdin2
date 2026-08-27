"""STEP 1 of the D1 market-cap bug impact replay: fetch, ONCE, exactly the
real data the already-reported production run used, plus the two new inputs
the fix needs. Cached to a pickle so the three replays below run against
bit-identical data."""
import pickle
import sys
import time
import traceback
from datetime import date, timedelta

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")

OUT = "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/d1_impact_data.pkl"
LOG = "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/d1_impact_fetch.log"


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def main():
    from app.services.market_data.yfinance_provider import YFinanceProvider
    from app.services.research_lab.cross_sectional_ivol import (
        PRICE_HISTORY_PADDING_CALENDAR_DAYS,
    )
    from app.services.research_lab.sp500_membership_history import (
        MEMBERSHIP_DATA_START,
        get_universe_over,
    )

    start = MEMBERSHIP_DATA_START
    end = date(2026, 8, 26)
    padded_start = start - timedelta(days=PRICE_HISTORY_PADDING_CALENDAR_DAYS)
    log(f"start={start} end={end} padded_start={padded_start}")

    universe = get_universe_over(start, end)
    log(f"universe: {len(universe)} tickers")

    provider = YFinanceProvider()
    t0 = time.time()
    close, missing_price = provider.get_price_history(universe, padded_start, end)
    log(f"signal close: {close.shape}, missing {len(missing_price)}  ({time.time()-t0:.1f}s)")

    priced = list(close.columns)
    t0 = time.time()
    mcap_close, splits, missing_basis = provider.get_market_cap_basis(priced, padded_start, end)
    log(f"mcap basis close: {mcap_close.shape}, splits for {len(splits)} tickers, "
        f"missing {len(missing_basis)}  ({time.time()-t0:.1f}s)")

    t0 = time.time()
    shares, missing_shares = provider.get_shares_outstanding(priced, padded_start, end)
    log(f"shares: {len(shares)} resolved, {len(missing_shares)} missing  ({time.time()-t0:.1f}s)")

    with open(OUT, "wb") as f:
        pickle.dump(
            {
                "start": start, "end": end, "padded_start": padded_start,
                "universe": universe, "close": close, "missing_price": missing_price,
                "mcap_close": mcap_close, "splits": splits, "missing_basis": missing_basis,
                "shares": shares, "missing_shares": missing_shares,
            },
            f,
        )
    log(f"WROTE {OUT}")
    log("DONE")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("FATAL:\n" + traceback.format_exc())
        raise
