from collections.abc import Iterable
from datetime import date

# Point-in-time S&P 600 SMALL-CAP membership: which tickers were ACTUALLY
# index members on a given historical date. The exact analogue of
# sp500_membership_history.py, for the universe that module cannot speak to,
# and written to that module's conventions deliberately — same symbology
# (yfinance dashes, BRK-B not BRK.B), same base-snapshot-plus-dated-events
# storage, same "hard error, never a silent clamp" boundary behavior, same
# habit of stating KNOWN LIMITS before anything is built on it.
#
# WHY A SEPARATE MODULE AND NOT A PARAMETER ON THE S&P 500 ONE: the two
# have genuinely different provenance and genuinely different quality, and
# collapsing them behind one interface would hide exactly that. The S&P 500
# data comes from a maintained point-in-time reconstruction with full
# constituent SNAPSHOTS at every change date; this one is rebuilt from a
# CHANGES table alone, which is a strictly weaker source (see the
# falsification test below). A caller must be able to see which of the two
# it is reading.
#
# SOURCE: Wikipedia, "List of S&P 600 companies" — the current-constituents
# table plus the dated "Selected changes to the list of S&P 600 components"
# table. Confirmed live 2026-08-27: 603 current tickers, 491 dated change
# rows spanning 2019-12-17 .. 2026-08-04, of which 488 carry an inline
# footnote citation and the overwhelming majority cite S&P Dow Jones Indices
# press releases directly (699 spglobal.com references on the page). The
# reason text is specific and checkable rather than boilerplate: 182 rows
# name an acquisition, 207 an S&P 400 promotion/relegation, 58 an S&P 500
# move, 28 a spin-off, 6 a bankruptcy.
#
# WHY NOT THE SAME SOURCE THE S&P 500 MODULE USES: github.com/fja05680/sp500
# publishes point-in-time constituents for the S&P 500 ONLY. Confirmed
# 2026-08-27 that it has no S&P 600 (or S&P 400) equivalent, and no free
# small-cap point-in-time constituent file was found anywhere else. This
# module is therefore built on the best free source that exists for this
# index, which is materially weaker than the S&P 500's — hence the
# quantified quality statement below rather than a claim of parity.
#
# STORAGE. A base universe at MEMBERSHIP_DATA_START plus chronological
# add/remove events, exactly like sp500_membership_history: no network
# dependency at import time, diffable literals, and the same replay
# machinery. The base universe was RECONSTRUCTED by replaying the changes
# table BACKWARD from the current-constituents snapshot, since (unlike the
# S&P 500 source) no historical snapshot is published to start from.
#
# THE FALSIFICATION TEST, run on this data before anything was built on it —
# this project's own standard, and the reason the numbers below are stated
# rather than assumed. A changes table is complete if and only if replaying
# it backward from today's snapshot lands on a set of the index's nominal
# size at every point; DRIFT IS INCOMPLETENESS, since a missing event leaves
# a ticker stranded in (or out of) the replayed set forever after. Measured
# live 2026-08-27:
#  * Today's snapshot is 603 tickers for a nominally 600-COMPANY index (the
#    excess is multi-share-class names, e.g. CENT/CENTA, which the S&P 500
#    data has too — 503 tickers for 500 companies).
#  * Backward replay to 2020-01-01 lands on 612 tickers, and the replayed
#    count over the whole window runs 603 .. 614 — a band of 11 tickers,
#    1.8% of the nominal 600.
#  * The SAME test on this project's existing S&P 500 harness, for
#    calibration: its replayed count runs 498 .. 507 over 2015-2026, a band
#    of 9 tickers, also 1.8% of its nominal 500 (0.8% restricted to 2020
#    onward). So the two datasets sit in the same quality register — which
#    is the honest claim, and NOT the same as saying they are equally good:
#    the S&P 500 band is mostly genuine index drift, because its events are
#    derived from complete snapshots and cannot be missing; this one's band
#    is genuine drift PLUS real missing events, and the two are not
#    separable from the source alone.
#  * The residue that could not be reconciled at all is named, not smoothed
#    away: _UNDATED_REMOVALS and _UNDATED_READDITIONS below (13 tickers
#    total). With those applied at coverage end, forward replay from the
#    base universe reproduces the current 603-ticker snapshot EXACTLY,
#    603/603 — the same round-trip standard sp500_membership_history holds
#    itself to ("verified to reproduce the source file's own final row
#    exactly, 503/503").
#
# INDEPENDENTLY SPOT-VERIFIED 2026-08-27, on events whose real dates are
# known outside this source, chosen deliberately to include the
# failure-driven removals that matter most for survivorship bias: BBBY added
# 2020-06-22 and removed 2023-03-20 (Bed Bath & Beyond, which filed Chapter
# 11 the following month); WW added 2021-09-20, removed 2023-03-20; RILY
# added 2021-04-15, removed 2024-09-23 (B. Riley's 2024 collapse); TUP
# removed 2022-12-19 (Tupperware); APPS added 2022-06-29, removed
# 2024-03-18; GME removed 2021-08-04 (promoted OUT of the small-cap index
# after the meme-stock run — the opposite direction, and correctly dated).
# The table therefore does capture failure-clustered exits with real dates,
# which is the property a survivorship-free candidate pool actually depends
# on.
#
# KNOWN LIMITS — read these before trusting anything built on this module:
#  * COVERAGE STARTS 2020-01-01, not 2015 like the S&P 500 module. The
#    changes table's own first row is 2019-12-17; there is nothing before
#    it, so no earlier base universe can be reconstructed at any quality.
#  * 12 UNDATED REMOVALS (_UNDATED_REMOVALS). Wikipedia dates these
#    tickers' ADDITION but never their removal, and they are absent from the
#    current snapshot, so they left the index on a date this source does not
#    record. They are removed at coverage end, which means each stays
#    ELIGIBLE for an unknown stretch past its real removal date. Chosen over
#    the alternatives deliberately: dropping them outright would delete real
#    members from real historical formations (survivorship bias, the exact
#    failure this module exists to prevent), and inventing a removal date
#    would be a silently-plausible wrong answer. Keeping a departed name
#    eligible too long is the mild, disclosed direction of this error.
#  * 1 UNDATED RE-ADDITION (_UNDATED_READDITIONS): BBT is in the current
#    snapshot, but the changes table records it as REMOVED 2025-09-02 with
#    no later addition (the row describes Berkshire Hills/Brookline's merger,
#    in which the surviving ticker stayed in the index). Restored at
#    coverage end, same treatment and same disclosure.
#  * Ticker-keyed, not company-keyed — identical limitation to
#    sp500_membership_history, and for the identical reason: a rename reads
#    as a same-date removal plus addition. Unlike that module, there is NO
#    rename-correction overlay here (its _EARLIEST_MEMBERSHIP_OVERRIDES has
#    no small-cap equivalent to build from), so ticker renames are simply
#    uncorrected.
#  * This module answers WHO WAS A MEMBER. It does NOT make a
#    survivorship-free backtest possible, and for small caps the gap is
#    WORSE than the S&P 500's, not better — see the measured price-coverage
#    figures in cross_sectional_small_mid_cap.py, which is the module that
#    actually runs against this data. Closing it needs a delisted-securities
#    price vendor this project does not have.

