"""Re-estimate the section 4.1 / reversal / permutation regressions through the
CORRECTED module (sigma20 without the duplicated close). Nothing else is rerun;
positions, returns, DSR and the power block never use sigma20."""
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BACKEND))
from app.services.research_lab.letf_rebalancing_eod import (
    PRIMARY_WINDOW,
    SECONDARY_WINDOW,
    build_panel,
    regression_4_1,
    regression_reversal,
    shuffled_coefficient,
)
from data.research_runs.fetch_letf_aum import (
    AUM_COL,
    DATE_COL,
    TARGET_TICKERS,
    TICKER_COL,
    load_target_frame,
)
from data.research_runs.run_letf_rebalancing_eod import AUM_SNAPSHOT, load_bars

aum = load_target_frame(AUM_SNAPSHOT).rename(columns={AUM_COL: 'aum'})[[DATE_COL, TICKER_COL, 'aum']]
minute = load_bars()
fund_map = TARGET_TICKERS
panel, audit = build_panel(minute, aum, fund_map)
out = {}
for lab, fit in [('4_1_w1530', regression_4_1(panel, PRIMARY_WINDOW)), ('4_1_w1500', regression_4_1(panel, SECONDARY_WINDOW)),
                 ('reversal', regression_reversal(panel, PRIMARY_WINDOW)),
                 ('permutation_diagnostic', regression_4_1(panel, PRIMARY_WINDOW, coefficient=shuffled_coefficient(panel), label='perm', is_placebo=True))]:
    out[lab] = {'b': fit.b, 't': fit.b_t, 'se': fit.b_se, 'c': fit.c, 'c_t': fit.c_t, 'n': fit.n_observations, 'clusters': fit.n_clusters, 'r2_pct': fit.r_squared_pct, 'passes_gate': fit.passes_gate()}
out['panel'] = {'rows': len(panel), 'sessions': int(panel['date'].nunique())}
print(json.dumps(out, indent=1))
