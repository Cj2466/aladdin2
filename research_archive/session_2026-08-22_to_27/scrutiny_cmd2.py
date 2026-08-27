import sys, warnings, pickle
warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/wf_d605a76f-0be-1/backend")
import numpy as np, pandas as pd
from datetime import date
from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.cross_sectional import (
    run_cross_sectional_backtest, fixed_universe_membership, CrossSectionalData)
from app.services.research_lab.cross_sectional_commodities import (
    COMMODITIES_UNIVERSE, build_commodities_family, build_commodities_price_panel,
    build_inverse_vol_basis, default_commodities_config)
from app.services.research_lab.metrics import sharpe_ratio
from app.services.research_lab import deflated_sharpe as DS
import inspect
print(inspect.signature(DS.compute_deflated_sharpe))

OUT="/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
BEST="cmd_momentum_l126_h126_inverse_vol"
provider=YFinanceProvider()
panel,_,_=build_commodities_price_panel(provider,end=date.today())
basis=build_inverse_vol_basis(panel)
data=CrossSectionalData(close=panel,leg_weight_basis=basis)
mem=fixed_universe_membership(COMMODITIES_UNIVERSE)
specs={s.pattern_id:s for s in build_commodities_family()}
daily={}
for pid,sp in specs.items():
    rr=run_cross_sectional_backtest(data,sp,default_commodities_config(),mem)
    if rr.status=="ok": daily[pid]=rr.daily_returns
M=pd.DataFrame(daily).dropna(how="any")
C=M.corr(); lam=np.sort(np.linalg.eigvalsh(C.to_numpy()))[::-1]
neff=float(lam.sum()**2/(lam**2).sum())
sh=pd.Series({p:sharpe_ratio(s) for p,s in daily.items()})
sigma=float(sh.std(ddof=1))
best=daily[BEST]
print(f"sigma_sr={sigma:.4f}  neff_eig={neff:.2f}")
print("\nDSR of the best spec at various n_trials (sigma_sr held at the 24-sibling estimate 0.3358):")
for N in (3,4,6,8,12,18,24,48,100):
    d=DS.compute_deflated_sharpe(sharpe_net_annualized=sharpe_ratio(best),returns=best,n_trials=int(N),sigma_sr_annualized=sigma)
    if d.dsr is None:
        print(f"  n_trials={N:4d} -> below MIN_TRIALS_FOR_DSR=5, DSR not computed by the module; "
              f"manual SR0_ann={DS.expected_max_sharpe_under_noise(sigma/np.sqrt(252), N)*np.sqrt(252) if DS.expected_max_sharpe_under_noise(sigma/np.sqrt(252), N) else float('nan'):.3f}")
    else:
        print(f"  n_trials={N:4d} -> SR0_ann={d.expected_max_sharpe_noise_annualized:.3f}  DSR={d.dsr:.4f}  PSR0={d.psr_vs_zero:.4f}")

# sigma_sr measured on subsets that are genuinely distinct bets
mom=[p for p in daily if p.startswith("cmd_momentum")]
iv=[p for p in daily if p.endswith("inverse_vol")]
print(f"\nsigma_sr on 12 momentum-only siblings: {sh[mom].std(ddof=1):.4f}")
print(f"sigma_sr on 12 inverse_vol-only siblings: {sh[iv].std(ddof=1):.4f}")
for lab,sub,N in [("momentum-only",mom,12),("inverse_vol-only",iv,12)]:
    s2=float(sh[sub].std(ddof=1))
    d=DS.compute_deflated_sharpe(sharpe_net_annualized=sharpe_ratio(best),returns=best,n_trials=N,sigma_sr_annualized=s2)
    print(f"  {lab}: N={N} sigma={s2:.4f} -> DSR={d.dsr}")

# ---- beta / neutralization ----
print("\n=== market (EW basket) beta of the best spec ===")
mkt=panel.pct_change(fill_method=None).mean(axis=1).reindex(best.index)
j=pd.concat([best.rename("s"),mkt.rename("m")],axis=1).dropna()
beta=j["s"].cov(j["m"])/j["m"].var(ddof=1)
resid=j["s"]-beta*j["m"]
print(f"  EW-basket sharpe {sharpe_ratio(j['m']):+.3f}; beta {beta:+.3f}; "
      f"beta-neutralized sharpe {sharpe_ratio(resid):+.3f}; alpha t {resid.mean()/(resid.std(ddof=1)/np.sqrt(len(resid))):+.2f}")
# metals factor
metals=panel[["GLD","SLV","PPLT","PALL"]].pct_change(fill_method=None).mean(axis=1).reindex(best.index)
j2=pd.concat([best.rename("s"),mkt.rename("m"),metals.rename("pm")],axis=1).dropna()
X=np.column_stack([np.ones(len(j2)),j2["m"],j2["pm"]])
b,*_=np.linalg.lstsq(X,j2["s"].to_numpy(),rcond=None)
res2=j2["s"].to_numpy()-X@b
print(f"  vs EW basket + precious-metals factor: b_mkt={b[1]:+.3f} b_pm={b[2]:+.3f}; "
      f"residual sharpe {sharpe_ratio(pd.Series(res2,index=j2.index)):+.3f}")
print(f"  EW precious-metals sharpe over window: {sharpe_ratio(metals.dropna()):+.3f}")

# yearly
y=best.groupby(best.index.year).sum()
print("\n  yearly sums:", {int(k):f"{v:+.1%}" for k,v in y.items()})
ex=best.drop(best.abs().nlargest(10).index)
print(f"  sharpe excl 10 largest |days|: {sharpe_ratio(ex):+.3f}; skew {best.skew():+.2f}")
# per-formation-block returns (20 blocks)
blocks=[]
import itertools
fr=run_cross_sectional_backtest(data,specs[BEST],default_commodities_config(),mem)
fd=[f.date for f in fr.formations if f.skipped_reason is None]
for i,d0 in enumerate(fd):
    d1=fd[i+1] if i+1<len(fd) else best.index[-1]
    seg=best.loc[(best.index>d0)&(best.index<=d1)]
    blocks.append((d0.date(),float(seg.sum())))
print("\n  per-formation block returns:", [(str(a),f"{b:+.1%}") for a,b in blocks])
pos=sum(1 for _,b in blocks if b>0)
print(f"  {pos}/{len(blocks)} formation blocks positive; mean {np.mean([b for _,b in blocks]):+.2%} median {np.median([b for _,b in blocks]):+.2%}")
