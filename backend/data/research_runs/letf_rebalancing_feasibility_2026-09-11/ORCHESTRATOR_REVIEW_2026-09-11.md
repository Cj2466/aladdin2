# Orchestrator review of the feasibility memo — 2026-09-11 (Fable 5.1, main session)

Independent re-verification of `FEASIBILITY_MEMO_2026-09-11.md` (Sonnet agent, commits
`154583d`, `f5d4759`). Everything below was re-run or re-fetched by the orchestrator, not
taken from the agent's report. The memo is NOT edited; corrections are recorded here.

## 1. Re-verified as stated

- Per-underlying `Σ AUM·(L²−L)` recomputed from `letf_universe.csv` by an independent
  script: S&P 500 103.18B, Nasdaq-100 268.85B, Russell 2000 3.47B, Semiconductors 142.26B,
  Biotech 4.22B, Gold Miners 3.35B — matches `flow_scale.json` to the cent. The
  `leverage_sq_minus_l` column is L²−L for every row.
- All four cited source URLs return HTTP 200 on re-fetch (ProShares historical NAV CSV,
  FEDS 2014-106 PDF, EFMA 2024 Lisbon PDF, University of Toronto TSpace post-print of Shum
  et al. 2016).
- ProShares CSV re-downloaded (52,552,331 bytes, identical size): header row as quoted;
  173 tickers; the 12 target tickers present with the row counts the memo reports.
- Direxion product page re-tried with a full Chrome user-agent string: still HTTP 403.

## 2. CORRECTION — ProShares history reaches every fund's inception, not 2008/2013

The memo (Q3 and `aum_sources.md`) states first dates of 2008-01-02 or 2013-01-02 and
calls the 3–4 missing early years "a real, disclosed gap". That is a string-sort artefact:
the file's `Date` column is `MM/DD/YYYY`, so the lexically smallest date is a January 2nd,
not the earliest date. Parsed as dates, the coverage is:

| Ticker | rows | first | last | AUM on first day |
|---|---|---|---|---|
| SSO  | 5,088 | 2006-06-19 | 2026-09-09 | 10,500,000 |
| SDS  | 5,073 | 2006-07-11 | 2026-09-09 | 10,500,000 |
| UPRO | 4,330 | 2009-06-23 | 2026-09-09 | 8,000,180 |
| SPXU | 4,330 | 2009-06-23 | 2026-09-09 | 8,000,083 |
| QLD  | 5,088 | 2006-06-19 | 2026-09-09 | 10,500,000 |
| QID  | 5,073 | 2006-07-11 | 2026-09-09 | 10,500,000 |
| TQQQ | 4,171 | 2010-02-09 | 2026-09-09 | 8,000,080 |
| SQQQ | 4,171 | 2010-02-09 | 2026-09-09 | 8,000,082 |
| UWM  | 4,939 | 2007-01-23 | 2026-09-09 | 26,250,070 |
| TWM  | 4,939 | 2007-01-23 | 2026-09-09 | 26,250,071 |
| URTY | 4,171 | 2010-02-09 | 2026-09-09 | 8,000,080 |
| SRTY | 4,171 | 2010-02-09 | 2026-09-09 | 8,000,083 |

Every first date equals the fund's own inception date from Q2, and the first-day AUM is the
seed capital, which is what an inception row should look like. The `proshares_nav_history_
sample.csv` "first two rows" are therefore not the first two rows. Net effect: the
ProShares AUM history covers the whole Alpaca minute-bar sample (2016-01-04 onward) for all
twelve funds with years to spare. The gap the memo describes does not exist. The
point-in-time caveat (rows are the issuer's current historical record, restatements
undetectable) still stands.

## 3. CORRECTION — SOXX and SOXL/SOXS reference the same index name

