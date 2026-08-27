import sys, pickle, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
import pandas as pd, numpy as np

SP="/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
d = pickle.load(open(f"{SP}/d1_impact_data.pkl","rb"))
close, shares, splits = d["close"], d["shares"], d["splits"]
print("D1 run:", d["start"], "->", d["end"], "padded", d["padded_start"])
print("universe", len(d["universe"]), "priced", close.shape[1], "missing_price", len(d["missing_price"]), "shares dict", len(shares), "missing_shares", len(d["missing_shares"]))
print("STI in universe:", "STI" in d["universe"], "| STI priced:", "STI" in close.columns, "| STI in missing_price:", "STI" in d["missing_price"], "| STI in shares:", "STI" in shares)
for t in ["DFS","CMA","SRCL","PARA"]:
    print(f"{t}: universe={t in d['universe']} priced={t in close.columns} missing_price={t in d['missing_price']} shares={t in shares}")
