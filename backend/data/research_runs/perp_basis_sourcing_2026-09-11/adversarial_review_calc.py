"""Adversarial-review computations for ADVERSARIAL_REVIEW_2026-09-11.md (reviewer: Fable 5.1, 2026-09-11).
Every number in that review comes from this script or from a formula the review states.
Reads only the project's own dsr_power functions; writes nothing.
Run from backend/: ./venv/bin/python data/research_runs/perp_basis_sourcing_2026-09-11/adversarial_review_calc.py
"""
import math, sys
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
from app.services.research_lab.dsr_power import dsr_power_report, power_to_pass
PPY=365; BAR=0.95
def pw(sr, years, n_trials=16, skew=0.0, kurt=3.0):
    n=int(years*PPY)
    return power_to_pass(true_sharpe_annualized=sr, threshold=BAR, n_observations=n, n_trials=n_trials,
        sigma_sr_annualized=math.sqrt(PPY/n), periods_per_year=PPY, skewness=skew, kurtosis=kurt)
def req(years, n_trials=16):
    n=int(years*PPY)
    return dsr_power_report(claimed_sharpe_annualized=1.0, threshold=BAR, n_observations=n, n_trials=n_trials,
        sigma_sr_annualized=math.sqrt(PPY/n), periods_per_year=PPY).required_observed_sharpe

# ---- Table 7 (UNRESTRICTED, High tier) and Table 8 (LONG-SPOT-ONLY), transcribed from the extract
# per coin: {year: (SR, Return, Vol, Active%, OtC, N)}
T7 = {
 "BTC": {2020:(2.26,8.29,3.67,28.66,94.00,8616),2021:(2.39,14.81,6.18,34.43,141.52,8760),2022:(0.70,0.28,0.40,9.21,402.50,8760),2023:(1.32,1.11,0.84,7.68,223.33,8760),2024:(11.52,11.97,1.04,22.18,185.50,1682),"All":(1.80,6.38,3.55,20.06,134.94,36578)},
 "ETH": {2020:(3.08,17.12,5.55,37.80,78.54,8616),2021:(3.52,18.08,5.13,34.91,67.81,8760),2022:(1.29,1.19,0.92,8.23,102.14,8760),2023:(1.64,1.81,1.10,10.35,180.40,8760),2024:(10.70,10.98,1.03,20.93,175.00,1682),"All":(2.55,9.59,3.76,22.68,83.71,36578)},
 "BNB": {2020:(6.04,31.23,5.18,55.23,23.17,7815),2021:(6.60,33.13,5.02,48.03,21.44,8760),2022:(2.83,5.01,1.77,16.54,54.77,8760),2023:(2.96,6.27,2.12,18.93,41.62,8760),2024:(4.31,15.11,3.51,53.39,61.21,1682),"All":(4.84,18.41,3.80,35.02,27.28,35777)},
 "DOGE":{2020:(4.90,59.81,12.20,60.12,6.20,4190),2021:(5.93,53.43,9.01,49.19,18.22,8760),2022:(1.49,1.53,1.02,16.92,32.68,8760),2023:(0.85,0.68,0.79,8.37,243.67,8760),2024:(2.75,6.78,2.46,12.72,70.33,1682),"All":(3.58,23.31,6.51,28.79,13.82,32152)},
 "ADA": {2020:(3.88,21.35,5.51,47.61,29.53,8055),2021:(3.41,24.19,7.09,42.18,40.62,8760),2022:(2.33,3.05,1.31,28.52,32.03,8760),2023:(1.12,1.63,1.45,25.24,236.89,8760),2024:(2.23,5.02,2.25,13.20,110.50,1682),"All":(2.68,12.03,4.49,34.60,40.58,36017)},
}
T8 = {
 "BTC": {2022:(0.51,0.08,0.17,0.02,1.00,8760),2023:(0.87,0.26,0.30,2.85,124.00,8760),2024:(11.52,11.97,1.04,22.18,185.50,1682),"All":(1.62,5.49,3.40,14.66,147.92,36578)},
 "ETH": {2022:(0.81,0.53,0.66,0.08,1.33,8760),2023:(1.16,0.48,0.42,3.76,108.67,8760),2024:(10.70,10.98,1.03,20.93,175.00,1682),"All":(2.23,8.15,3.66,18.29,93.21,36578)},
 "BNB": {2022:(0.76,0.16,0.21,0.07,2.00,8760),2023:(0.73,0.28,0.38,2.26,23.75,8760),2024:(2.24,3.02,1.35,9.16,76.00,1682),"All":(3.29,8.96,2.73,16.31,26.92,35777)},
 "DOGE":{2022:(1.03,0.25,0.24,0.05,1.00,8760),2023:(0.49,0.08,0.16,0.73,63.00,8760),2024:(2.75,6.78,2.46,12.72,70.33,1682),"All":(2.52,14.37,5.71,17.18,15.96,32152)},
 "ADA": {2023:(0.88,0.51,0.58,3.46,100.00,8760),2024:(2.23,5.02,2.25,13.20,110.50,1682),"All":(2.11,8.89,4.21,19.25,44.34,36017)},
}
MEMO_POST = {"BTC":(0.51,0.87),"ETH":(0.81,1.16),"BNB":(0.76,0.73),"DOGE":(1.03,0.49),"ADA":(0.88,)}
MEMO_ALL = {"BTC":1.62,"ETH":2.23,"BNB":3.29,"DOGE":2.52,"ADA":2.11}
print("=== A. Label check: memo 'Table 7' constants vs Table 7 / Table 8 ===")
for c in T7:
    t7 = tuple(T7[c][y][0] for y in (2022,2023) if y in T7[c])
    t8 = tuple(T8[c][y][0] for y in (2022,2023) if y in T8[c])
    print(f"{c:5s} memo={MEMO_POST[c]} T7_unrestricted={t7} T8_longspot={t8} | memoAll={MEMO_ALL[c]} T7All={T7[c]['All'][0]} T8All={T8[c]['All'][0]}")

