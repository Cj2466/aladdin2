# COULD_NOT_VERIFY — hunting-ground review, 2026-09-11

Everything I tried to source and failed to, plus every item in the orchestrator's brief that I did
NOT verify. Nothing here is summarised from memory.

---

## A. Documents that blocked me (403 / paywall / not found)

| Document | URL(s) tried | Result | What I did instead |
|---|---|---|---|
| McLean & Pontiff (2016), SSRN abstract page | `papers.ssrn.com/sol3/papers.cfm?abstract_id=2156623` | HTTP 403 to WebFetch | Read the author-hosted accepted version (source #2). Numbers verified there. |
| Makarov & Schoar (2020), LSE Research Online copy | `researchonline.lse.ac.uk/id/eprint/100409/...pdf`, `eprints.lse.ac.uk/100409/...pdf` | HTTP 403 to both curl and WebFetch | Read the author's own LSE personal-page copy (source #5). |
| Makarov & Schoar, MIT DSpace record | `dspace.mit.edu/entities/publication/7f91bfb5-...` | HTTP 405 Method Not Allowed | as above |
| Senate PSI **staff report** (93 pp.), "Abuse of Structured Financial Products" PDF | `hsgac.senate.gov/wp-content/uploads/imo/media/doc/REPORT-Abuse of Structured Financial Products (Basket Options) (7-22-14, updated 9-30-14).pdf` | HTTP 403 to curl and WebFetch | Read the govinfo hearing record CHRG-113shrg89882 (source #6) instead. **Consequence**: all PSI figures I cite are from members' opening statements and sworn testimony in the hearing record, not from the staff report. If the staff report gives different figures, I have not seen them. |
| Boehmer, Jones, Zhang & Zhang (2021), "Tracking Retail Investor Activity", *Journal of Finance* | Wiley / SSRN / SMU repository — not fetched | Not attempted past search; paywalled at Wiley | I read only the Ardia–Aymard–Cenesizoglu replication (source #7). **Every BJZZ number in the review is second-hand, as reported by the replication paper, and is labelled T2-secondhand.** |
| Novy-Marx & Velikov, *published* RFS version (incl. the capacity / "new capital" result that search snippets attribute to it) | Oxford Academic — paywalled | Not read | I read only the NBER WP version (source #11), which does **not** contain a capacity result I could verify. **I make no capacity claim from this paper.** |
| Hou, Xue & Zhang, *published* RFS version | Oxford Academic — paywalled | Not read | Read the NBER WP (source #16). |

## B. Items in the brief I could NOT verify and therefore drop

1. **"Barber & Odean's retail work"** — I did not fetch or read any Barber & Odean paper. I have
   *no* verified Barber & Odean number. The only thing I can state is that Chague et al. (source #1,
   read) *cite* Barber, Lee, Liu & Odean (2014) and Barber et al. (2019) as finding "less than 3% of
   the frequent day traders present consistent profit", and that Chague et al. say their own results
   confirm that low fraction while contradicting BLLO's finding that top frequent day traders earn
   very high and consistent profits. That is a citation-of-a-citation, tiered **T4** in the review.

2. **Crypto market-maker profitability studies (firm-level realised P&L)** — I found and read a live
   *experiment* on Binance maker orders (source #14), but I did **not** find any study reporting
   realised profits of actual crypto market-making firms comparable to Baron et al. for equities.
   Not established either way.

3. **Kalshi** — no academic or audited evidence on Kalshi maker profitability was located or read.
   Everything I could say about Kalshi would be memory. Dropped entirely.

4. **Odd-lot / retail-flow mechanics beyond the BJZZ replication** — no primary source read.
   No SEC/FINRA report on odd-lot or PFOF economics was fetched.

5. **Closed-end fund discounts** — no source read. I have no post-2015 evidence on whether CEF
   discount strategies are exploitable at small size. Not in the ranking as an evidenced ground.

6. **Small-crypto-pair and maker-rebate programs at specific exchanges** — I read Binance's fee tiers
   only as *reported inside* sources #9 and #14 (both of which state the best tier: taker 1.5bp,
   maker −0.5bp rebate for source #14's BTC perp; source #9's tier table for spot/futures). I did
   **not** fetch Binance's own fee page, so the current live fee schedule is unverified.

7. **Jane Street / Citadel Securities public filings or regulatory findings** — not fetched, not read.
   I have nothing on them. The only firm-level filing I read is Virtu's S-1 (source #4); the only
   other firm figures I have are Baron et al.'s Table 3 summary of Virtu/KCG/GETCO/Flow Traders/Jump
   filings, read inside source #3 rather than from the filings themselves.

8. **CFTC/SEC reports on who provides liquidity** — none fetched. The Kirilenko-authored CFTC-hosted
   version of source #3 exists at cftc.gov but I read the CityU-hosted 2017 version instead.

9. **Collective2 / Darwinex / Numerai track records** — I searched, found no study that measures
   realised, survivorship-corrected performance of small systematic traders on these platforms, and
   read none. One arXiv paper on eToro that surfaced ("Popularity and Performance", arXiv:1406.7729)
   turned out to be about popularity dynamics, not trader profitability; I fetched it, read the
   abstract and model section, found it off-topic, and deleted it rather than cite it. **Deliverable
   section 4 is therefore answered only by the CTA-database literature (source #10), which covers
   professional CTAs, not retail platforms.** The retail-platform question is open.

10. **Whether Polymarket currently charges trading fees** — source #8 states Polymarket charged no
    per-trade fee during its Apr-2024–Apr-2025 measurement window. Whether that is still true on
    2026-09-11 is **unverified**; I did not fetch Polymarket's fee documentation.

11. **Regulatory access** — whether the project owner (Thailand-resident, per project context) can
    lawfully access Polymarket, Kalshi, or Binance derivatives is **entirely unverified**. I read no
    regulatory document on this. It is a gating question for two of the top-ranked grounds and must
    be settled before any of them is worked on.

12. **Alpaca's SIP minute-bar history and Binance data availability** — asserted in the orchestrator's
    brief, taken as given, not independently verified by me in this review.

## C. A guess I made that was wrong, recorded so it isn't repeated

I twice constructed NBER working-paper URLs from a *guessed* paper number rather than from a search
result. `w20591` returned Novy-Marx, "Understanding Defensive Equity" (not McLean & Pontiff);
`w25614` returned Head & Mayer, "Misfits in the Car Industry" (not Makarov & Schoar). Both wrong
files were deleted unread beyond the title page. The lesson: an NBER number is never inferable —
resolve it from a search result, Crossref, or OpenAlex first. (w20721 and w23394 were later obtained
from actual search results and OpenAlex respectively, and their title pages confirm the right papers.)
