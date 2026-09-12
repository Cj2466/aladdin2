# COULD NOT VERIFY — small-participant edges review (2026-09-12)

Every claim I could not establish from a source I actually fetched and read. Nothing in this file
is used as evidence anywhere in `SMALL_PARTICIPANT_EDGES_2026-09-12.md`; the review points here
instead. Format: claim · what I tried · status.

## A. Sources that exist but I could not read

1. **Bailey & Jagtiani (1994), "Foreign ownership restrictions and stock prices in the Thai capital
   market", JFE 36(1) 57–87.** Citation verified on RePEc (page fetched and committed); the RePEc
   record says **"No abstract is available for this item"**, and the ScienceDirect copy is gated.
   **I make no claim whatsoever about this paper's findings.** It is the most obviously relevant
   literature to candidate #1 and it remains unread.
2. **OECD Capital Market Review of Thailand 2025, "The public equity market" chapter.** Both curl
   and WebFetch returned **HTTP 403**. Would have given investor-type composition, mai statistics
   and ownership structure from an institutional source instead of a T3 reprint.
3. **SEC Thailand, "SEC Supervision of Short Selling Transactions" (sec.or.th PDF, 2025).**
   HTTP 403 to both curl and WebFetch. The SET circular (T1) covers the eligibility change; the
   SEC's own framing, the naked-short penalty figures and the HFT registration rules are **not**
   sourced by me. The "penalty tripled to 3× illicit profits, minimum THB 1m, effective
   1 Nov 2024" figure appeared only in a search-engine summary → **T4, not used**.
4. **Huang, Rhee, Suzuki & Yasutake, "Shareholder Perks in Japan: Price Movement and Trading Volume
   Around Ex-Benefit Days" (SSRN 2777549).** Found, not read. This is the paper that would carry
   the actual ex-day capture economics for candidate #3.
5. **Sakai, "Shareholder Perks in Japan: A Systematic Literature Review" (Ritsumeikan).** PDF
   downloaded but AES-encrypted; `pypdf` could not extract text without the `cryptography` extra.
   Not read, not cited.
6. **Lakonishok & Vermaelen (1990), Journal of Finance 45, 455–477 — the PUBLISHED version.** I read
   the INSEAD working-paper version (WP 88-40, 46 pages, committed). The published version could
   differ; my "the word 'odd' appears zero times" finding is a statement about the **working paper
   text only**.

## B. Claims I could not establish at all

7. **The legal basis of the odd-lot preference in US tender offers.** The current eCFR text of
   **17 CFR 240.13e-4** and **240.14d-8** contains the string "odd" **zero times** (both fetched
   and committed). Secondary sources assert that "regulation deliberately created" the odd-lot gap;
   on what I read, the provision appears to be **contractual**, offered at the issuer's option.
   Where (if anywhere) the SEC addresses odd-lot priority is **unresolved**.
8. **Whether the EDGAR "odd lot" hits actually grant odd-lot PRIORITY.** The phrase can appear in
   boilerplate that merely mentions odd-lot holders. The measured counts are counts of *documents
   containing the phrase*, and EDGAR counts **filings including amendments**, not distinct offers.
9. **Whether a Thai-resident retail brokerage account can (a) sell local-registered shares onto the
   foreign board, (b) short-sell at all, (c) trade odd lots, and at what commission.** No broker
   document was read. This decides candidate #1 entirely and is the operational half of
   measurement M1.
10. **Foreign-ownership-limit utilisation (headroom) per Thai stock, free or paid.** Not sourced.
    Without it, "the FOL is full" — the precondition of candidate #1 — cannot be dated per name,
    so the measured `-F` premium cannot be conditioned on the limit actually binding.
11. **SET's investor-type, NVDR-flow, short-selling and program-trading DAILY files.** The pages
    exist and were fetched; the numbers render client-side and SET's JSON API returns **HTTP 403**
    to a script. Whether those series are downloadable free in any machine form is **unknown**;
    if they are not, that is a **candidate paid-data gap (provisionally P10)** — logged, not acted
    on, per the standing rule.
12. **SET/mai delisting history.** No free list obtained. Today's 8-of-12 zero-bar result is a
    hand-picked sample, **not** an estimate of the survivorship rate.
13. **SET vs mai membership per symbol.** Yahoo tags all 2,281 Thai lines `exchange = SET`; there is
    no mai flag in the free feed.
14. **SETSMART and other paid SET data products — price and contents.** Not looked up, nothing
    priced, nothing purchased.
15. **Thai retail-trader loss statistics.** Searched; **nothing Thailand-specific found**. The
    project's existing anti-evidence on retail (Chague et al., Brazil, 97% of persistent day traders
    lose) is from the 2026-09-11 review and is **not** a Thai number.
16. **Thai IPO underpricing / first-day returns; Thai SET50-SET100 rebalancing effects; Thai retail
    herding; NVDR premium literature; Thai tender-offer and delisting rules.** No primary source
    read on any of them. The NVDR *structure* is sourced (prospectus, T1); its *pricing literature*
    is not.
17. **The status of each of the 12 named Thai symbols** used in the survivorship probe (SSI, MAX,
    POLAR, EARTH, PACE, NMG, STARK, MORE, IFEC, JAS, TRUE, DTAC). I selected them as *candidates*
    for dead/suspended names; I did **not** verify any one's actual SET status. What is measured is
    bar availability and screener membership only.
18. **The THB/USD rate.** I used **33.2**, implied by SET's own August 2026 statement (THB 75.05bn ≈
    USD 2.26bn) in the T3 reprint. It is not a quoted FX rate and the USD figures in this review are
    therefore approximate by construction.

## C. Part B mechanisms I did not research at all (named in the brief, honestly not covered)

No primary source was read on any of these; they are **unranked**, and their absence from the
ranking is absence of evidence, not evidence of absence. The search that would settle each:

| mechanism | what to read first |
|---|---|
| IPO retail allocations (Thai / HK clawback + lottery / US) | HKEX listing rules on the retail clawback mechanism; SET/SEC Thailand IPO allocation rules; the allocation-discrimination literature (Ritter's IPO data page for underpricing by market) |
| Rights offerings and oversubscription privileges | prospectus language on the oversubscription privilege in US/Thai rights issues; the rights-offering discount literature |
| Dutch-auction self-tenders | Bagwell's work on Dutch-auction repurchases; and whether the odd-lot preference co-occurs |
| Small-cap merger arbitrage below fund size | Mitchell & Pulvino (2001) by deal-size decile; Jetley & Ji on the shrinking spread |
| Share-class / dual-class arbitrage | Froot & Dabora (1999) on Royal Dutch/Shell; modern dual-class spread studies |
| OTC / small-exchange liquidity provision | the OTC market-quality literature; and note the project's measured blocker — Alpaca's free tier returns HTTP 403 for `feed=otc` (P9, ledger #15) |
| Thai shareholder perks | whether SET-listed companies run perk programmes at all, and whether they are per-holder |

## D. Method notes that are limitations, not findings

19. The `-F` premium table is computed on **unadjusted closes** of two lines that may carry
    different corporate-action bases (this is exactly what makes the `-R` series unusable). A
    like-for-like basis check is part of measurement M1 and was **not** done today.
20. The 26.69-year Thai window and its 1.528 threshold assume the whole window is usable. Given the
    survivorship defect (#12) and the basis question (#19), the **effective** usable window is
    unknown and could be much shorter.