# The changes table's own coverage begins 2019-12-17; 2020-01-01 is the
# first clean calendar boundary at or after it, and is the date the base
# universe below was reconstructed for. Nothing before it can be answered
# at any quality, so it is a hard error rather than a clamp.
MEMBERSHIP_DATA_START = date(2020, 1, 1)
# The last DATED change row on the source page as fetched 2026-08-27. The
# undated reconciliation below is applied on this date too.
MEMBERSHIP_DATA_AS_OF = date(2026, 8, 4)

# The index's nominal COMPANY count. Tickers exceed it slightly because of
# multi-share-class members; used only by the data-quality self-check
# exposed as membership_data_quality().
NOMINAL_INDEX_SIZE = 600

# The 612 constituents on MEMBERSHIP_DATA_START, reconstructed by replaying
# the changes table BACKWARD from the current-constituents snapshot (no
# historical snapshot is published for this index — see the header). 612 for
# a nominally 600-company index: the excess is multi-share-class tickers plus
# the measured incompleteness the falsification test above quantifies.
_BASE_UNIVERSE: tuple[str, ...] = (
    "AAMI", "AAOI", "AAON", "AAT", "AAWW", "ABCB", "ABG", "ABM", "ABTX", "ACA", "ACLS", "ACOR", "ADC",
    "ADEA", "ADTN", "ADUS", "AEGN", "AEIS", "AEL", "AGYS", "AHRT", "AIN", "AIR", "AIT", "AJRD", "AKR",
    "AKRX", "ALG", "ALGT", "ALK", "ALRM", "AMAG", "AMBC", "AMN", "AMPH", "AMSF", "AMWD", "ANDE", "ANF",
    "ANGO", "ANIP", "AORT", "APEI", "APOG", "ARCB", "ARI", "ARLO", "ARNC", "AROC", "ARR", "ASIX", "ASTE",
    "ASTH", "ATNI", "AVA", "AVAV", "AVD", "AVTA", "AWR", "AX", "AXE", "AZZ", "B", "BANC", "BANR",
    "BBT", "BCC", "BCPC", "BEAT", "BELFB", "BFS", "BGG", "BGS", "BHE", "BIG", "BJRI", "BKE", "BLD",
    "BLMN", "BMI", "BNED", "BOOM", "BOOT", "BPFH", "BRC", "BRKL", "BRKS", "CADE", "CAL", "CALM", "CALY",
    "CAMP", "CASH", "CATM", "CATO", "CBB", "CBL", "CBU", "CCOI", "CCRN", "CCS", "CDR", "CENT", "CENTA",
    "CENX", "CEVA", "CHCO", "CHCT", "CHEF", "CHS", "CHUY", "CIR", "CIVI", "CKH", "CLDT", "CLF", "CLW",
    "CMO", "CMTL", "CNMD", "CNR", "CNSL", "CNXN", "COHU", "COKE", "COLB", "CONN", "CORE", "CORT", "CPE",
    "CPF", "CPS", "CPSI", "CRCM", "CROX", "CRVL", "CSGS", "CSII", "CSR", "CTB", "CTRE", "CTS", "CUB",
    "CUBI", "CUTR", "CVBF", "CVCO", "CVET", "CVGW", "CVSA", "CWT", "CYH", "CYTK", "DAKT", "DAR", "DBD",
    "DBI", "DCH", "DCOM", "DDD", "DEA", "DFIN", "DGII", "DIN", "DIOD", "DO", "DORM", "DPLO", "DRH",
    "DRQ", "DSPG", "DXPE", "EBIX", "EBS", "ECHO", "ECOL", "ECPG", "EE", "EGBN", "EGHT", "EGOV", "EGRX",
    "EHTH", "EIG", "ELME", "ELY", "ENDP", "ENSG", "ENVA", "EPAC", "EPAY", "EPRT", "ESE", "ETD", "EVTC",
    "EXLS", "EXPO", "EXPR", "EXTN", "EXTR", "EZPW", "FARO", "FBC", "FBP", "FCF", "FCPT", "FDP", "FELE",
    "FF", "FFBC", "FG", "FIX", "FIZZ", "FL", "FLOW", "FMBI", "FN", "FOE", "FORM", "FORR", "FOSL",
    "FOXF", "FRGI", "FSB", "FSP", "FSS", "FUL", "FUN", "FWRD", "GBCI", "GBX", "GCI", "GCO", "GCP",
    "GEAR", "GEOS", "GES", "GFF", "GHL", "GIII", "GKOS", "GLT", "GLUU", "GME", "GMS", "GNL", "GPI",
    "GPMT", "GPOR", "GPRE", "GTLS", "GTX", "GTY", "GVA", "GWB", "HA", "HAFC", "HAYN", "HCC", "HCI",
    "HFWA", "HI", "HIBB", "HLIT", "HLX", "HMN", "HMST", "HMSY", "HNGR", "HOPE", "HOUS", "HPR", "HSII",
    "HSKA", "HSTM", "HT", "HTLD", "HUBG", "HVT", "HWKN", "HZO", "IBP", "IBTX", "ICHR", "IIIN", "IIPR",
    "ILPT", "INDB", "INGN", "INN", "INVA", "IOSP", "IPAR", "IRBT", "IRDM", "IRT", "ITGR", "ITRI", "IVC",
    "IVR", "JBSS", "JBT", "JCP", "JJSF", "JOE", "JRVR", "KALU", "KAMN", "KELYA", "KFY", "KLIC", "KN",
    "KNSL", "KOP", "KRA", "KREF", "KRG", "KTB", "KWR", "LAD", "LCI", "LCII", "LDL", "LGIH", "LHCG",
    "LL", "LMAT", "LMNX", "LNN", "LNTH", "LOCO", "LPG", "LPSN", "LQDT", "LTC", "LTHM", "LXP", "LXU",
    "LZB", "M", "MANT", "MATV", "MATW", "MATX", "MCRI", "MCS", "MDC", "MDR", "MED", "MEDP", "MEI",
    "MERC", "MGLN", "MGPI", "MHO", "MIK", "MLAB", "MLI", "MMI", "MMSI", "MNRO", "MNTA", "MODV", "MOG-A",
    "MOV", "MPAA", "MPT", "MRTN", "MSTR", "MTH", "MTOR", "MTRN", "MTRX", "MTSC", "MTUS", "MXL", "MYE",
    "MYGN", "MYRG", "NBHC", "NBR", "NBTB", "NE", "NEO", "NEOG", "NFBK", "NMIH", "NP", "NPK", "NPO",
    "NR", "NSA", "NSIT", "NTGR", "NTUS", "NVRI", "NWBI", "NWN", "NX", "NXGN", "NXRT", "NYMT", "OAS",
    "ODP", "OFG", "OFIX", "OII", "OIS", "OMCL", "OMI", "ONB", "ONTO", "OPB", "OPI", "OSIS", "OSPN",
    "OSUR", "OXM", "PAHC", "PARR", "PATK", "PBI", "PCRX", "PDCE", "PDFS", "PEI", "PETS", "PFBC", "PFS",
    "PGTI", "PINC", "PIPR", "PKE", "PLAB", "PLAY", "PLCE", "PLUS", "PLXS", "PMT", "PNTG", "POLY", "POWI",
    "POWL", "PPBI", "PPLI", "PRA", "PRAA", "PRDO", "PRFT", "PRGS", "PRK", "PRLB", "PRSU", "PSMT", "PUMP",
    "QEP", "QLYS", "QNST", "RAVN", "RC", "RDNT", "REGI", "REI", "RES", "REX", "RGNX", "RGP", "RGR",
    "RGS", "RH", "RMAX", "RMBS", "ROCC", "ROCK", "ROG", "ROIC", "RPT", "RRC", "RRD", "RRGB", "RUTH",
    "RWT", "RYAM", "SAFE", "SAFT", "SAH", "SAIA", "SANM", "SBCF", "SBSI", "SCHL", "SCL", "SCSC", "SCVL",
    "SEM", "SENEA", "SFBS", "SFNC", "SGH", "SHAK", "SHEN", "SHOO", "SIG", "SITC", "SJI", "SKYW", "SLCA",
    "SM", "SMP", "SNBR", "SNEX", "SPNT", "SPOK", "SPPI", "SPSC", "SPTN", "SPXC", "SRDX", "SSD", "SSP",
    "SSTK", "STAR", "STBA", "STC", "STMP", "STRA", "SUPN", "SWN", "SXC", "SXI", "SYKE", "TALO", "TBI",
    "TCMD", "TFIN", "TG", "TGI", "THRM", "TILE", "TISI", "TIVO", "TLRD", "TMP", "TNC", "TRHC", "TRST",
    "TSE", "TTEC", "TTGT", "TTI", "TTMI", "TUP", "TVTY", "TWI", "UBA", "UCB", "UCTT", "UEIC", "UFCS",
    "UFI", "UFPI", "UHT", "UIHC", "UIS", "UNF", "UNFI", "UNIT", "UPBD", "USCR", "USNA", "USPH", "UVE",
    "UVV", "VAL", "VBTX", "VECO", "VG", "VGR", "VIAV", "VICR", "VIVO", "VNDA", "VRA", "VRE", "VREX",
    "VRTS", "VRTU", "VRTV", "VSXY", "VTLE", "VTOL", "WABC", "WD", "WDFC", "WDR", "WGO", "WING", "WIRE",
    "WKC", "WLH", "WNC", "WPG", "WRLD", "WSR", "WT", "WTS", "WWW", "XHR", "XNCR", "ZEUS", "ZUMZ",
    "ZYXI",
)

