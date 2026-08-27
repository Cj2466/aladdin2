import json

with open("/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/alpaca_results.json") as f:
    results = json.load(f)

def find_flatline_end_and_resume(sym):
    """Find (a) last day of real (pre-flatline) trading, (b) first day volume
    goes to 0 (flatline start), (c) last day of flatline / first day real
    trading resumes with a genuinely different price."""
    bars = results[sym]["bars"]
    events = []
    prev_vol = None
    flatline_start = None
    for i, b in enumerate(bars):
        d = b["t"][:10]
        v = b["v"]
        c = b["c"]
        if prev_vol is not None:
            if prev_vol != 0 and v == 0 and flatline_start is None:
                flatline_start = i
                events.append(("FLATLINE_START", bars[i-1]["t"][:10], bars[i-1]["c"], d, c))
            if flatline_start is not None and v != 0:
                events.append(("RESUME", bars[i-1]["t"][:10], bars[i-1]["c"], d, c))
                flatline_start = None
        prev_vol = v
    return events

for sym in ["CA", "HCP", "PX", "MON", "LLL", "DNB", "DO", "MNK", "ARNC", "ANSS" if False else "WRK"]:
    print(f"\n=== {sym} flatline/resume events ===")
    for e in find_flatline_end_and_resume(sym):
        print(" ", e)

# DNB specific window around the real flagged jump 2020-06-30/07-01
print("\n=== DNB around 2020-06-25 to 2020-07-06 ===")
bars = results["DNB"]["bars"]
for b in bars:
    d = b["t"][:10]
    if "2020-06-2" <= d <= "2020-07-10":
        print(" ", d, "close=", b["c"], "vol=", b["v"])
