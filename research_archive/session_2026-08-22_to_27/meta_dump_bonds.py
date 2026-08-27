import json, logging, sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
logging.basicConfig(level=logging.ERROR)
from app.services.research_lab.cross_sectional_bonds import run_bonds_screening
s = run_bonds_screening()
out=[{"pattern_id": r.pattern_id, "sharpe": r.sharpe_annualized,
      "dsr": r.deflated_sharpe.dsr, "sigma_sr": r.deflated_sharpe.sigma_sr_annualized,
      "n": r.deflated_sharpe.n_observations} for r in s.results]
json.dump({"n_trials": 18, "results": out}, open("/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/bonds_meta_result.json","w"), indent=1, default=str)
print("OK", len(out))