# Tickers whose ADDITION the changes table dates but whose REMOVAL it never
# does, and which are absent from the current snapshot. Removed at
# MEMBERSHIP_DATA_AS_OF by _build_membership_intervals — each therefore stays
# eligible for an unknown stretch past its real removal date. See KNOWN
# LIMITS for why this beats both dropping them and inventing a date.
_UNDATED_REMOVALS: tuple[str, ...] = ("ALSK", "AMEH", "ATGE", "BHLB", "BSIG", "CLI", "IAC", "INT", "MODG", "MPW", "SIX", "VSCO")

# Present in the current snapshot but recorded as removed with no later
# addition (BBT: the 2025-09-02 Berkshire Hills / Brookline merger row, in
# which the surviving ticker in fact stayed in the index). Restored at
# MEMBERSHIP_DATA_AS_OF, same treatment and same disclosure.
_UNDATED_READDITIONS: tuple[str, ...] = ("BBT",)

# (effective date, tickers added that date, tickers removed that date), in
# chronological order, collapsed to one entry per effective date from the
# source's per-row change table. A rename shows up as a same-date
# remove+add pair — see KNOWN LIMITS.
_MEMBERSHIP_EVENTS: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("2020-01-02", ("FBM",), ("RH",)),
    ("2020-01-27", ("SKT",), ("MDR",)),
    ("2020-02-04", ("RUN",), ("DAR",)),
    ("2020-02-06", ("GDOT",), ("WLH",)),
    ("2020-02-13", ("ALEX", "CRMT"), ("CRCM", "DPLO")),
    ("2020-04-17", ("YETI",), ("LHCG",)),
    ("2020-05-01", ("CLB", "MDP"), ("AKRX", "DO")),
    ("2020-05-12", ("CPRI",), ("ACOR",)),
    ("2020-05-22", ("HP",), ("JCP",)),
    ("2020-06-01", ("CHRS", "DHC", "PLMR", "PTEN", "SLP"), ("FG", "LXU", "NE", "OPB", "TIVO")),
    ("2020-06-22", ("BBBY", "BSIG", "CAKE", "DNOW", "MDRX", "MTDR", "REZI"), ("CBL", "GBCI", "HPR", "QLYS", "STRA", "TLRD", "TTI")),
    ("2020-06-25", ("EAT",), ("AXE",)),
    ("2020-06-30", ("BDN", "RPAI"), ("BGG", "BLD")),
    ("2020-07-24", ("FHB",), ("EBS",)),
    ("2020-08-03", ("BANF", "CRS", "DLX"), ("CDR", "EE", "RUN")),
    ("2020-08-17", ("CXW", "FBK"), ("FSB", "VAL")),
    ("2020-09-01", ("BKU", "TRUP"), ("LAD", "REI")),
    ("2020-09-21", ("ATI", "CLI", "COOP", "PBF", "RCM"), ("EXPR", "FOXF", "MEDP", "PEI", "WING")),
    ("2020-09-25", ("FLGT",), ("GTX",)),
    ("2020-10-01", ("CPK",), ("MNTA",)),
    ("2020-10-05", ("SBH",), ("OAS",)),
    ("2020-10-07", ("AGO", "CFFN", "RNST"), ("NEOG", "NR", "SSD")),
    ("2020-11-13", ("FBNC", "GEO", "MD"), ("AMAG", "GPOR", "WPG")),
    ("2020-12-02", ("AAN", "AMCX"), ("GEOS", "RRD")),
    ("2020-12-29", ("SMPL",), ("KNSL",)),
    ("2021-01-07", ("CELH", "ELF"), ("BRKS", "CPRI")),
    ("2021-01-21", ("HTH",), ("YETI",)),
    ("2021-01-29", ("PBH",), ("FBM",)),
    ("2021-02-10", ("ISBC",), ("BEAT",)),
    ("2021-02-12", ("COLL",), ("IRDM",)),
    ("2021-02-16", ("HNI",), ("VRTU",)),
    ("2021-03-01", ("WSFS",), ("CLF",)),
    ("2021-03-22", ("EPC", "VCEL"), ("EXTN", "QEP")),
    ("2021-03-30", ("OI",), ("HMSY",)),
    ("2021-04-08", ("CARA",), ("MTSC",)),
    ("2021-04-12", ("IDCC",), ("CKH",)),
    ("2021-04-15", ("RILY",), ("MIK",)),
    ("2021-04-20", ("UFS",), ("EGOV",)),
    ("2021-05-03", ("GNW", "UTL"), ("GLUU", "WDR")),
    ("2021-05-07", ("TBBK",), ("RCM",)),
    ("2021-05-14", ("EFC",), ("NSA",)),
    ("2021-05-17", ("AVNS",), ("AEGN",)),
    ("2021-05-27", ("JYNT",), ("CUB",)),
    ("2021-06-02", ("ORGO",), ("CROX",)),
    ("2021-06-04", ("SVC",), ("LCI",)),
    ("2021-06-10", ("SLQT",), ("CTB",)),
    ("2021-06-15", ("AMEH",), ("ELY",)),
    ("2021-06-22", ("TWO",), ("CATM",)),
    ("2021-07-07", ("ATGE",), ("BPFH",)),
    ("2021-07-15", ("MSEX",), ("LMNX",)),
    ("2021-08-03", ("STRA",), ("BELFB",)),
    ("2021-08-04", ("INT", "LKFN"), ("GME", "SPOK")),
    ("2021-08-30", ("BLFS", "CNK", "TRMK"), ("SAIA", "SYKE", "USCR")),
    ("2021-09-03", ("THS",), ("CORE",)),
    ("2021-09-07", ("LGND",), ("CBB",)),
    ("2021-09-20", ("HCSG", "QURE", "WW"), ("MSTR", "TISI", "UIHC")),
    ("2021-10-04", ("OPRX", "SLVM"), ("LDL", "STMP")),
    ("2021-10-11", ("CCSI",), ("RGS",)),
    ("2021-10-19", ("FBRT",), ("CMO",)),
    ("2021-10-22", ("HRMY", "TREE"), ("KRG", "RPAI")),
    ("2021-10-29", ("CDMO",), ("CADE",)),
    ("2021-11-05", ("NTCT",), ("IVC",)),
    ("2021-11-09", ("LYLT",), ("AAOI",)),
    ("2021-11-16", ("ONL",), ("DAKT",)),
    ("2021-11-24", ("THRY",), ("ECHO",)),
    ("2021-11-30", ("EBS",), ("UFS",)),
    ("2021-12-02", ("CARS", "KAR", "NVEE"), ("DSPG", "MDP", "RAVN")),
    ("2021-12-20", ("NKTR", "TDS", "TR"), ("M", "POWI", "VICR")),
    ("2021-12-30", ("DOUG",), ("MTRX",)),
    ("2022-01-05", ("ITOS",), ("MGLN",)),
    ("2022-02-01", ("CMP", "TWNK"), ("GWB", "WTS")),
    ("2022-02-03", ("JACK",), ("SPPI",)),
    ("2022-02-15", ("XPEL",), ("PDCE",)),
    ("2022-02-18", ("CRSR", "UE"), ("FMBI", "ONB")),
    ("2022-03-02", ("GDEN", "ZIMV"), ("RRC", "TRHC")),
    ("2022-03-14", ("CRNC",), ("CPS",)),
    ("2022-03-16", ("ASO",), ("KRA",)),
    ("2022-03-30", ("SONO",), ("GTLS",)),
    ("2022-04-04", ("EMBC", "VIR"), ("BNED", "MTDR")),
    ("2022-04-06", ("PRG",), ("FRGI",)),
    ("2022-04-07", ("RCUS",), ("ISBC",)),
    ("2022-04-08", ("GOGO",), ("FLOW",)),
    ("2022-04-26", ("ATEN",), ("FOE",)),
    ("2022-05-03", ("TPH",), ("ECOL",)),
    ("2022-05-17", ("DVAX",), ("EPAY",)),
    ("2022-05-19", ("AOSL",), ("IRT",)),
    ("2022-06-16", ("EYE",), ("REGI",)),
    ("2022-06-21", ("IRWD", "RAMP", "TRN", "URBN", "YELP"), ("ENDP", "GHL", "RRGB", "TCMD", "VRA")),
    ("2022-06-29", ("APPS",), ("TVTY",)),
    ("2022-07-05", ("EHAB", "LRN", "SNCY"), ("LYLT", "NP", "OMCL")),
    ("2022-07-06", ("FTDR",), ("SWN",)),
    ("2022-07-20", ("GRBK",), ("COKE",)),
    ("2022-07-21", ("SHO",), ("VG",)),
    ("2022-07-26", ("SIX",), ("NTUS",)),
    ("2022-08-04", ("AHCO",), ("MTOR",)),
    ("2022-08-10", ("CLFD",), ("CELH",)),
    ("2022-09-01", ("AVID",), ("POLY",)),
    ("2022-09-15", ("CPRX",), ("MANT",)),
    ("2022-09-19", ("AEO", "HPP", "MCY", "MTX", "OUT"), ("APEI", "CAMP", "EHTH", "FOSL", "GLT")),
    ("2022-09-28", ("LESL",), ("GCP",)),
    ("2022-10-03", ("HAIN", "MCW", "STEL", "XPER"), ("ABTX", "EXLS", "HNGR", "SLQT")),
    ("2022-10-12", ("PAYO",), ("LNTH",)),
    ("2022-10-18", ("MLKN",), ("CVET",)),
    ("2022-11-02", ("BFH",), ("UFI",)),
    ("2022-12-01", ("NUS", "SABR"), ("FBC", "PBF")),
    ("2022-12-19", ("AGTI", "CWK", "MBC", "NUVA", "SJW", "SMTC"), ("CATO", "CONN", "DBD", "DHC", "LL", "TUP")),
    ("2023-01-05", ("RXO",), ("JYNT",)),
    ("2023-01-31", ("DV",), ("VIVO",)),
    ("2023-02-02", ("NOG",), ("SJI",)),
    ("2023-02-06", ("CRK",), ("ADC",)),
    ("2023-02-23", ("OTTR",), ("UFPI",)),
    ("2023-03-01", ("VRRM",), ("COLB",)),
    ("2023-03-20", ("AUB", "CBRL", "DY", "HBI", "JBGS", "KMT", "KW", "LUMN", "NEX", "PEB", "RDN", "SLG", "TNDM", "VSAT", "WAFD"), ("BBBY", "FSP", "GPMT", "HT", "ILPT", "MPAA", "OPRX", "ORGO", "PKE", "PNTG", "SRDX", "UEIC", "UIS", "WW", "ZIMV")),
    ("2023-03-21", ("CVI",), ("AAWW",)),
    ("2023-03-22", ("CERT",), ("EXPO",)),
    ("2023-04-03", ("NABL",), ("STAR",)),
    ("2023-04-05", ("PACW",), ("NKTR",)),
    ("2023-05-01", ("CTKB",), ("CSII",)),
    ("2023-06-01", ("BOH",), ("HMST",)),
    ("2023-06-14", ("EXPI", "PRVA"), ("HSKA", "RUTH")),
    ("2023-06-19", ("APAM", "CARG", "CRC", "DAN", "DEI", "DISH", "FULT", "MAC", "MC", "NAVI", "NGVT", "PECO", "SDGR", "SITM", "SPWR", "UFPT", "VSCO", "WLY"), ("BIG", "BOOM", "CARA", "CMTL", "CUTR", "DOUG", "EGRX", "FARO", "GCI", "GCO", "INGN", "LPSN", "PETS", "PLCE", "RYAM", "TG", "TREE", "ZUMZ")),
    ("2023-06-23", ("ABR",), ("ROCC",)),
    ("2023-07-03", ("FTRE", "PHIN"), ("LOCO", "SENEA")),
    ("2023-08-01", ("MSGS",), ("AJRD",)),
    ("2023-08-21", ("MRCY",), ("ARNC",)),
    ("2023-08-22", ("STAA",), ("UBA",)),
    ("2023-08-25", ("AAP",), ("EBS",)),
    ("2023-09-01", ("GSHD", "JXN"), ("NEX", "NUVA")),
    ("2023-09-18", ("APLE", "BXMT", "CATY", "ENR", "HASI", "HIW", "JBLU", "LBRT", "LNC", "NWL", "OMCL", "PZZA", "SXT", "TRIP", "XRX"), ("AAN", "ANGO", "CHRS", "CPSI", "EGHT", "FF", "NTGR", "ONL", "OPI", "QURE", "RMAX", "TSE", "UVE", "VNDA", "ZYXI")),
    ("2023-09-29", ("HAYW",), ("CIVI",)),
    ("2023-10-03", ("DXC", "KLG", "KSS"), ("AVD", "EBIX", "HA")),
    ("2023-10-18", ("NATL", "OGN"), ("ITOS", "ONTO")),
    ("2023-10-20", ("VICR",), ("CIR",)),
    ("2023-11-07", ("ENV",), ("TWNK",)),
    ("2023-11-10", ("AMR",), ("AVID",)),
    ("2023-11-13", ("ACIW",), ("NXGN",)),
    ("2023-11-30", ("CWEN", "CWEN-A", "ICUI", "WOR"), ("AVTA", "PACW", "VRTV")),
    ("2023-12-04", ("WS",), ("SNBR",)),
    ("2023-12-18", ("ALKS", "ALSK", "AWI", "MODG", "NHC", "PJT", "SEDG", "SEE", "VSTS"), ("CDMO", "CLFD", "CYH", "FIX", "IVR", "JRVR", "OFIX", "OSPN", "RMBS")),
    ("2024-01-02", ("RUSHA", "SATS", "VYX"), ("DISH", "LTHM", "RPT")),
    ("2024-01-05", ("PDCO",), ("CHS",)),
    ("2024-01-23", ("BTU",), ("ELF",)),
    ("2024-03-04", ("CXM",), ("MDRX",)),
    ("2024-03-18", ("AL", "ARCH", "BGC", "BL", "BOX", "CALX", "MGEE", "MGY", "MPW"), ("AIT", "APPS", "CCSI", "CRMT", "CYTK", "FORR", "IRBT", "OIS", "TBI")),
    ("2024-04-01", ("NARI", "RUN"), ("CPE", "PGTI")),
    ("2024-04-03", ("FOXF", "VFC"), ("MODV", "SSP")),
    ("2024-04-22", ("CABO",), ("MDC",)),
    ("2024-04-23", ("CNS",), ("KAMN",)),
    ("2024-05-06", ("IAC",), ("AEL",)),
    ("2024-05-07", ("DOCN",), ("AGTI",)),
    ("2024-05-08", ("MARA",), ("AAON",)),
    ("2024-06-24", ("CMA", "GO", "HTZ", "IART", "KRYS", "LEG", "PENN", "RHI", "STEP", "TDW", "VIRT", "WERN", "WHD"), ("ADTN", "ATNI", "CLDT", "CRNC", "HOUS", "MCS", "MED", "MEI", "NFBK", "OSUR", "RGP", "TTEC", "XPER")),
    ("2024-07-03", ("PTGX",), ("WIRE",)),
    ("2024-07-22", ("GTES",), ("ANF",)),
    ("2024-07-26", ("QDEL",), ("HIBB",)),
    ("2024-07-31", ("SNDR",), ("SLCA",)),
    ("2024-08-09", ("SWI",), ("SPWR",)),
    ("2024-09-06", ("INVX",), ("DRQ",)),
    ("2024-09-23", ("ADMA", "ADNT", "CSW", "ETSY", "HELE", "INSP", "MP", "PGNY", "PI", "TGNA", "TGTX", "WOLF", "YOU", "ZD", "ZWS"), ("AMCX", "CHCT", "CMP", "CVGW", "DBI", "DDD", "DIN", "EHAB", "FN", "HVT", "MERC", "NUS", "RILY", "VREX", "ZEUS")),
    ("2024-10-01", ("BBWI", "CURB", "TMDX"), ("CCRN", "ENSG", "MOV")),
    ("2024-10-04", ("CRGY",), ("PRFT",)),
    ("2024-10-09", ("HIMS",), ("VGR",)),
    ("2024-10-11", ("MDU",), ("CHUY",)),
    ("2024-10-15", ("PENG",), ("SGH",)),
    ("2024-11-04", ("ECG",), ("CLW",)),
    ("2024-11-25", ("AZTA", "DFH"), ("ENV", "HAYN")),
    ("2024-11-26", ("AESI",), ("MLI",)),
    ("2024-11-27", ("CON",), ("MYE",)),
    ("2024-12-23", ("AMTM", "CRI", "QRVO", "SKY", "TRNO", "VSH"), ("CMA", "CRS", "HPP", "KELYA", "RGNX", "SVC")),
    ("2024-12-30", ("INSW",), ("CNSL",)),
    ("2025-01-02", ("GDYN",), ("GEAR",)),
    ("2025-01-03", ("ACAD", "JBTM"), ("IBTX", "JBT")),
    ("2025-01-14", ("ENOV",), ("ARCH",)),
    ("2025-01-27", ("ARWR",), ("B",)),
    ("2025-02-10", ("MRP",), ("IRWD",)),
    ("2025-02-13", ("GOLF",), ("ROIC",)),
    ("2025-02-19", ("KAI",), ("NARI",)),
    ("2025-02-25", ("SNDK",), ("LESL",)),
    ("2025-03-24", ("BWA", "CC", "CE", "CLSK", "ESI", "FMC", "FRPT", "KTOS", "MWA", "NEOG", "RHP", "TDC", "TFX", "WSC"), ("ALK", "AMBC", "ATI", "BBWI", "FLGT", "GDOT", "GPRE", "HAIN", "HIMS", "MATV", "NBR", "SATS", "VFC", "WNC")),
    ("2025-04-02", ("ANGI",), ("ODP",)),
    ("2025-04-16", ("ACT",), ("SWI",)),
    ("2025-04-17", ("STRL",), ("PDCO",)),
    ("2025-06-06", ("HTO",), ("SJW",)),
    ("2025-07-01", ("RAL",), ("WOLF",)),
    ("2025-07-18", ("VCTR",), ("AVAV",)),
    ("2025-07-29", ("VCYT",), ("TGI",)),
    ("2025-08-06", ("KGS",), ("NVEE",)),
    ("2025-09-02", ("ADAM", "BHLB", "KNTK", "SRPT"), ("BBT", "BRKL", "NYMT", "PPBI")),
    ("2025-09-08", ("PRKS",), ("FL",)),
    ("2025-09-09", ("MIR",), ("GMS",)),
    ("2025-09-22", ("ACHC", "CZR", "ENPH", "HL", "MAN", "MKTX", "NE", "QTWO", "WAY", "WEN"), ("BGS", "JACK", "KTOS", "MLAB", "MP", "OMI", "PUMP", "SLP", "TTGT", "XRX")),
    ("2025-09-24", ("REYN",), ("SPTN",)),
    ("2025-09-26", ("ACMR",), ("KLG",)),
    ("2025-10-06", ("WU",), ("COOP",)),
    ("2025-10-20", ("BTSG",), ("VBTX",)),
    ("2025-10-31", ("KMX",), ("USNA",)),
    ("2025-11-04", ("EMN",), ("CAL",)),
    ("2025-11-13", ("RRR",), ("STRL",)),
    ("2025-11-28", ("PTCT", "UPWK"), ("PINC", "SNDK")),
    ("2025-12-02", ("FIBK",), ("HBI",)),
    ("2025-12-11", ("VITL",), ("HSII",)),
    ("2025-12-15", ("SEZL",), ("VTLE",)),
    ("2025-12-22", ("CWST", "HE", "INDV", "IRDM", "LKQ", "MHK", "NSP", "POWI", "PRGO", "PRIM", "SOLS", "UA", "UAA", "VAC"), ("ASIX", "BWA", "CEVA", "DY", "HELE", "HL", "MGPI", "RC", "RGR", "SCVL", "SITC", "SPXC", "THRY")),
    ("2025-12-26", ("OPLN",), ("KAR",)),
    ("2026-01-07", ("VSNT",), ("BDN",)),
    ("2026-01-26", ("WINA",), ("GES",)),
    ("2026-01-30", ("AMRX",), ("TTMI",)),
    ("2026-02-02", ("APLS", "LZ"), ("AEIS", "ELME")),
    ("2026-02-09", ("ADT",), ("ARWR",)),
    ("2026-02-10", ("OSW",), ("DVAX",)),
    ("2026-02-11", ("MBIN",), ("THS",)),
    ("2026-02-12", ("RNG",), ("HI",)),
    ("2026-03-13", ("NSSC",), ("ALEX",)),
    ("2026-03-23", ("AGX", "ASGN", "GTM", "KMPR", "LAUR", "LIF", "LTH", "LW", "LYFT", "MOH", "MTCH", "PAYC", "RITM", "SPHR", "VSEC"), ("AHRT", "ANGI", "BLMN", "CARS", "CTRE", "IDCC", "INN", "KREF", "MOG-A", "MYGN", "PLAY", "SITM", "SOLS", "SXC", "VICR")),
    ("2026-03-25", ("COCO",), ("TGNA",)),
    ("2026-04-02", ("VGNT",), ("TWI",)),
    ("2026-04-09", ("ATMU", "BNL"), ("AL", "DOCN")),
    ("2026-04-10", ("DBD",), ("SEE",)),
    ("2026-04-24", ("EFOR",), ("ASGN",)),
    ("2026-05-01", ("LFST",), ("GDEN",)),
    ("2026-05-08", ("AGNT",), ("EXPI",)),
    ("2026-05-14", ("ALHC", "BFAM", "RELY"), ("APLS", "SNCY", "TPH")),
    ("2026-05-18", ("FLO", "PTON"), ("CSGS", "NVRI")),
    ("2026-05-19", ("FG",), ("MCW",)),
    ("2026-05-27", ("UTI",), ("VRE",)),
    ("2026-06-01", ("DAVE",), ("AMWD",)),
    ("2026-06-02", ("EPAM",), ("SSTK",)),
    ("2026-06-09", ("DMC",), ("FDP",)),
    ("2026-06-16", ("FA",), ("KW",)),
    ("2026-06-22", ("BLKB", "CACC", "CNXC", "COTY", "CPB", "EBC", "IVT", "LAZ", "LQDA", "NIC", "POOL", "RSI", "USLM", "WRBY", "WSBC"), ("CABO", "CTKB", "EMBC", "ETD", "FWRD", "GOGO", "IIIN", "MNRO", "OXM", "PRAA", "SANM", "SMTC", "UHT", "VIAV", "VITL")),
    ("2026-06-29", ("NTST",), ("PRA",)),
    ("2026-07-01", ("CAG", "GPOR", "MBGL", "NHI"), ("ARI", "CLB", "GDYN", "SEM")),
    ("2026-07-06", ("GT",), ("STEL",)),
    ("2026-07-08", ("LEU", "MFP"), ("RWT", "WSR")),
    ("2026-07-15", ("SEI",), ("CPRX",)),
    ("2026-07-17", ("KRMN",), ("BTSG",)),
    ("2026-07-22", ("ROAD",), ("MOH",)),
    ("2026-07-24", ("TPC",), ("KRYS",)),
    ("2026-07-27", ("VVX",), ("AVNS",)),
    ("2026-08-03", ("FIVN",), ("TWO",)),
    ("2026-08-04", ("ADIG",), ("HTZ",)),
)

