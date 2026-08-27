import sys
from datetime import date
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/agent-a327c9fd73bf9f348/backend")
from app.services.research_lab.sp500_membership_history import (
    MEMBERSHIP_DATA_START, get_universe_over, get_universe_as_of, membership_coverage_end,
)
start = MEMBERSHIP_DATA_START
end = date.today()
uni = get_universe_over(start, end)
cov = membership_coverage_end()
cur = get_universe_as_of(min(end, cov))
print("universe size:", len(uni))
print("coverage_end:", cov, "current members:", len(cur))
cur_in_uni = [t for t in uni if t in set(cur)]
print("current-in-universe:", len(cur_in_uni))
print("departed:", len(uni) - len(cur_in_uni))

missing_txt = """AABA, ABC, ABMD, ADS, AGN, ALTR, ALXN, ANSS, ANTM, ARG, ARNC, ATVI, AVP, BCR, BHGE, BK, BLL, BRCM, BXLT, CA, CBS, CCE, CDAY, CELG, CERN, CFN, CHK, CMA, CMCSK, COG, COV, CPGX, CTL, CTLT, CTRA, CTXS, CVC, CXO, DAY, DFS, DISCA, DISCK, DISH, DNB, DNR, DO, DRE, DTV, DWDP, ENDP, ESV, ETFC, FBHS, FDO, FI, FL, FLIR, FLT, FRC, FTR, GAS, GGP, GMCR, GPS, HAR, HBI, HCBK, HCP, HES, HFC, HOLX, HRS, HSP, IPG, JEC, JNPR, JOY, JWN, K, KORS, KRFT, KSU, LLL, LLTC, LM, LO, LVLT, MJN, MMC, MNK, MON, MRO, MWV, MXIM, MYL, NBL, NLOK, NLSN, PBCT, PCP, PDCO, PEAK, PETM, PKI, PLL, PX, PXD, QEP, RAI, RE, RHT, RTN, SATS, SEE, SIAL, SIVB, SNI, SRCL, STJ, SWN, SWY, SYMC, TEG, TGNA, TIF, TMK, TSS, TWC, TWTR, UTX, VAR, VIAB, VIAC, WBA, WCG, WFC, WFM, WIN, WLTW, WRK, WYND, XEC, XL, XLNX"""
missing = [t.strip() for t in missing_txt.split(",")]
print("n missing parsed:", len(missing))
notin = [t for t in missing if t not in set(uni)]
print("missing tickers not in universe:", notin)
curset = set(cur)
missing_current = sorted([t for t in missing if t in curset])
print("MISSING tickers that ARE CURRENT members:", len(missing_current), missing_current)
departed = [t for t in uni if t not in curset]
md = [t for t in missing if t not in curset]
print("departed count:", len(departed), "missing-and-departed:", len(md), "rate:", len(md)/len(departed))
