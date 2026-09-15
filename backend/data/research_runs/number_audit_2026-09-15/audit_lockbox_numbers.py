"""Independent audit of the Set-2 lockbox headline numbers (2026-09-15).

Written from LOCKBOX_PROTOCOL_OSAP.md only. Does NOT import osap_lockbox.py or any
shared project helper -- the project's own rule that a re-derivation sharing helpers
with the builder is not independent (feedback_independent_rederivation_must_not_share_helpers).

Checks performed (each prints PASS/FAIL/INFO):
  C1  reproduce pooled P-clean post-publication standard-haircut Sharpe = 0.599
  C2  members-per-month profile (is the early pool thin?)
  C3  naive t vs my own Newey-West(6) t  -- does NW actually bite?
  C4  Lo (2002) autocorrelation-adjusted annualization vs naive sqrt(12)
  C5  subperiod stability (decade by decade)
  C6  robustness to dropping thin early months
  C7  is the PSR >= 0.95 gate informative at n=612, or vacuous?
"""
import csv
import math
from collections import defaultdict

HERE = __file__.rsplit("/", 1)[0]
OSAP = HERE + "/../postpub_lockbox_2026-09-12/osap"

CLEAN_PRED = {"1_clear", "2_likely"}
CLEAN_QUAL = {"1_good", "2_fair"}
MIN_SEALED = 36
END = "2024-12"