# Parsed once at import, same reasoning as sp500_membership_history's own
# _EVENTS: cheaper than parsing ISO strings on every lookup, and keeps the
# literals above readable and diffable as plain dates.
_EVENTS: tuple[tuple[date, tuple[str, ...], tuple[str, ...]], ...] = tuple(
    (date.fromisoformat(effective), added, removed)
    for effective, added, removed in _MEMBERSHIP_EVENTS
)


class SmallCapPointInTimeUniverseError(ValueError):
    """Raised when a requested date falls outside this vendored data's
    coverage. A hard error rather than a silent clamp to the nearest covered
    date, for exactly the reason sp500_membership_history.
    PointInTimeUniverseError gives: a backtest quietly told "the 2017
    small-cap index looked exactly like the 2020 one" is worse than one that
    fails loudly, and silently-plausible wrong answers are the whole failure
    mode this module exists to remove.

    Deliberately its OWN exception type rather than a reuse of the S&P 500
    module's: a caller catching one must not accidentally swallow the other,
    because the two speak to different universes with different coverage
    windows, and "no small-cap data for this date" and "no large-cap data
    for this date" call for different fixes."""


def _build_membership_intervals() -> dict[str, list[tuple[date, date | None]]]:
    """Replays the events once into per-ticker [start, end) intervals, end
    None meaning "still a member at the end of coverage" — the same
    construction sp500_membership_history._build_membership_intervals uses,
    plus the coverage-end reconciliation step this data needs and that one
    does not.

    A ticker can legitimately have several intervals: genuine index
    re-entries are common in the small-cap index (a name relegated to the
    S&P 600 from the S&P 400, promoted back, then relegated again)."""
    open_since: dict[str, date] = {ticker: MEMBERSHIP_DATA_START for ticker in _BASE_UNIVERSE}
    intervals: dict[str, list[tuple[date, date | None]]] = {}
    for effective, added, removed in _EVENTS:
        for ticker in removed:
            started = open_since.pop(ticker, None)
            if started is not None:
                intervals.setdefault(ticker, []).append((started, effective))
        for ticker in added:
            if ticker not in open_since:
                open_since[ticker] = effective

    # The coverage-end reconciliation (see _UNDATED_REMOVALS /
    # _UNDATED_READDITIONS and the KNOWN LIMITS above). Applied here, as its
    # own explicit step AFTER every dated event, rather than being folded
    # into _MEMBERSHIP_EVENTS: an undated correction must never become
    # indistinguishable from sourced, dated history — and one of these lands
    # on a day that already carries a real event, where merging them would
    # do exactly that.
    for ticker in _UNDATED_REMOVALS:
        started = open_since.pop(ticker, None)
        if started is not None:
            intervals.setdefault(ticker, []).append((started, MEMBERSHIP_DATA_AS_OF))
    for ticker in _UNDATED_READDITIONS:
        if ticker not in open_since:
            open_since[ticker] = MEMBERSHIP_DATA_AS_OF

    for ticker, started in open_since.items():
        intervals.setdefault(ticker, []).append((started, None))
    return {ticker: sorted(spans) for ticker, spans in intervals.items()}