print("\n=== B. Sharpe-convention check: implied hourly mu/sigma and the mu^2 correction ===")
for c in T7:
    a=T7[c]["All"][3]/100; Na=a*8760; sr=T7[c]["All"][0]; ms=sr/math.sqrt(Na)
    # calendar hourly series with 0 when flat: mean=a*mu, var=a*sig^2 + a(1-a)mu^2
    exact = math.sqrt(a)*ms/math.sqrt(1+(1-a)*ms**2)*math.sqrt(8760)
    print(f"{c:5s} active={a:.3f} Na={Na:.0f} hourly mu/sigma={ms:.4f} LM SR={sr} exact calendar SR={exact:.4f} ratio={exact/sr:.5f}")
# worst case: 2022 BTC T8 (active 0.02%): Na=1.75h
a=0.0002; Na=a*8760; ms=0.51/math.sqrt(Na); print(f"T8 BTC 2022: Na={Na:.2f} hours, hourly mu/sigma={ms:.3f} (one 1-hour trade) -> not an effect-size estimate")

print("\n=== C. Trades per year implied by Table 7 (Na / OtC) ===")
for c in T7:
    for y in (2022,2023,2024,"All"):
        sr,ret,vol,act,otc,N = T7[c][y]; Na=act/100*N; tr=Na/otc
        print(f"{c:5s} {str(y):4s} active_hours={Na:7.0f} OtC={otc:6.1f} trades={tr:6.1f}")

print("\n=== D. Lucca-Moench pooling of the post-break years (2022, 2023, 2024-partial) ===")
def pool(tab, coin, years):
    tot_na=0; s1=0; s2=0; hours=0
    for y in years:
        if y not in tab[coin]: continue
        sr,ret,vol,act,otc,N = tab[coin][y]
        Na=act/100*N
        if Na<=0: continue
        NaY = act/100*8760            # active hours per YEAR (the LM annualization unit)
        mu = ret/100/NaY; sig = vol/100/math.sqrt(NaY)   # hourly mu, sigma while active
        tot_na+=Na; s1+=Na*mu; s2+=Na*(sig**2+mu**2); hours+=N
    mu_p=s1/tot_na; var_p=s2/tot_na-mu_p**2; NaY_p=tot_na/(hours/8760)
    return mu_p/math.sqrt(var_p)*math.sqrt(NaY_p), tot_na, hours
# self-check: does pooling the per-year rows reproduce the 'All' column for T7 BTC?
for c in T7:
    sr_chk,_,_=pool(T7,c,[2020,2021,2022,2023,2024]); print(f"  self-check {c}: pooled 2020-24 SR={sr_chk:.2f} vs paper All={T7[c]['All'][0]}")
