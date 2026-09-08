# Frazzini & Lamont, "Dumb Money" — what was actually read, and its provenance

Candidate #15 in the flow-mechanism queue. Every equation, table number, page
number and quoted phrase used by this family was read off the PDFs recorded
below. Nothing in this family is cited from memory.

## The published version WAS obtained — no paywall substitution this time

Unlike this queue's `margin_credit`, `ipo_lockup`, `quarter_end_marking` and
`coval_stafford` builds, all four of which had to fall back to an ungated
working paper and disclose the gap, the **published Journal of Financial
Economics article itself** was obtained here, from the corresponding author's
own faculty page at NYU Stern.

| | |
|---|---|
| Citation | Frazzini, Andrea and Owen A. Lamont, "Dumb money: Mutual fund flows and the cross-section of stock returns," *Journal of Financial Economics* **88**(2), May 2008, pp. 299–322 |
| DOI (printed on the PDF's own first page) | `10.1016/j.jfineco.2007.07.001` |
| URL fetched, 2026-09-08 | `https://pages.stern.nyu.edu/~afrazzin/pdf/Dumb%20money%20Mutual%20fund%20flows%20and%20the%20cross-section%20of%20stock%20returns%20-%20Frazzini%20and%20Lamont.pdf` |
| sha256 | `3c39e8ffa58008def0fb96c3c36989554e6658b282143936cb620f10ffb9c743` |
| Size / pages | 428,444 bytes / 24 pages (pypdf page count) |
| Local file | `dumbmoney_src/stern_published.pdf` (gitignored), text `dumbmoney_src/stern_published.txt` (committed) |

Confirmed to be the published version rather than a preprint by its own
first-page masthead — "Journal of Financial Economics 88 (2008) 299–322",
"Received 21 September 2005; received in revised form 22 May 2007; accepted 9
July 2007", "Available online 23 February 2008" — and by the running footer
"A. Frazzini, O.A. Lamont / Journal of Financial Economics 88 (2008) 299–322"
on every page. **All equation, table, figure and page references in this
family's pre-registration, code and results are to THIS published version.**

## Two earlier drafts, fetched as cross-checks only

Not used as the citation base; fetched so that any claim about what the
published version says could be checked against what the drafts said.

| Version | URL | sha256 | Pages |
|---|---|---|---|
| NBER WP 11526, July 2005 | `https://www.nber.org/system/files/working_papers/w11526/w11526.pdf` | `80091f8529d283bdfcf19ebba7965f223eadb450d4af275958ae8215294155a0` | 60 |
| Yale/Shiller behfin draft, 27 March 2005 ("PRELIMINARY AND INCOMPLETE") | `http://www.econ.yale.edu/~shiller/behfin/2005-04/frazzini-lamont.pdf` | `03ded558bfef96f3049c7a6112d25d13677f1ccd8141a48fba078078ae1863e3` | 55 |

The published paper's own footnote 2 (p.304) points at the NBER version for
the CRSP↔Thomson matching procedure and data-error handling, which the
published version drops for space — that is the one place the working paper is
genuinely load-bearing rather than a cross-check.

## Reproducibility

Text was extracted with `pypdf` (the version in `backend/venv`) and the
extracted `.txt` files are committed so that a reviewer can grep exactly what
was read without re-downloading anything. The PDFs themselves are gitignored
(this repo commits no PDFs anywhere) but are byte-pinned by the sha256s above.