_INTERVALS: dict[str, list[tuple[date, date | None]]] = _build_membership_intervals()


def get_universe_as_of(target_date: date) -> list[str]:
    """The S&P 600's actual constituents on `target_date`, sorted. Raises
    SmallCapPointInTimeUniverseError outside [MEMBERSHIP_DATA_START,
    MEMBERSHIP_DATA_AS_OF]. Removals are applied before additions within a
    single effective date; the two sets are disjoint by construction, so the
    order is defensive rather than load-bearing.

    Reads the replayed INTERVALS rather than re-walking the raw events, so
    that this function and was_member can never disagree — in particular so
    that the coverage-end reconciliation, which lives only in the interval
    builder, is applied identically by both."""
    if target_date < MEMBERSHIP_DATA_START or target_date > MEMBERSHIP_DATA_AS_OF:
        raise SmallCapPointInTimeUniverseError(
            f"No point-in-time S&P 600 membership data for {target_date.isoformat()}; "
            f"coverage is {MEMBERSHIP_DATA_START.isoformat()} to {MEMBERSHIP_DATA_AS_OF.isoformat()}."
        )
    return sorted(t for t in _INTERVALS if was_member(t, target_date))


def get_universe_over(start: date, end: date) -> list[str]:
    """Every ticker that was an S&P 600 member on ANY day in [start, end],
    sorted — the right primitive for a lookback WINDOW, as opposed to
    get_universe_as_of's single-day answer, and the exact analogue of
    sp500_membership_history.get_universe_over (same clamping contract, same
    reasoning).

    A walk-forward replay over [start, end] could have held anything that
    was a member at any point in it, so the union — not the intersection,
    and emphatically not the end-date snapshot — is what a survivorship-free
    candidate pool means.

    `end` is CLAMPED to MEMBERSHIP_DATA_AS_OF rather than rejected: the
    natural call passes end=today, and refusing that would make the function
    unusable for its only real use. `start` is NOT clamped — a start before
    the data begins means the caller is asking about a period this module
    genuinely cannot speak to, which must fail loudly."""
    if start > end:
        raise SmallCapPointInTimeUniverseError(
            f"start {start.isoformat()} is after end {end.isoformat()}."
        )
    if start < MEMBERSHIP_DATA_START:
        raise SmallCapPointInTimeUniverseError(
            f"No point-in-time S&P 600 membership data for {start.isoformat()}; "
            f"coverage starts {MEMBERSHIP_DATA_START.isoformat()}."
        )
    capped_end = min(end, MEMBERSHIP_DATA_AS_OF)
    members: set[str] = set()
    for ticker, spans in _INTERVALS.items():
        for began, ended in spans:
            if began <= capped_end and (ended is None or ended > start):
                members.add(ticker)
                break
    return sorted(members)