POOLED={}
for c in T7:
    s7,na7,h7=pool(T7,c,[2022,2023,2024]); s7b,_,_=pool(T7,c,[2022,2023])
    s8,na8,h8=pool(T8,c,[2022,2023,2024]); s8b,_,_=pool(T8,c,[2022,2023])
    POOLED[c]=(s7,s7b,s8,s8b)
    print(f"{c:5s} T7 pooled 2022-24-03={s7:.2f} (2022-23 only {s7b:.2f}, {na7:.0f} active h) | T8 pooled 2022-24-03={s8:.2f} (2022-23 only {s8b:.2f})")

print("\n=== E. Power at n_local=16, both windows, under alternative claims ===")
claims = {}
for c in T7:
    claims[c] = {
      "memo(T8 2022-23 mean)": sum(MEMO_POST[c])/len(MEMO_POST[c]),
      "T7 unrestricted 2022-23 mean": sum(T7[c][y][0] for y in (2022,2023))/2,
      "T7 pooled 2022-24-03": POOLED[c][0],
      "T8 pooled 2022-24-03": POOLED[c][2],
      "T6 full High": T7[c]["All"][0],
    }
for label in ["memo(T8 2022-23 mean)","T7 unrestricted 2022-23 mean","T7 pooled 2022-24-03","T8 pooled 2022-24-03","T6 full High"]:
    print(f"-- claim: {label}")
    for c in T7:
        s=claims[c][label]
        print(f"   {c:5s} SR={s:5.2f}  power7y={pw(s,7.0):.3f}  power2.5y={pw(s,2.5):.3f}")

print("\n=== F. Required observed Sharpe and n_local sensitivity ===")
for yrs in (7.0,2.5):
    for nt in (5,16,37,362,1031):
        print(f"  years={yrs} n_trials={nt:5d} required_obs_SR={req(yrs,nt):.3f}  power@0.69={pw(0.69,yrs,nt):.3f} power@1.01={pw(1.01,yrs,nt):.3f} power@1.80={pw(1.80,yrs,nt):.3f}")

print("\n=== G. Pooling across coins (equal-weight, equal-vol approx): SR_p = mean(SR) / sqrt((1+(n-1)rho)/n) ===")
rho_pairs=[0.89,0.58,0.76,0.82,0.61,0.76,0.84,0.58,0.56,0.78]; rbar=sum(rho_pairs)/len(rho_pairs)
print(f"Table 5 mean pairwise rho of deviation levels = {rbar:.3f}")
for label in ["memo(T8 2022-23 mean)","T7 unrestricted 2022-23 mean","T7 pooled 2022-24-03","T6 full High"]:
    m=sum(claims[c][label] for c in T7)/5
    for rho in (rbar,0.5,0.0):
        f=1/math.sqrt((1+4*rho)/5); sp=m*f
        print(f"  {label:30s} meanSR={m:.2f} rho={rho:.3f} factor={f:.3f} SR_p={sp:.2f} power7y={pw(sp,7.0):.3f} power2.5y={pw(sp,2.5):.3f}")
# 20 coins, rho=rbar, same mean
for label in ["memo(T8 2022-23 mean)","T7 unrestricted 2022-23 mean"]:
    m=sum(claims[c][label] for c in T7)/5; f=1/math.sqrt((1+19*rbar)/20); sp=m*f
    print(f"  20-coin {label}: factor={f:.3f} SR_p={sp:.2f} power7y={pw(sp,7.0):.3f} power2.5y={pw(sp,2.5):.3f}")

print("\n=== H. Moment sensitivity (mixture kurtosis 3/a; negative skew) ===")
for s in (0.69,1.01,1.80):
    for (sk,ku) in ((0,3),(0,15),(0,100),(-1,15),(-2,30)):
        print(f"  SR={s} skew={sk} kurt={ku}: power7y={pw(s,7.0,16,sk,ku):.3f} power2.5y={pw(s,2.5,16,sk,ku):.3f}")

print("\n=== I. Fee bound check (Table 3 formula rho_u = kappa*log(1+C)) ===")
k=1095
for name,spot,fut in (("paper High maker",0.0675,0.0144),("VIP0 taker 10bp spot/5bp fut (spot side UNVERIFIED)",0.10,0.05),("VIP0 maker 10bp spot/2bp fut (spot side UNVERIFIED)",0.10,0.02)):
    C=2*(spot+fut)/100; print(f"  {name}: C={C*1e4:.1f}bp round trip -> rho_u={k*math.log(1+C)*100:.1f}%/yr")
