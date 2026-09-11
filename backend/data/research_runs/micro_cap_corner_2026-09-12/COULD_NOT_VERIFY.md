# COULD_NOT_VERIFY — micro-cap forced-flow sourcing, 2026-09-12

Everything on this page is something I tried to establish and could not, or deliberately did not
attempt. Nothing here supports any claim in `FORCED_FLOW_SOURCING_2026-09-12.md`; where a deliverable
depends on one of these, it says so and declines rather than assumes.

---

## A. Sources the brief named that I did not fully read

- **A.1 Wardlaw, "Measuring Mutual Fund Flow Pressure as Shock to Stock Returns", JF 75(6), 2020 —
  ABSTRACT ONLY.** The brief said this "MUST be read". I fetched and quoted the abstract verbatim
  from a saved file (`sources/wardlaw_2020_repec_abstract.html`, SHA-256 in SOURCES.md), but the full
  text is behind a paywall: SSRN (`abstract_id=3248750`) returned **HTTP 403** and the Wiley article
  page is gated. **Consequences, stated plainly:** I cannot report the magnitude behind "fairly
  negligible", cannot name the table it is in, and — the point that matters most for this project —
  **cannot determine whether the critique lands on Coval & Stafford's Eq. (4) unweighted count
  measure as hard as it lands on Edmans-Goldstein-Jiang's share-weighted MFFlow.** This project's own
  `coval_stafford_firesale` build deliberately implemented the unweighted count. Resolving this is
  recommendation 2 in the report and it needs paid or library access to the JF article.
- **A.2 Khan, Kogan & Serafeim (2012)** — named in the brief. **Not fetched, not read.** No claim is
  attributed to it anywhere. I stopped once the fire-sale branch was settled by Wardlaw's abstract
  plus the Wang preprint's own no-microcap sample restriction, both of which bind regardless of what
  KKS report.
- **A.3 Lou (2012) "A Flow-Based Explanation for Return Predictability", by size** — **not fetched.**
  The project already closed a Lou-FIT family (recorded in `coval_stafford_firesale_RESULTS.md` §1),
  and Lou's measure is the share/severity-weighted average that Wardlaw's critique targets most
  directly. Scope decision, not a finding about the paper.