def was_member(ticker: str, on: date) -> bool:
    """Whether `ticker` was an S&P 600 constituent on `on`. False outside the
    covered window too — a caller that needs to distinguish "no" from
    "unknown" should compare against MEMBERSHIP_DATA_START /
    MEMBERSHIP_DATA_AS_OF itself.

    This is the MembershipFn the cross-sectional harness takes: pass it as
    `membership_fn` so the harness's point-in-time eligibility gate asks
    about S&P 600 membership instead of defaulting to the S&P 500's
    was_member, which answers False for every small cap and would make the
    entire universe ineligible on every formation date (see
    cross_sectional.EmptyEligibleUniverseError)."""
    for started, ended in _INTERVALS.get(ticker, ()):
        if started <= on and (ended is None or on < ended):
            return True
    return False


def get_membership_intervals(ticker: str) -> list[tuple[date, date | None]]:
    """This ticker's [start, end) index-membership intervals in
    chronological order, end None meaning "still a member at the end of
    coverage". Empty list for a ticker that was never an S&P 600 member in
    the covered window — a large cap, an ETF, or a member whose entire
    tenure predates MEMBERSHIP_DATA_START. Callers must not read an empty
    list as "definitely never in the S&P 600"; it means "no membership
    recorded in this window"."""
    return list(_INTERVALS.get(ticker, ()))