SEC full-text search (efts.sec.gov, forms 497K/485BPOS, 2023-01-01..2026-09-11) for the
exact phrase "NYSE Semiconductor Index" returns 24 Direxion Shares ETF Trust filings and 42
iShares Trust filings; iShares' own SOXX product page names the "NYSE Semiconductor Index"
27 times and the third-party SOXL page names the same index. Both issuers therefore
reference the same named index (ICE's NYSE Semiconductor Index, the successor to the PHLX
SOX index both funds tracked before 2021). Not read: the two prospectuses' index
methodology paragraphs — "same name" is verified, "identical methodology" is not, and the
question is moot for the build (section 5).

## 4. Literature finding the memo missed — the return-effect evidence is in Tuzun (2013)

None of the three papers the agent read measures a RETURN effect: Shum et al. regress
end-of-day volatility, Ivanov-Lenkey regress rebalancing demand on returns (Table III: the
mechanical coefficient m(m−1) shrinks to 1.5–3.5 for m=+3 and 7.3–8.8 for m=−3 in the
tail quintiles once flows are counted — a 40–75% / 27–39% offset), and the EFMA paper
extends Ivanov-Lenkey. A pre-registration needs a source-claimed return effect, so the
orchestrator fetched Tuzun, "Are Leveraged and Inverse ETFs the New Portfolio Insurers?",
FEDS 2013-48 (federalreserve.gov/pubs/feds/2013/201348/201348pap.pdf, HTTP 200, 1,858
lines of text, read sections C.1–C.3 and Tables IV–VI). Sample 2006-06-19..2011-12-31, TAQ
intraday prices, all US-listed equity LETFs. Its Eq. (2) regresses the 15:00–16:00 return
(scaled by 20-day σ) on the stock's share of the LETF rebalancing flow implied by the
target index return from the previous close to 15:00, scaled by 20-day ADV. Table IV Panel
A (with the close-to-15:00 return as a control): β = 4.32 for S&P 500 members (s.e. 0.57,
684,869 obs, adj. R² 1.36%), 3.83 for Nasdaq-100 members, 0.86 for Russell 2000 members;
2010–2011 subperiod 3.78 / 3.48 / 0.88. The paper's own translation (p. 15): "the end-of-
day price reaction is 6.9 basis points (4.32 × 0.8% × 2%) in an average large stock" on a
1% index day at December-2011 AUM. Table VI (Eq. 3) finds the next-day reversal: the
lagged flow coefficient on the close→15:00 return is −3.52 for large caps (s.e. 1.08),
−4.24 for technology, −0.35 for small caps. Tuzun also cites Bai, Bond & Hatch (2012) as
finding "both end-of-day LETF price pressure and extra volatility" in 63 real-estate
stocks — NOT fetched, cited only as Tuzun cites it.

## 5. Decisions (orchestrator, within the owner's approval of direction 1)

1. **Scope the historical test to the three ProShares-covered underlyings — SPY, QQQ,
   IWM** — with the rebalancing coefficient built from ProShares AUM only. Direxion's
   share is disclosed as a scaling omission (today: SPXL/SPXS are ~44% of the S&P 500
   coefficient; the memo's universe lists no Direxion Nasdaq-100 fund; the Russell 2000
   row omits Direxion TNA/TZA, which the orchestrator RECALLS exist — a labelled guess the
   builder must verify). The omission scales the signal, it does not change its sign.
2. Semiconductors/biotech/gold-miners are NOT in the historical test (no Direxion history).
   A forward point-in-time AUM store for all issuers is a separate build, not started now.
3. Cheng & Madhavan (2009) stays secondary-source-verified; the formula is also stated
   independently in Ivanov-Lenkey Eq. (6) and used by Tuzun, so the build does not depend
   on obtaining it.
4. The effect size for the power block comes from Tuzun Table IV, not from any of the
   three papers the agent read. See `../letf_rebalancing_2026-09-11/PREREGISTRATION.md`.
5. No paid data is requested. Nothing here touches any live registration.
