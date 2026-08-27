import json

with open("/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/alpaca_results.json") as f:
    results = json.load(f)

def flatline_resume_events(bars):
    events = []
    prev_vol = None
    flatline_active = False
    for i, b in enumerate(bars):
        v = b["v"]
        if prev_vol is not None:
            if prev_vol != 0 and v == 0 and not flatline_active:
                flatline_active = True
                fl_start_idx = i
            if flatline_active and v != 0:
                # only report flatlines lasting >= 5 calendar bars (i.e. not just a
                # weekend/holiday quirk) to avoid noise from 1-day data gaps
                gap_days = i - fl_start_idx
                if gap_days >= 5:
                    events.append({
                        "last_real": (bars[fl_start_idx-1]["t"][:10], bars[fl_start_idx-1]["c"]),
                        "flatline_price": bars[fl_start_idx]["c"],
                        "gap_bars": gap_days,
                        "resume": (b["t"][:10], b["c"]),
                    })
                flatline_active = False
        prev_vol = v
    return events

flagged_new = {}
for sym, r in results.items():
    bars = r.get("bars") or []
    if not bars:
        continue
    events = flatline_resume_events(bars)
    if events:
        flagged_new[sym] = events

already_known = {"CA","HCP","PX","MON","LLL","DNB","DO","MNK","ARNC"}
print("Tickers with a >=5-bar flatline+resume gap (potential recycling signature):")
for sym in sorted(flagged_new):
    tag = "" if sym in already_known else "  <<< NEWLY FOUND, not previously flagged"
    print(f"\n{sym}{tag}")
    for e in flagged_new[sym]:
        print(" ", e)