def membership_data_quality() -> dict[str, object]:
    """This dataset's own falsification-test numbers, computed from the
    vendored literals rather than quoted from the header comment — so a
    future edit to the data that degrades its quality shows up here (and in
    the test that asserts on it) instead of leaving a stale prose claim
    behind. See the header's FALSIFICATION TEST section for what each number
    means and what the S&P 500 harness's own comparable values are.

    Returned as data, not logged or printed, following the same convention
    the cross-sectional modules use for their diagnostic counts: a number a
    caller might act on must be a value, never a log line that could go
    unread."""
    counts = [len(get_universe_as_of(MEMBERSHIP_DATA_START))]
    for effective, _added, _removed in _EVENTS:
        counts.append(len(get_universe_as_of(effective)))
    counts.append(len(get_universe_as_of(MEMBERSHIP_DATA_AS_OF)))
    return {
        "coverage_start": MEMBERSHIP_DATA_START,
        "coverage_end": MEMBERSHIP_DATA_AS_OF,
        "n_dated_events": len(_EVENTS),
        "n_base_universe": len(_BASE_UNIVERSE),
        "n_ever_member": len(_INTERVALS),
        "min_members": min(counts),
        "max_members": max(counts),
        # The band as a fraction of the index's nominal company count — the
        # single number to compare against another point-in-time dataset's
        # own. 1.8% here; 1.8% for this project's S&P 500 data over its full
        # window, 0.8% over 2020 onward.
        "member_count_drift_fraction": (max(counts) - min(counts)) / NOMINAL_INDEX_SIZE,
        "n_undated_removals": len(_UNDATED_REMOVALS),
        "n_undated_readditions": len(_UNDATED_READDITIONS),
    }


