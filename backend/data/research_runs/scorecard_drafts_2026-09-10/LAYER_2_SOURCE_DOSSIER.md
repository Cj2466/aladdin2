# Layer 2 source dossier for the four live registrations (2026-09-10)

What the mechanism-fidelity pass needs before it starts, gathered mechanically and
laid out **without pairing anything**. Deliberately no proposed mapping from paper
section to code: handing a reviewer a curated pairing invites them to validate the
pairing instead of checking it independently, which is the one thing this artifact
must not cause.

Companion to the drafts in this directory, whose `layer_2_mechanism_fidelity` block is
null in all four by design.

## 1. Where each family's source is recorded

| live family | source(s) the module cites | provenance the module claims | preregistration on disk |
|---|---|---|---|
| `quality_cbop` | Ball, Gerakos, Linnainmaa & Nikolaev, "Accruals, cash flows, and operating profitability in the cross section of stock returns", *JFE* 121(1) 2016; Hirshleifer, Hou, Teoh & Zhang (NOA) | "fetched live 2026-08-28, not recalled from memory" — working-paper PDF from `ivey.uwo.ca/media/3775325/gerakos.pdf`; a second published-version PDF from `anderson.ucla.edu`, §3.1 cited | **none found** (the draft says so in words) |
| `short_interest_ratio` | "good news in short interest", *JFE* 96(1) 2010 | "BIBLIOGRAPHIC RECORD AND ABSTRACT: VERIFIED, live-fetched from RePEc" | `short_interest_PREREGISTRATION.txt` |
| `lazy_prices_jaccard_full` | Cohen, Malloy & Nguyen, *Journal of Finance* 75(3) 2020, pp. 1371-1415, doi:10.1111/jofi.12885; also NBER WP 25084 | "the NBER working paper PDF was fetched from nber.org and text-extracted IN FULL on 2026-09-01, and every quote below is from that extracted document" | `lazy_prices_2026-09-01_preregistration.txt` |
| `cross_sectional_crypto` | Jegadeesh & Titman (*JF* 1993); Liu, Tsyvinski & Wu (*JF* 2022); Liu & Tsyvinski (*RFS* 2021); De Bondt & Thaler; "Value and Momentum Everywhere" (*JF* 2013); Ang et al. (*JF* 2006); Blitz & van Vliet | bibliographic only; no fetch-and-extract claim in the header | **none found** |

## 2. The gap this exposes

**No source text is retained anywhere in the repository for any of the four.** A search
across the whole tree found exactly three PDFs, all belonging to a different family
(`frazzini-lamont-dumbmoney`, and only in an unmerged worktree). The modules record that
papers *were* fetched and quoted — with URLs, dates, and in `lazy_prices`' case an
explicit statement that the full text was extracted — but the extracted text was not
kept.

That is the same defect class as everything else corrected on 2026-09-09/10: **an input
that verification depends on, which can vanish and cannot be reconstructed.** Prices,
fundamentals and filing indexes now have point-in-time stores. Source texts do not.

The practical consequence for the layer-2 pass: every quote must be re-verified against
a document that has to be re-fetched, and a dead link or a paywall makes a citation
unverifiable rather than merely inconvenient. The `source_text_obtained` field in the
scorecard schema is therefore a question about *now*, not about 2026-08-28, and the
honest answer today is **no** for all four.

**Not fixed here, and deliberately not**: retrieving and storing published papers is a
decision with a copyright dimension and it is the owner's to make, not something to do
unilaterally at 03:40 while they are asleep. Recorded as the recommendation instead:
retain the extracted text (not necessarily the PDF) for every family whose scorecard
claims a citation, in the same gitignored-with-committed-manifest pattern the three data
stores already use.

## 3. What the layer-2 pass has to produce, per family

From the schema (`registration_scorecard.py`), for each of the four:

* `source_citation` — author, title, journal, volume(issue), year, pages, doi.
* `source_text_obtained` — true only if the reviewer actually has the document in hand.
* `construction_choices[]` — each `{choice, source_locus}` where source_locus names the
  paper, section and equation/table. This is the field the test file's docstring
  forbids reconstructing from code.
* `deviations[]` — each `{deviation, reason}`.
* `independent_reviewer`, `..._signed_off_at`, `..._findings` — including "nothing" when
  nothing was found, which is itself a result.

Plus `layer_3_regime_conditional.source_claim_type` and `claim_evidence`, which need the
paper to establish whether its claim is conditional or unconditional.

## 4. Two things already flagged in the drafts that the pass should carry

1. **`lazy_prices` has a materially disagreeing DSR across run_tags.** Its canonical
   registration run (`lazy_prices_2026-09-01`) records 0.7540 while a later cost-model
   rerun of the same trial_id gives 0.8639 — a ~0.06 gap, and the committed
   preservation-score artifact's rerun DSR disagrees with the registered figure by the
   same amount. Disclosed in that draft's `preservation_inputs_note`, unresolved.
2. **`cross_sectional_crypto` is a documented deliberate exception**: forward-tracked
   despite failing every standing DSR bar, so no single pass threshold was ever
   pre-declared. Its draft leaves `dsr_pass_threshold` null rather than inventing one,
   and its verdict must be read against that exception, not against the normal rule.

## 5. Provenance of this dossier

Assembled by reading the four module headers and searching the tree for retained source
documents. Every claim above is either quoted from a module docstring or is the result
of a file search stated as such. No paper was read, no mapping was proposed, and no
scorecard field was filled.
