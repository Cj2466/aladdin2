"""Compare the Phase A re-audit's flat control and edge_spread runs against
each other and against the archived original flat run (research_archive's
full_screen_results.json, fetched on different — earlier — bars, so it is
context, not the baseline; the CONTROL run is the baseline)."""
import json

SCRATCH = "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
ARCHIVE = "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/research_archive/session_2026-08-22_to_27/full_screen_results.json"

with open(f"{SCRATCH}/phase_a_reaudit_flat_control.json") as f:
    flat = {r["pattern_id"]: r for r in json.load(f)["results"]}
with open(f"{SCRATCH}/phase_a_reaudit_edge_spread.json") as f:
    edge = {r["pattern_id"]: r for r in json.load(f)["results"]}
with open(ARCHIVE) as f:
    orig = {r["pattern_id"]: r for r in json.load(f)["results"]}


def stats(d):
    sharpes = [r["sharpe_annualized"] for r in d.values()]
    pos = [s for s in sharpes if s > 0]
    dsr_ok = [
        r for r in d.values()
        if r["deflated_sharpe"]["dsr"] not in (None, "None")
        and float(r["deflated_sharpe"]["dsr"]) > 0.5
    ]
    mean = sum(sharpes) / len(sharpes) if sharpes else float("nan")
    return len(d), len(pos), len(dsr_ok), mean


for label, d in (("archived original (older bars)", orig), ("flat control (this fetch)", flat), ("edge_spread (this fetch)", edge)):
    n, npos, nclear, mean = stats(d)
    print(f"{label:<32} n_measurable={n:>3} positive_sharpe={npos:>3} dsr>0.5={nclear} mean_sharpe={mean:+.3f}")

common = sorted(set(flat) & set(edge))
deltas = [edge[p]["sharpe_annualized"] - flat[p]["sharpe_annualized"] for p in common]
n_up = sum(1 for x in deltas if x > 0)
print(f"\ncommon specs {len(common)}; edge-minus-flat sharpe: mean {sum(deltas)/len(deltas):+.3f}, "
      f"improved {n_up}, worsened {len(deltas)-n_up}")

print(f"\n{'pattern_id':<45} {'ctrl_sh':>8} {'edge_sh':>8} {'d':>7} {'ctrl_dsr':>9} {'edge_dsr':>9}")
by_edge = sorted(common, key=lambda p: -edge[p]["sharpe_annualized"])
for p in by_edge[:15]:
    cd = flat[p]["deflated_sharpe"]["dsr"]
    ed = edge[p]["deflated_sharpe"]["dsr"]
    fmt = lambda v: f"{float(v):.3f}" if v not in (None, "None") else "n/a"
    print(f"{p:<45} {flat[p]['sharpe_annualized']:>8.3f} {edge[p]['sharpe_annualized']:>8.3f} "
          f"{edge[p]['sharpe_annualized']-flat[p]['sharpe_annualized']:>+7.3f} {fmt(cd):>9} {fmt(ed):>9}")

only_flat = sorted(set(flat) - set(edge))
only_edge = sorted(set(edge) - set(flat))
print(f"\nspecs measurable only under flat: {len(only_flat)} {only_flat[:8]}")
print(f"specs measurable only under edge: {len(only_edge)} {only_edge[:8]}")