def _as_dates(values: Iterable[object]) -> list[date]:
    """Accepts pandas Timestamps, datetimes, or plain dates — the replay
    index handed in by the strategy modules is a DatetimeIndex, but the
    membership logic itself is pure stdlib and must not import pandas just
    for this. Same helper, same reasoning, as sp500_membership_history."""
    return [value.date() if hasattr(value, "date") else value for value in values]  # type: ignore[misc]


def build_membership_warnings(ticker: str, replay_dates: Iterable[object]) -> list[str]:
    """Point-in-time universe disclosure for a backward-looking backtest:
    given the trading days a run actually replayed, say plainly which of them
    fall outside this ticker's real S&P 600 membership. Deliberately a
    WARNING and not a filter, for the same reason
    sp500_membership_history.build_membership_warnings is.

    Returns [] for a ticker with no recorded membership: no S&P 600 claim is
    being made about it, so there is nothing to disclose."""
    spans = _INTERVALS.get(ticker)
    dates = sorted(_as_dates(replay_dates))
    if not spans or not dates:
        return []

    warnings: list[str] = []
    total = len(dates)

    uncovered = sum(1 for d in dates if d < MEMBERSHIP_DATA_START)
    if uncovered:
        warnings.append(
            f"Point-in-time S&P 600 membership data starts {MEMBERSHIP_DATA_START.isoformat()}; "
            f"{uncovered} of the {total} replayed trading days precede it and were not checked "
            f"for index membership."
        )

    joined = spans[0][0]
    if joined > MEMBERSHIP_DATA_START:
        n_before = sum(1 for d in dates if d < joined)
        if n_before:
            warnings.append(
                f"{ticker} joined the S&P 600 on {joined.isoformat()}; {n_before} of the {total} "
                f"replayed trading days precede that date. Treat the result as inclusion-biased, "
                f"not a clean out-of-sample estimate."
            )

    left = spans[-1][1]
    if left is not None:
        n_after = sum(1 for d in dates if d >= left)
        if n_after:
            suffix = (
                " (an UNDATED removal — this date is coverage end, not the real removal date; "
                "see _UNDATED_REMOVALS)"
                if ticker in _UNDATED_REMOVALS
                else ""
            )
            warnings.append(
                f"{ticker} left the S&P 600 on {left.isoformat()}{suffix}; {n_after} of the "
                f"{total} replayed trading days follow that date and fall outside the universe."
            )

    return warnings
