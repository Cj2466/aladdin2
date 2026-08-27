import json, logging, sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/wf_d605a76f-0be-1/backend")
logging.basicConfig(level=logging.ERROR)
from dataclasses import asdict
from app.services.research_lab.cross_sectional_commodities import run_commodities_screening

s = run_commodities_screening()
out = {"n_trials": s.n_trials, "results": []}
for r in s.results:
    d = r.deflated_sharpe
    out["results"].append({
        "pattern_id": r.pattern_id,
        "sharpe": r.sharpe_annualized,
        "n_formations": r.n_formations,
        "dsr": asdict(d),
    })
json.dump(out, open("/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/commodities_meta_result.json", "w"), indent=1, default=str)
print("OK", len(out["results"]))
