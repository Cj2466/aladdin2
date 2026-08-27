import sys
import time
from datetime import date, timedelta

import numpy as np
import pandas as pd

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/agent-a327c9fd73bf9f348/backend")

from app.services.market_data.yfinance_provider import YFinanceProvider  # noqa: E402
from app.services.research_lab.cross_sectional import (  # noqa: E402
    CrossSectionalData,
    _leg_weights,
    select_leg_tickers,
    validate_cross_sectional_data,
)
from app.services.research_lab.cross_sectional_patterns import (  # noqa: E402
    LPS_HOLDING_DAYS,
    LPS_LOOKBACK_DAYS,
    signal_component_persistence,
)
from app.services.research_lab.sp500_membership_history import get_universe_over, was_member  # noqa: E402

START = date(2021, 1, 4)
END = date(2026, 8, 21)
PADDING_CALENDAR_DAYS = 420  # warms up the longest LPS lookback (252 + 1 rows)
MIN_NAMES_PER_LEG = 5

t0 = time.time()
universe = get_universe_over(START, END)
print(f"universe size: {len(universe)}", flush=True)

provider = YFinanceProvider()
padded_start = START - timedelta(days=PADDING_CALENDAR_DAYS)
frames, missing = provider.get_daily_ohlcv(universe, padded_start, END)
print(f"fetch done in {time.time()-t0:.1f}s, missing {len(missing)}/{len(universe)}: {missing[:20]}", flush=True)

data = CrossSectionalData(close=frames["close"], open=frames["open"], volume=frames.get("volume"))
validate_cross_sectional_data(data)

index = data.close.index
n = len(index)
eligible_positions = np.flatnonzero(index.date >= START)
start_pos = int(eligible_positions[0])

rows_out = []  # pattern_id, leg, weight, fwd_return

for component in ("overnight", "intraday"):
    for lookback in LPS_LOOKBACK_DAYS:
        for holding in LPS_HOLDING_DAYS:
            pattern_id = f"lps_{component}_l{lookback}_h{holding}"
            lookback_days_signal = lookback + 1
            first_formation = max(lookback_days_signal, start_pos)

            n_formations = 0
            n_skipped = 0
            for i in range(first_formation, n - 1, holding):
                formation_ts = index[i]
                formation_day = formation_ts.date()
                formation_close = data.close.iloc[i]
                eligible = [
                    t for t in data.close.columns if was_member(t, formation_day) and np.isfinite(formation_close[t])
                ]
                if not eligible:
                    n_skipped += 1
                    continue
                row_start = max(0, i + 1 - lookback_days_signal)
                view = CrossSectionalData(
                    close=data.close.iloc[row_start : i + 1].loc[:, eligible],
                    open=data.open.iloc[row_start : i + 1].loc[:, eligible],
                    volume=None,
                )
                signal = signal_component_persistence(view, component=component, lookback_days=lookback)
                top, bottom = select_leg_tickers(signal, 0.1)
                n_ranked = int(signal.dropna().shape[0])
                n_leg = len(top)
                if n_leg < MIN_NAMES_PER_LEG or 2 * n_leg > n_ranked:
                    n_skipped += 1
                    continue
                n_formations += 1

                hold_end = min(i + holding, n - 1)
                fwd = data.close.iloc[hold_end] / data.close.iloc[i] - 1.0

                long_w = _leg_weights(top, signal, higher_is_stronger=True)
                short_w = _leg_weights(bottom, signal, higher_is_stronger=False)

                for t, w in short_w.items():
                    fr = fwd.get(t, np.nan)
                    if np.isfinite(fr):
                        rows_out.append((pattern_id, "short", w, float(fr)))
                for t, w in long_w.items():
                    fr = fwd.get(t, np.nan)
                    if np.isfinite(fr):
                        rows_out.append((pattern_id, "long", w, float(fr)))

            print(f"{pattern_id}: formations={n_formations} skipped={n_skipped}", flush=True)

df = pd.DataFrame(rows_out, columns=["pattern_id", "leg", "weight", "fwd_return"])
out_path = "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/lps_weight_fwdreturn_rows.csv"
df.to_csv(out_path, index=False)
print(f"wrote {len(df)} rows to {out_path}", flush=True)
print(f"total elapsed {time.time()-t0:.1f}s", flush=True)
