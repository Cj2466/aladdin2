MAX_WEIGHT_MULTIPLE = 3.0

def apply_weight_cap_more_iters(raw, max_iters):
    total = sum(raw.values())
    weights = {t: w / total for t, w in raw.items()}
    equal_share = 1.0 / len(weights)
    cap = MAX_WEIGHT_MULTIPLE * equal_share
    for it in range(max_iters):
        over = {t: w for t, w in weights.items() if w > cap}
        if not over:
            print(f"  converged after {it} iterations")
            break
        excess_to_redistribute = sum(w - cap for w in over.values())
        under = {t: w for t, w in weights.items() if w <= cap}
        under_total = sum(under.values())
        for t in over:
            weights[t] = cap
        if under_total > 0.0:
            for t in under:
                weights[t] += excess_to_redistribute * (under[t] / under_total)
    else:
        print(f"  DID NOT CONVERGE within {max_iters} iterations")
    return weights

raw = {'T0': 2.0019796134911236, 'T1': 7.628240927476112, 'T2': 6.314432612041357, 'T3': 0.00206849274179782, 'T4': 420100.3011406971, 'T5': 0.008077610593144798, 'T6': 278593.4703299702, 'T7': 380547.3733367, 'T8': 0.007324344688268798, 'T9': 922373.0766561318, 'T10': 0.008630898313076694, 'T11': 70485.59367491718}

for max_iters in [12, 20, 50, 200]:
    print(f"max_iters={max_iters}")
    w = apply_weight_cap_more_iters(dict(raw), max_iters)
    cap = MAX_WEIGHT_MULTIPLE / 12
    viol = {t: v for t,v in w.items() if v > cap + 1e-12}
    print("  sum=", sum(w.values()), "violations:", viol)
