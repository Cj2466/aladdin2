import sys, time
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/agent-a327c9fd73bf9f348/backend")
import yfinance as yf

missing = "AABA, ABC, ABMD, ADS, AGN, ALTR, ALXN, ANSS, ANTM, ARG, ARNC, ATVI, AVP, BCR, BHGE, BK, BLL, BRCM, BXLT, CA, CBS, CCE, CDAY, CELG, CERN, CFN, CHK, CMA, CMCSK, COG, COV, CPGX, CTL, CTLT, CTRA, CTXS, CVC, CXO, DAY, DFS, DISCA, DISCK, DISH, DNB, DNR, DO, DRE, DTV, DWDP, ENDP, ESV, ETFC, FBHS, FDO, FI, FL, FLIR, FLT, FRC, FTR, GAS, GGP, GMCR, GPS, HAR, HBI, HCBK, HCP, HES, HFC, HOLX, HRS, HSP, IPG, JEC, JNPR, JOY, JWN, K, KORS, KRFT, KSU, LLL, LLTC, LM, LO, LVLT, MJN, MMC, MNK, MON, MRO, MWV, MXIM, MYL, NBL, NLOK, NLSN, PBCT, PCP, PDCO, PEAK, PETM, PKI, PLL, PX, PXD, QEP, RAI, RE, RHT, RTN, SATS, SEE, SIAL, SIVB, SNI, SRCL, STJ, SWN, SWY, SYMC, TEG, TGNA, TIF, TMK, TSS, TWC, TWTR, UTX, VAR, VIAB, VIAC, WBA, WCG, WFC, WFM, WIN, WLTW, WRK, WYND, XEC, XL, XLNX".split(", ")
print(f"n missing to retry: {len(missing)}", flush=True)

resolved = []
still_missing = []
for i, t in enumerate(missing):
    try:
        df = yf.download(t, start="2015-01-07", end="2026-08-26", auto_adjust=True, progress=False, threads=False)
        if df is not None and not df.empty:
            resolved.append((t, len(df)))
        else:
            still_missing.append(t)
    except Exception as e:
        still_missing.append(t)
    if (i+1) % 20 == 0:
        print(f"...{i+1}/{len(missing)} done, resolved so far: {len(resolved)}", flush=True)
    time.sleep(0.15)

print(f"\nRESOLVED ON RETRY (individual, serial): {len(resolved)} / {len(missing)}")
for t, n in resolved:
    print(f"  {t}: {n} rows")
print(f"\nSTILL MISSING after individual retry: {len(still_missing)} / {len(missing)}")
print(", ".join(sorted(still_missing)))
