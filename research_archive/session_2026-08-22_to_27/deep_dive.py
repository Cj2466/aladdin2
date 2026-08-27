import json

with open("/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/alpaca_results.json") as f:
    results = json.load(f)

def show(sym, around_dates=None, n_head=5, n_tail=5):
    bars = results[sym]["bars"]
    print(f"\n=== {sym} === total bars {len(bars)}")
    print("Asset:", results[sym]["asset"])
    print("HEAD:")
    for b in bars[:n_head]:
        print(" ", b["t"][:10], "close=", b["c"], "vol=", b["v"])
    print("TAIL:")
    for b in bars[-n_tail:]:
        print(" ", b["t"][:10], "close=", b["c"], "vol=", b["v"])
    if around_dates:
        for target in around_dates:
            print(f"AROUND {target}:")
            idxs = [i for i, b in enumerate(bars) if b["t"][:10] >= target]
            if not idxs:
                print("  (no bars at/after this date)")
                continue
            i0 = idxs[0]
            for i in range(max(0, i0 - 5), min(len(bars), i0 + 5)):
                b = bars[i]
                print(" ", b["t"][:10], "close=", b["c"], "vol=", b["v"])

# CA: Computer Associates -> Broadcom acquisition closed 2018-11-05
show("CA", ["2018-11-01"])
# HCP: Healthpeak ticker changed HCP->PEAK effective 2020-06-01ish; HashiCorp IPO'd 2023-12-13
show("HCP", ["2020-05-25", "2023-12-10"])
# PX: Praxair/Linde merger closed 2018-10-31
show("PX", ["2018-10-25"])
# MON: Bayer/Monsanto merger closed 2018-06-07
show("MON", ["2018-06-01"])
# WRK: Ingevity spinoff completed 2016-05-15
show("WRK", ["2016-05-10"])
# LLL: L3/Harris merger closed 2019-06-29
show("LLL", ["2019-06-25"])
# ARNC: Arconic spinoff 2020-04-01 already known
show("ARNC", ["2020-03-27"])
# DNB: take-private 2019-02, re-IPO 2020-07-01
show("DNB", ["2019-02-01"])
# FI: Fiserv rename 2023-06-07
show("FI", ["2023-06-01"])
# MNK: first bankruptcy filed 2020-10-12, emerged 2022-06-16; second filing 2023-08-28
show("MNK", ["2020-10-08", "2022-06-13"])
# DO: bankruptcy emergence 2021-04-23
show("DO", ["2021-04-19"])