- **A.4 Tax-loss-selling literature (Sias & Starks 1997; Reinganum; D'Mello-Ferris; Sikes 2014)** —
  **not fetched, not read.** Deliberate: this project's own June placebo already beat the December
  spec on its own data, and no literature claim can overturn an in-house placebo failure. Recorded as
  a scope decision. No number from any of these papers appears in the report.
- **A.5 Edmans, Goldstein & Jiang (JF 2012)** — PDF fetched and hashed (`sources/`), but I read only
  enough to confirm it is the origin of the MFFlow/FIT measure. **No effect size from it is quoted**;
  its headline result (an interquartile valuation decrease raising takeover likelihood by seven
  percentage points) is a corporate-finance real-effects result, not a tradable claim, and appears
  nowhere in my deliverables.
- **A.6 Cao, Han & Wang, "Institutional Investment Constraints and Stock Prices" (JFQA)** — PDF
  fetched and hashed, **abstract read only.** It turned out to be about institutions' reluctance to
  add to overweight positions, not about the $5 price-level rule, so it does not source candidate 3's
  price-level variant. No number from it is quoted.
- **A.7 Berger, "Selection Bias in Mutual Fund Fire Sales" (JFQA)** — **title and venue only, from a
  search-result listing.** Not fetched, not read. Mentioned once in the report explicitly as an
  unread second methodological attack; no claim rests on it.

## B. Things I looked for and could not find

- **B.1 A primary source measuring the fire-sale / flow-pressure effect SEPARATELY IN MICROCAPS (below
  the NYSE 20th percentile) or by ownership breadth.** This was the brief's central question for
  candidate 1 and **I could not find one.** The closest source (Wang, arXiv:2605.30672) excludes
  microcaps by construction in every headline table and splits by dollar volume *within* the
  non-microcap universe instead, giving an explicit reason (§4.4: "Very small stocks can be noisy and
  may have little mutual fund ownership"). So the honest statement is: **the literature I could reach
  does not measure the fire-sale mechanism in the corner this project needs it in**, and one paper
  says out loud that the mechanism may not exist there because microcaps have little fund ownership.
- **B.2 A primary academic source for a tradable closed-end-fund open-ending / liquidation effect on
  the UNDERLYING small stocks.** Searches returned practitioner material (CEF Advisors on the
  discount, ACA and CT Acquisitions on interval/tender-offer fund structures) and one Brookings paper
  on municipal-bond CEF deleveraging. Nothing reporting an effect size with a sample period on the
  underlying equities. **Candidate 6 is declined for want of a source, not on evidence against it.**
- **B.3 A primary source for institutional forced selling at the $5 price threshold specifically.**
  The brief asked for a "five-dollar rule" / "penny stock rule institutional constraint" source. What
  I found were trade-press articles (CFO.com, Yahoo Finance) asserting the rule is common but not
  universal, and one academic paper (Cao-Han-Wang) that merely *excludes* sub-$5 stocks as a sample
  filter. **No academic paper measuring a forced-selling price effect at the $5 boundary was found.**
  I did not propose it as a separate candidate; the delisting candidate (rank 1) is the version of
  this mechanism that does have a primary source for the mandate.
- **B.4 Any follow-up measuring post-publication decay of the Coval-Stafford fire-sale effect.** Not
  found. The report therefore reports no decay evidence for candidate 2 rather than inferring one.
- **B.5 A published net-of-cost return for ANY of these mechanisms.** Zero of the six candidates has
  one. Every effect size in this report is gross.

## C. Facts I did not measure, and which must not be quoted as if I had

- **C.1 Whether Alpaca returns any daily bars for a US equity AFTER its involuntary delisting to the
  Pink Sheets / OTC.** This is the single fact on which candidate 1 turns and **I did not probe it.**
  The 2026-09-11 coverage work established that Alpaca covers *delisted names up to their delisting
  date* ("six known-delisted anchors end on their delisting dates" — HANDOVER §1), which is evidence
  *against* post-delisting coverage, but nobody has checked directly. The report's recommendation is
  to run that probe before anything else.
- **C.2 The rate of involuntary US delistings in the 2016+ window.** The report's ~430/year figure is
  **my arithmetic on the paper's own two numbers** (7,300 delistings since 1995, "almost half"
  involuntary, over ~8.5 years) and describes 1995-2003, not the window we would trade. Order of
  magnitude only.
- **C.3 The effect of SEC Rule 15c2-11 (as amended, Sept 2021) on post-delisting OTC trading.** I did
  not read the rule or measure anything. It is recorded in the report as a plausible structural break
  that would make candidate 1 worse, explicitly labelled unverified.
- **C.4 Whether the published RFS 2015 version of Chang-Hong-Liskovich differs from the Aug 2013 NBER
  working paper I read.** A search-result summary described the published version as identifying
  "time trends in indexing effects and the types of funds that provide liquidity to indexers" — the
  NBER abstract I read says nothing of the kind. **Table and section numbers, and possibly results,
  may differ between the two versions.** Every CHL number I quote is from the NBER WP; the decay
  discussion in my report uses only the banding figures (~10% -> ~3%), which appear in both CHL and
  Appel-Gormley-Keim.
- **C.5 Whether Macey-O'Hara-Pompilio's published JLE 2008 article differs from the July 2004 working
  paper I read.** The title itself changed ("Law and Finance" -> "Law and Economics"). Section,
  table and footnote numbers may be renumbered. Footnote 45 and the price/spread figures are from the
  2004 WP.
- **C.6 The CUSIP->ticker crosswalk problem for micro-caps.** I state it as the hardest missing piece
  for candidate 2 but **I did not attempt it and did not measure how many N-PORT microcap CUSIPs
  would fail to resolve.**
- **C.7 Whether the Wang (2026) preprint's results replicate, or whether it has been refereed since
  29 May 2026.** Not checked.

## D. A judgment, labelled as a judgment

My ranking of `microcap_delisting_forced_exit` first is a **reading**, not a measurement. It rests on
the fact that it is the only candidate whose criterion-(ii) exclusion is *legal and structural*
(large regulated capital may not hold the security at all) rather than merely *economic* (large
capital finds it unprofitable). I believe that is the stronger form of the criterion. Someone else
could reasonably rank it last on the ground that a one-year, N=57, 2002 sample with a 25% spread is
not evidence of anything tradable. Both readings are defensible; the data probe in C.1 settles it
more cheaply than either argument.
