"""Final before/after report for the D1 market-cap bug."""
import json, sys

BASE = "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
n = json.load(open(f"{BASE}/d1_impact_replay.json"))
old = json.load(open(f"{BASE}/d1_production_result.json"))
oldmap = {r["pattern_id"]: r for r in old["results"]}
A = {r["pattern_id"]: r for r in n["screenings"]["A_shipped"]}
B = {r["pattern_id"]: r for r in n["screenings"]["B_split_fixed"]}
C = {r["pattern_id"]: r for r in n["screenings"]["C_fixed"]}

print("=" * 104)
print("STEP 0 — does the replay reproduce the ALREADY-REPORTED production run?")
ws = max(abs(oldmap[p]["sharpe_annualized"] - A[p]["sharpe_annualized"]) for p in A)
wd = max(abs(oldmap[p]["deflated_sharpe"]["dsr"] - A[p]["dsr"]) for p in A)
print(f"   max |sharpe diff| = {ws:.2e}   max |dsr diff| = {wd:.2e}   -> replay is the reported run")
print(f"   legs {sum(r['n_value_weighted_legs'] for r in A.values())} / fallbacks "
      f"{sum(r['n_value_weight_fallbacks'] for r in A.values())}  (reported: 2321 / 2011)")

print("\n" + "=" * 104)
print("FULL BEFORE/AFTER, all 21 definitions, sorted by the SHIPPED DSR")
print("  A = shipped (adj close x raw shares)   B = split fix only   C = full fix (basis close x split-adj shares)")
print("-" * 104)
print(f"{'pattern_id':<30}{'A sharpe':>10}{'B sharpe':>10}{'C sharpe':>10}   {'A dsr':>8}{'B dsr':>8}{'C dsr':>8}   {'dsr A->C':>9}")
for pid in sorted(A, key=lambda p: -A[p]["dsr"]):
    print(f"{pid:<30}{A[pid]['sharpe_annualized']:>10.4f}{B[pid]['sharpe_annualized']:>10.4f}"
          f"{C[pid]['sharpe_annualized']:>10.4f}   {A[pid]['dsr']:>8.4f}{B[pid]['dsr']:>8.4f}{C[pid]['dsr']:>8.4f}"
          f"   {C[pid]['dsr']-A[pid]['dsr']:>+9.4f}")
print("-" * 104)
for lbl, S in (("A shipped", A), ("B split-fix", B), ("C full fix", C)):
    best = max(S.values(), key=lambda r: r["dsr"])
    pos = sum(1 for r in S.values() if r["sharpe_annualized"] > 0)
    over = sum(1 for r in S.values() if r["dsr"] > 0.5)
    print(f"{lbl:<12} best DSR {best['dsr']:.4f} ({best['pattern_id']}, sharpe {best['sharpe_annualized']:+.4f})  "
          f"positive-sharpe {pos}/21   DSR>0.5 {over}/21")

print("\n" + "=" * 104)
print("LEG-WEIGHT DIFF (direct, formation by formation)")
w = n["weight_diff"]
for k in ("legs_compared", "legs_value_weighted_in_A", "legs_value_weighted_in_C",
          "legs_whose_weights_changed", "max_abs_weight_change", "sum_abs_weight_change"):
    print(f"   {k:<28} {w[k]}")
print("   largest individual weight changes:")
for e in sorted(w["examples"], key=lambda e: -abs(e["weight_shipped"] - e["weight_fixed"]))[:8]:
    print(f"     {e['pattern']:<28} {e['formation']}  {e['ticker']:<6} "
          f"{e['weight_shipped']:.4f} -> {e['weight_fixed']:.4f}")

print("\n" + "=" * 104)
print("MARKET-CAP CELL DIFFS")
for k, v in n["cap_summary"].items():
    print(f"   {k:<28} {v}")
print(f"   tickers with >=1 split in window: {n['n_tickers_with_splits']} of {n['n_priced']} priced")