def load_doc():
    meta = {}
    with open(OSAP + "/osap_signal_doc.csv", newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            acr = row["Acronym"].strip()
            if not acr:
                continue
            meta[acr] = row
    return meta


def load_returns():
    with open(OSAP + "/osap_ls_returns_wide.csv", newline="") as fh:
        rd = csv.reader(fh)
        header = next(rd)
        cols = header[1:]
        months, data = [], []
        for row in rd:
            months.append(row[0][:7])          # YYYY-MM
            data.append(row[1:])
    return cols, months, data


def pool(cols, months, data, meta):
    """Equal-weight monthly average of sealed, haircut returns. Returns (months, series, members, n_by_month)."""
    # eligibility per predictor
    start_idx = {}
    haircut = {}
    for j, acr in enumerate(cols):
        m = meta.get(acr)
        if not m:
            continue
        if m["Predictability in OP"].strip() not in CLEAN_PRED:
            continue
        if m["Signal Rep Quality"].strip() not in CLEAN_QUAL:
            continue
        try:
            yr = int(float(m["Year"]))
        except (ValueError, KeyError):
            continue
        start_idx[j] = f"{yr + 1}-01"
        try:
            p = float(m["Portfolio Period"])
            if p <= 0 or math.isnan(p):
                p = 1.0
        except (ValueError, TypeError):
            p = 1.0
        haircut[j] = 20.0 / p / 100.0          # bps/month -> percent/month

    # count sealed months per predictor to apply the >=36 rule
    sealed_count = defaultdict(int)
    for i, mo in enumerate(months):
        if mo > END:
            continue
        for j in start_idx:
            if mo >= start_idx[j] and data[i][j] not in ("NA", ""):
                sealed_count[j] += 1
    eligible = {j for j in start_idx if sealed_count[j] >= MIN_SEALED}

    out_m, out_r, out_n = [], [], []
    for i, mo in enumerate(months):
        if mo > END:
            continue
        vals = []
        for j in eligible:
            if mo < start_idx[j]:
                continue
            v = data[i][j]
            if v in ("NA", ""):
                continue
            vals.append(float(v) - haircut[j])
        if vals:
            out_m.append(mo)
            out_r.append(sum(vals) / len(vals))
            out_n.append(len(vals))
    return out_m, out_r, out_n, len(eligible)


def mean_sd(x):
    n = len(x)
    mu = sum(x) / n
    var = sum((v - mu) ** 2 for v in x) / (n - 1)
    return mu, math.sqrt(var)


def autocorr(x, lag):
    n = len(x)
    mu = sum(x) / n
    num = sum((x[i] - mu) * (x[i - lag] - mu) for i in range(lag, n))
    den = sum((v - mu) ** 2 for v in x)
    return num / den


def newey_west_t(x, lags):
    """t-stat for mean(x)=0 with Newey-West(lags) HAC standard error (Bartlett kernel)."""
    n = len(x)
    mu = sum(x) / n
    e = [v - mu for v in x]
    g0 = sum(v * v for v in e) / n
    s = g0
    for L in range(1, lags + 1):
        gL = sum(e[i] * e[i - L] for i in range(L, n)) / n
        s += 2.0 * (1.0 - L / (lags + 1.0)) * gL
    se = math.sqrt(s / n)
    return mu / se


def sharpe_annual(x):
    mu, sd = mean_sd(x)
    return (mu / sd) * math.sqrt(12.0)


def lo_adjusted_annual(x, q=12):
    """Lo (2002, FAJ, eq. 8/9): annualized SR = q*mu / (sd * sqrt(q + 2*sum_{k=1}^{q-1}(q-k)*rho_k))."""
    mu, sd = mean_sd(x)
    tot = float(q)
    for k in range(1, q):
        tot += 2.0 * (q - k) * autocorr(x, k)
    return (q * mu) / (sd * math.sqrt(tot)), tot


def main():
    meta = load_doc()
    cols, months, data = load_returns()
    mo, r, nmem, n_elig = pool(cols, months, data, meta)

    print("=" * 72)
    print("C1  reproduce the headline")
    print(f"    eligible members      : {n_elig}        (report says 195)")
    print(f"    months                : {len(r)}        (report says 612)")
    print(f"    window                : {mo[0]} -> {mo[-1]}   (report says 1974-01 -> 2024-12)")
    mu, sd = mean_sd(r)
    sr = sharpe_annual(r)
    print(f"    mean %/month          : {mu:.4f}      (report says 0.4202)")
    print(f"    annualized Sharpe     : {sr:.4f}      (report says 0.599)")
    print(f"    VERDICT               : {'PASS' if abs(sr - 0.599) < 0.002 else 'FAIL'}")

    print("=" * 72)
    print("C2  members per month -- how thin is the early pool?")
    for cut in ("1974-01", "1980-01", "1990-01", "2000-01", "2010-01", "2020-01"):
        idx = min(range(len(mo)), key=lambda i: abs((mo[i] > cut) - 0.5) if mo[i] >= cut else 9)
        for i, m_ in enumerate(mo):
            if m_ >= cut:
                idx = i
                break
        print(f"    {cut}: {nmem[idx]:3d} members")
    print(f"    min members in any month: {min(nmem)}  (month {mo[nmem.index(min(nmem))]})")
    thin = sum(1 for v in nmem if v < 20)
    print(f"    months with < 20 members: {thin} of {len(nmem)}")

    print("=" * 72)
    print("C3  naive t vs Newey-West(6)")
    t_naive = mu / (sd / math.sqrt(len(r)))
    t_nw = newey_west_t(r, 6)
    print(f"    naive t               : {t_naive:.4f}")
    print(f"    my Newey-West(6) t    : {t_nw:.4f}     (report says 4.27)")
    print(f"    ratio NW/naive        : {t_nw / t_naive:.4f}")
    print(f"    rho(1)                : {autocorr(r, 1):+.4f}")

    print("=" * 72)
    print("C4  Lo (2002) autocorrelation-adjusted annualization")
    sr_lo, tot = lo_adjusted_annual(r, 12)
    print(f"    naive sqrt(12) Sharpe : {sr:.4f}")
    print(f"    Lo-adjusted Sharpe    : {sr_lo:.4f}")
    print(f"    scale factor vs 12    : {tot / 12.0:.4f}   (<1 means naive UNDERSTATES the annualized Sharpe)")

    print("=" * 72)
    print("C5  subperiod stability (annualized Sharpe by decade)")
    buckets = defaultdict(list)
    for m_, v in zip(mo, r):
        buckets[m_[:3] + "0s"].append(v)
    for k in sorted(buckets):
        seg = buckets[k]
        if len(seg) >= 24:
            print(f"    {k}: n={len(seg):3d}  SR={sharpe_annual(seg):+.3f}")

    print("=" * 72)
    print("C6  drop thin early months (require >= 20 members)")
    keep = [(m_, v) for m_, v, nn in zip(mo, r, nmem) if nn >= 20]
    kr = [v for _, v in keep]
    print(f"    months kept           : {len(kr)} (from {keep[0][0]})")
    print(f"    annualized Sharpe     : {sharpe_annual(kr):.4f}")
    print(f"    Newey-West(6) t       : {newey_west_t(kr, 6):.4f}")

    print("=" * 72)
    print("C7  is PSR >= 0.95 an informative gate at n=612?")
    print("    PSR vs benchmark 0 is ~Phi(SR_monthly * sqrt(n-1)) adjusted for skew/kurtosis.")
    for test_sr_ann in (0.10, 0.20, 0.30, 0.50, 0.599):
        sr_m = test_sr_ann / math.sqrt(12.0)
        z = sr_m * math.sqrt(len(r) - 1)
        psr = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
        print(f"    annualized SR {test_sr_ann:.3f} -> z={z:5.2f} -> PSR~{psr:.4f}")
    print("    (skew/kurtosis adjustment ignored here; this is the order of magnitude)")


if __name__ == "__main__":
    main()
